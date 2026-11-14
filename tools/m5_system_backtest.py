"""Current M5/native-HTF policy replay; isolated research, no broker authority."""
import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.data.top_down import TIMEFRAMES, MINUTES
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import ExitVariant
from atlas_ai.testing.policy_replay import cache_candidates,replay
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import broker_snapshot,safe_settings
from tools.learn_candidate_ranker import digest,save_signed

LIMITATIONS=[
    "Uses the enabled built-in strategies and current deterministic policies; observer-only SMC proposals are not executable strategies.",
    "Historical screenshots, visual approvals, external macro/news context, Gemini calls, meta-model state, adaptive lessons and evolved strategy versions are not reconstructed.",
    "Strict mode refuses execution without missing historical evidence. Diagnostic mode measures only modelled policy opportunities, never executable returns.",
    "One modelled position at a time; next M5 opening quote with prior completed spread proxy; stop-first M5 exits are not tick-level live management.",
    "Current fee, currency conversion, stop levels and margin are frozen approximations for historical dates. Slippage is assumed, not measured from natural fills.",
    "Previously inspected history is reused retrospective evidence; this is not full live-system parity or proof of profitability or broker lifecycle.",
]


def run(output,days=30):
    if not 1<=days<=90:raise ValueError('bounded_history_days_required')
    original=load_settings()
    if original.timeframe!='M5' or not original.top_down_confluence_enabled:
        raise ValueError('configured_M5_and_top_down_required')
    output=output.resolve();output.relative_to(Path(original.storage_dir).resolve())
    output.mkdir(parents=True,exist_ok=False)
    end=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    end=end.replace(minute=end.minute//5*5);start=end-timedelta(days=days)
    def progress(stage,**kw):atomic_json(output/'progress.json',{'stage':stage,'checked_at':datetime.now(timezone.utc).isoformat(),**kw})
    def deny(*a,**kw):raise AssertionError('system_backtest_broker_dispatch_forbidden')
    try:
        with patch.object(mt5,'order_send',deny):
            progress('broker_cost_snapshot')
            spec,evidence,limits=broker_snapshot(original)
            frames={};data={}
            for tf in (*TIMEFRAMES,'M5'):
                progress('fetch_native_history',timeframe=tf)
                warmup=140 if tf=='D1' else 30 if tf!='M5' else 7
                frame=MarketDataFeed(replace(original,timeframe=tf)).get_rates_range(start-timedelta(days=warmup),end)
                times=pd.to_datetime(frame.time,utc=True)
                frame=frame[times+pd.Timedelta(minutes=MINUTES[tf])<=pd.Timestamp(end)].reset_index(drop=True)
                if len(frame)<90:raise ValueError('insufficient_native_history:'+tf)
                frame=prepare_frame(frame);frames[tf]=frame
                frame.to_csv(output/(tf+'.csv'),index=False)
                data[tf]={'bars':len(frame),'first_utc':pd.Timestamp(frame.time.iloc[0]).isoformat(),
                          'last_utc':pd.Timestamp(frame.time.iloc[-1]).isoformat(),'sha256':digest(output/(tf+'.csv'))}
            hashes={}
            for folder in ['atlas_ai','tools']:
                for source in (ROOT/folder).rglob('*.py'):
                    rel=source.relative_to(ROOT);target=output/'frozen_source'/rel
                    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                    hashes[rel.as_posix()]=digest(target)
            from dataclasses import asdict
            save_signed(output,'manifest',{'schema':'atlas_M5_system_replay_v1','frozen_at':datetime.now(timezone.utc).isoformat(),
                'start_utc':start.isoformat(),'end_utc':end.isoformat(),'settings':safe_settings(original),
                'spec':asdict(spec),'cost_evidence':evidence,'limits':limits,'data':data,'source_hashes':hashes,
                'slippage_points_per_side':3,'limitations':LIMITATIONS,'broker_eligible':False,'orders_sent':0})
            with tempfile.TemporaryDirectory(prefix='isolated_',dir=output) as temporary:
                settings=replace(original,execute_trades=False,storage_dir=temporary,gemini_api_key='',openai_api_key='',
                                 backtest_persist_learning_state=False,backtest_record_loss_analysis=False)
                store=KnowledgeStore(temporary)
                frame=frames['M5'];times=pd.to_datetime(frame.time,utc=True)
                eligible=times+pd.Timedelta(minutes=5)>=pd.Timestamp(start)
                start_index=max(250,int(eligible.to_numpy().nonzero()[0][0]))
                candidates,counts,names=cache_candidates(frame,settings,store,
                    lambda **kw:progress('candidate_generation',**{k:v for k,v in kw.items() if k!='stage'}),
                    start_index=start_index,native_frames=frames)
                # Freeze decisions and native context before exit/outcome evaluation.
                save_signed(output,'candidates',{'rows':candidates,'counts':counts,'strategies':names})
                candidate_hash=digest(output/'candidates.json')
                variant=ExitVariant('configured',settings.backtest_break_even_lock_r,3.)
                execution=frame.copy();execution['spread']=frame.spread.shift(1)
                result={'schema':'atlas_M5_system_replay_result_v1','state':'running','timeframe':'M5',
                        'start_utc':start.isoformat(),'end_utc':end.isoformat(),'strategies':names,
                        'generation_counts':counts,'candidate_bars':len(candidates),'limitations':LIMITATIONS,
                        'full_live_policy_parity':False,'broker_eligible':False,'orders_sent':0,
                        'manifest_sha256':digest(output/'manifest.json'),'candidate_sha256':candidate_hash}
                for strict,label in [(False,'diagnostic'),(True,'strict_evidence')]:
                    progress('policy_replay',lane=label,candidate_bars=len(candidates))
                    result[label]=replay(execution,candidates,settings,spec,variant,store,limits,strict=strict,start=start,end=end)
                    if digest(output/'candidates.json')!=candidate_hash:raise ValueError('candidates_changed')
                    save_signed(output,'report',result)
                result['state']='completed_research_only';result['finished_at']=datetime.now(timezone.utc).isoformat()
                save_signed(output,'report',result);progress('completed_research_only')
                return result
    except Exception as exc:
        progress('failed',error=type(exc).__name__,reason=str(exc));raise
    finally:mt5.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--days',type=int,default=30)
    args=parser.parse_args();r=run(args.output,args.days)
    print(json.dumps({'state':r['state'],'report':str(args.output/'report.json'),
        'diagnostic_trades':r['diagnostic']['trades'],'strict_trades':r['strict_evidence']['trades']}))
