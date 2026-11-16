"""One frozen M5 proposal, repaired baseline, chronological retrospective validation."""
import argparse
from collections import Counter,defaultdict
from contextlib import nullcontext
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
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
from atlas_ai.data.top_down import TIMEFRAMES,MINUTES
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.strategies.research_protocol import environment_versions
from atlas_ai.models import TradeSignal
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant,simulate
from atlas_ai.testing.policy_replay import cache_candidates,replay
from atlas_ai.testing.m5_proposal import matched_volatility,calibrate,proposal_candidates,volatility_policy
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import broker_snapshot,safe_settings
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for
from tools.m5_stop_research import review,POLICY_SOURCES
from tools.m5_system_backtest import LIMITATIONS

LANES=('repaired_baseline','fixed_M5_proposal')
CRITICAL=(*POLICY_SOURCES,'atlas_ai/data/top_down.py','atlas_ai/testing/m5_proposal.py',
          'tools/m5_calibration_study.py','tools/m5_demo_observer.py')


def deny(*a,**kw):raise AssertionError('M5_research_cannot_dispatch_orders')


def fetch_frames(settings,start,end,*,minute=False):
    frames={}
    for tf in (*TIMEFRAMES,'M5',*(['M1'] if minute else [])):
        warmup=140 if tf=='D1' else 30 if tf in TIMEFRAMES else 7 if tf=='M5' else 1
        f=MarketDataFeed(replace(settings,timeframe=tf)).get_rates_range(
            (start-pd.Timedelta(days=warmup)).to_pydatetime(),end.to_pydatetime())
        if len(f)<90:raise ValueError('insufficient_native_history:'+tf)
        frames[tf]=prepare_frame(f)
    return frames


def replay_lane(frame,rows,cfg,spec,limits,calibration,lane,start,end,*,audit=None):
    execution=frame.copy();execution['spread']=frame.spread.shift(1)
    change=(patch.object(AtlasTrader,'_volatility_safety_state',
        lambda self,*,context_snapshot,regime:volatility_policy(context_snapshot,regime,calibration))
        if lane=='fixed_M5_proposal' else nullcontext())
    with change:
        return replay(execution,rows,cfg,spec,ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                      KnowledgeStore(cfg.storage_dir),limits,start=start.to_pydatetime(),end=end.to_pydatetime(),audit=audit)


def rejected_path_audit(frame,traces,cfg,spec,end):
    """Independent overlapping hypothetical paths; never portfolio profit or selection."""
    groups=defaultdict(Counter);execution=frame.copy();execution['spread']=frame.spread.shift(1)
    for row in traces:
        group=groups[row['reason']];group['evaluations']+=1
        if row['signal'] is None:continue
        signal=TradeSignal(**row['signal']);entry=row['index']+1;last=entry+cfg.backtest_max_hold_bars-1
        if last>=len(frame):continue
        times=pd.to_datetime(frame.time.iloc[entry:last+1],utc=True)
        if times.iloc[-1]+pd.Timedelta(minutes=5)>end or not times.diff().dropna().eq(pd.Timedelta(minutes=5)).all():continue
        outcome=simulate(execution,entry,signal,spec.volume_min,spec,cfg,ExitVariant('configured',cfg.backtest_break_even_lock_r,3.))
        group['labelled_hypothetical_paths']+=1
        group['positive_hypothetical_paths' if outcome['net_cash']>0 else 'nonpositive_hypothetical_paths']+=1
        group['minimum_lot_risk_exceeded']+=int(outcome['initial_risk_cash']+spec.roundtrip_fee_per_lot*spec.volume_min
            +abs(spec.cash(-6*spec.point,spec.volume_min))>cfg.backtest_initial_balance*cfg.max_risk_per_trade)
    return {'by_sequential_rejection':dict(groups),'independent_overlapping_paths':True,
        'usable_for_filter_removal':False,'note':'Uses future bars only as outcome labels, after the proposal is frozen. A positive rejected path is not a verified missed opportunity. Preselection rejections have no chosen signal and are not assigned invented outcomes.'}


def validate(directory,*,verify_running_source=False):
    p=signed(directory,'protocol')
    if p.get('broker_eligible') is not False or p.get('auto_promotion') is not False:raise ValueError('research_only_required')
    for name,h in p['critical_source_hashes'].items():
        if digest(directory/'frozen_source'/name)!=h or (verify_running_source and digest(ROOT/name)!=h):raise ValueError('frozen_policy_changed:'+name)
    if p['settings']!=json.loads(json.dumps(safe_settings(load_settings()))):raise ValueError('settings_changed')
    if p['account_scope']!=account_scope(load_settings()):raise ValueError('account_scope_changed')
    if p['environment']!=environment_versions():raise ValueError('environment_changed')
    return p


def load_reused_frames(reuse,protocol):
    old=signed(reuse,'protocol')
    if any(old[key]!=json.loads(json.dumps(protocol[key])) for key in ['development_start','split','validation_end','settings']):
        raise ValueError('reused_window_or_settings_changed')
    inputs=signed(reuse,'inputs');frames={}
    for tf,h in inputs.items():
        if digest(reuse/(tf+'.csv'))!=h:raise ValueError('reused_native_input_changed')
        frames[tf]=prepare_frame(pd.read_csv(reuse/(tf+'.csv')))
    if set(frames)!=set((*TIMEFRAMES,'M5','M1')):raise ValueError('missing_reused_native_frames')
    return frames


def run(directory,start,split,end,*,reuse=None):
    if not start<split<end or any(t.tzinfo is None for t in [start,split,end]):raise ValueError('aware_ordered_windows_required')
    settings=load_settings();directory=directory.resolve();directory.relative_to(Path(settings.storage_dir).resolve())
    if settings.timeframe!='M5' or not settings.top_down_confluence_enabled:raise ValueError('M5_top_down_required')
    directory.mkdir(parents=True,exist_ok=False)
    def progress(phase,**kw):atomic_json(directory/'progress.json',{'phase':phase,'checked_at':datetime.now(timezone.utc).isoformat(),**kw})
    try:
        with patch.object(mt5,'order_send',deny):
            from tools.smc_validation import check_account
            check_account(settings);spec,costs,limits=broker_snapshot(settings)
            for folder in ['atlas_ai','tools']:
                for source in (ROOT/folder).rglob('*.py'):
                    target=directory/'frozen_source'/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            p={'schema':'atlas_M5_calibration_v1','frozen_at':datetime.now(timezone.utc).isoformat(),'project_root':str(ROOT),
               'development_start':start.isoformat(),'split':split.isoformat(),'validation_end':end.isoformat(),
               'calibration_rule':'Median paired M5/M1 absolute-move ratio over matching 295-minute completed windows; minimum 1000 pairs and 10 dates; reject factors outside [1,5]. Multiply only .045/.07 price-volatility boundaries; VIX panic veto unchanged.',
               'entry_rule':'Last completed M5 candle must close in the signal direction and beyond the previous close; use existing reviewed ATR point-conversion distances.',
               'parameter_search':False,'retune_after_outcomes':False,'settings':safe_settings(settings),'spec':asdict(spec),'cost_evidence':costs,'limits':limits,
               'review_criteria':{'trades_per_period':30,'dates_per_period':2,'positive_mean_net_R':True,'minimum_profit_factor':1.1,'maximum_drawdown_R':6,'baseline_minimum_trades':30,'candidate_mean_R_at_least_baseline':True},
               'critical_source_hashes':{name:digest(ROOT/name) for name in CRITICAL},'account_scope':account_scope(settings),'environment':environment_versions(),
               'historical_status':'Previously available history; chronological validation is retrospective, not blind or fresh forward proof.',
               'forward_deadline':(datetime.now(timezone.utc)+timedelta(days=21)).isoformat(),
               'broker_eligible':False,'auto_promotion':False,'orders_sent':0,'limitations':LIMITATIONS}
            save_signed(directory,'protocol',p)
            save_signed(directory,'source_receipt',{'protocol_sha256':digest(directory/'protocol.json'),
                'source_hashes':{x.relative_to(directory/'frozen_source').as_posix():digest(x) for x in (directory/'frozen_source').rglob('*.py')}})
            atomic_json(Path(settings.storage_dir)/'m5_calibration_active.json',{'run_dir':str(directory)})
            atomic_json(Path(settings.storage_dir)/'m5_calibration_active.json',{'run_dir':str(directory)})
            progress('fetching_native_M1_M5_and_higher_frames')
            if reuse is None:
                frames=fetch_frames(settings,start,end,minute=True)
            else:
                frames=load_reused_frames(reuse,p)
                save_signed(directory,'input_lineage',{'source_protocol_sha256':digest(reuse/'protocol.json'),
                    'inputs_sha256':digest(reuse/'inputs.json'),'reason':'Integrity-verified raw data reuse after an interrupted observer-hardening run; no outcomes reused.'})
            for tf,f in frames.items():f.to_csv(directory/(tf+'.csv'),index=False)
            save_signed(directory,'inputs',{tf:digest(directory/(tf+'.csv')) for tf in frames})
            pairs=matched_volatility(frames['M1'],frames['M5']);calibration=calibrate(pairs,start,split)
            save_signed(directory,'calibration',{**calibration,'frozen_at':datetime.now(timezone.utc).isoformat(),
                        'protocol_sha256':digest(directory/'protocol.json'),'no_trade_outcome_optimization':True})
            with tempfile.TemporaryDirectory(prefix='isolated_',dir=directory) as temp:
                cfg=settings_for(p,temp);frame=frames['M5'];times=pd.to_datetime(frame.time,utc=True)
                first=max(250,int((times+pd.Timedelta(minutes=5)>=start).to_numpy().nonzero()[0][0]))
                rows,counts,names=cache_candidates(frame,cfg,KnowledgeStore(temp),
                    lambda **kw:progress('candidate_generation',**{k:v for k,v in kw.items() if k!='stage'}),start_index=first,native_frames=frames)
                proposed,entry_counts=proposal_candidates(frame,rows,spec.point)
                save_signed(directory,'predictions',{'repaired_baseline':rows,'fixed_M5_proposal':proposed,'strategies':names,
                    'generation_counts':counts,'entry_confirmation_counts':entry_counts})
                save_signed(directory,'prediction_receipt',{'sha256':digest(directory/'predictions.json'),'calibration_sha256':digest(directory/'calibration.json'),
                    'protocol_sha256':digest(directory/'protocol.json'),'predictions_frozen_before_labels':True})
                result={'state':'running','results':{},'broker_eligible':False,'auto_promotion':False,'orders_sent':0}
                traces={};windows={'development':(start,split),'validation':(split,end)}
                with patch.object(mt5,'initialize',deny):
                    for period,(begin,finish) in windows.items():
                        result['results'][period]={}
                        for lane,candidates in [('repaired_baseline',rows),('fixed_M5_proposal',proposed)]:
                            progress('portfolio_replay',period=period,lane=lane);trace=[]
                            stats=replay_lane(frame,candidates,cfg,spec,limits,calibration,lane,begin,finish,audit=trace.append)
                            stats['review']=review(stats);result['results'][period][lane]=stats;traces[period+'/'+lane]=trace
                            save_signed(directory,'report',result)
                # Final selection is fixed before the rejected-path diagnostics are labelled.
                candidate_ok=all(result['results'][period]['fixed_M5_proposal']['review']['passed']
                    and result['results'][period]['repaired_baseline']['trades']>=30
                    and result['results'][period]['fixed_M5_proposal']['mean_net_r']>=result['results'][period]['repaired_baseline']['mean_net_r']
                    for period in windows)
                result['historical_review_passed']=candidate_ok;result['selected_for_live']=None
                result['forward_observation_authority']='read_only_closed_bar_demo_research_even_if_unqualified; never execution approval'
                save_signed(directory,'selection',{'historical_review_passed':candidate_ok,'selected_for_live':None,'broker_eligible':False})
                for key,trace in traces.items():
                    period,lane=key.split('/');finish=windows[period][1]
                    progress('rejected_path_labels',period=period,lane=lane)
                    result['results'][period][lane]['filter_audit']=rejected_path_audit(frame,trace,cfg,spec,finish)
                # A held-out distribution check does not select or retune thresholds.
                result['volatility_coverage']={}
                for period,(begin,finish) in windows.items():
                    sample=pairs[(pairs.index>=begin)&(pairs.index<finish)]
                    result['volatility_coverage'][period]={'paired_windows':len(sample),
                        'baseline_extreme_fraction':float((sample.m5>=.07).mean()),
                        'proposal_extreme_fraction':float((sample.m5>=calibration['extreme_pct']).mean())}
                result.update(state='completed_research_only',protocol_sha256=digest(directory/'protocol.json'),
                    calibration_sha256=digest(directory/'calibration.json'),prediction_receipt_sha256=digest(directory/'prediction_receipt.json'))
                if digest(directory/'predictions.json')!=signed(directory,'prediction_receipt')['sha256']:raise ValueError('predictions_changed')
                save_signed(directory,'report',result);progress('completed_research_only')
                return result
    except Exception as exc:
        progress('failed',error=type(exc).__name__,reason=str(exc));raise
    finally:mt5.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',default='2026-10-01T00:00:00Z');parser.add_argument('--split',default='2026-10-15T00:00:00Z');parser.add_argument('--end',default='2026-11-14T00:00:00Z')
    parser.add_argument('--reuse-inputs',type=Path)
    a=parser.parse_args();r=run(a.output,pd.Timestamp(a.start),pd.Timestamp(a.split),pd.Timestamp(a.end),reuse=a.reuse_inputs);print(json.dumps({'state':r['state'],'historical_review_passed':r['historical_review_passed']}))
