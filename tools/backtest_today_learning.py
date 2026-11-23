"""Today's closed-M5 diagnostic and recorded-entry learning probes. No orders."""
import argparse
from copy import deepcopy
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings,get_active_thresholds
from atlas_ai.data.broker_clock import normalize_rates,utc_query_time,broker_time_to_utc
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.inventory import base_inventory
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import policy_trader,replay
from atlas_ai.testing.smc_validation import HistoricalFeed
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.penalty_shadow import read_record,load_saved
from atlas_ai.testing.decision_archive import index_rows


def archived_before(storage,before):
    archive=storage/'replay_evidence'
    rows=[r for r in index_rows(archive) if r.get('decision_at') and pd.Timestamp(r['decision_at'])<=before]
    for row in reversed(rows):
        record=read_record(archive,row)
        if pd.Timestamp(record['observed_at'])<=before:
            return load_saved(archive,record,'learning_state.json'),{'record_id':row['record_id'],
                'observed_at':record['observed_at'],'decision_at':row['decision_at']}
    raise ValueError('no_causal_archived_memory_available')


def capture(directory):
    cfg=load_settings();storage=Path(cfg.storage_dir).resolve();directory=directory.resolve();directory.relative_to(storage)
    directory.mkdir(parents=True,exist_ok=False)
    now=datetime.now(timezone.utc);local=now.astimezone(ZoneInfo('Africa/Johannesburg'))
    start=local.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
    end=now.replace(second=0,microsecond=0);end=end.replace(minute=end.minute//5*5)
    entries=[]
    for line in (storage/'events.jsonl').open(encoding='utf-8'):
        try:r=json.loads(line)
        except ValueError:continue
        if start.isoformat()<=r.get('time','')<=now.isoformat() and r.get('type')=='execution' and str(r.get('message','')).startswith('Executed '):
            entries.append({'at':r['time'],'status':r['meta']})
    current=json.loads((storage/'learning_state.json').read_text());current=current.get('state',current)
    before,receipt=archived_before(storage,pd.Timestamp(start))
    save_signed(directory,'before_memory',before);save_signed(directory,'after_memory',current)
    for index,entry in enumerate(entries):
        memory,evidence=archived_before(storage,pd.Timestamp(entry['at'])-pd.Timedelta(seconds=5))
        save_signed(directory,'entry_memory_'+str(index),memory);entry['causal_memory_receipt']=evidence
    save_signed(directory,'recorded_entries',{'entries':entries})
    frames={};hashes={}
    with patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        if not mt5.initialize(path=cfg.hfm_terminal_path):raise ValueError('attach_failed')
        account=mt5.account_info()
        if not account or account.login!=cfg.hfm_login or account.server!=cfg.hfm_server or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise ValueError('matching_demo_required')
        info=mt5.symbol_info(cfg.symbol);tick=mt5.symbol_info_tick(cfg.symbol)
        deals=mt5.history_deals_get(utc_query_time(start,cfg),utc_query_time(now,cfg))
        if deals is None:raise ValueError('broker_deals_unavailable')
        ours=[d for d in deals if d.symbol==cfg.symbol and d.magic==cfg.magic_number]
        gross=sum(d.profit+d.commission+d.swap+d.fee for d in ours)
        entry_volume=sum(d.volume for d in ours if d.entry==mt5.DEAL_ENTRY_IN)
        fee=sum(abs(d.commission)+abs(d.fee) for d in ours)/entry_volume if entry_volume else 0.
        margin=mt5.order_calc_margin(mt5.ORDER_TYPE_BUY,cfg.symbol,1.,tick.ask)
        if margin is None:raise ValueError('margin_unavailable')
        spec=BrokerSpec(info.point,info.trade_tick_size,info.trade_tick_value_profit,info.trade_tick_value_loss,
            info.volume_min,info.volume_max,info.volume_step,info.digits,info.trade_stops_level,info.trade_freeze_level,margin,fee)
        for tf,n in [('D1',90),('H4',180),('H1',300),('M15',1000),('M5',2000)]:
            raw=mt5.copy_rates_from_pos(cfg.symbol,getattr(mt5,'TIMEFRAME_'+tf),0,n)
            if raw is None:raise ValueError('rates_unavailable:'+tf)
            f=normalize_rates(raw,cfg)
            if tf=='M5':f=f[pd.to_datetime(f.time,utc=True)+pd.Timedelta(minutes=5)<=pd.Timestamp(end)]
            f.to_csv(directory/(tf+'.csv'),index=False);hashes[tf]=digest(directory/(tf+'.csv'))
        actual=[{k:getattr(d,k) for k in ['ticket','position_id','entry','type','volume','price','profit','commission','swap','fee']}|
                {'time_utc':broker_time_to_utc(d.time,cfg).isoformat()} for d in ours]
    automation=json.loads((storage/'automation_state.json').read_text());automation=automation.get('payload',automation)
    session=automation['session_control'];pilot=automation['tiny_live_pilot']
    limits={'day_trades':min(session['daily_trade_limit'],pilot['max_trades_per_day']),
        'loss_streak':min(session['consecutive_loss_limit'],pilot['max_consecutive_losses']),
        'daily_loss_percent':pilot['daily_loss_cap'],'lot_cap':pilot['size_cap'],'setup_family':pilot['allowed_setup_family']}
    # Nominal start of day reconstructed only when no current exposure exists.
    settings=safe_settings(replace(cfg,backtest_initial_balance=account.balance-gross))
    source_hashes={}
    for folder in ('atlas_ai','tools'):
        for source in (ROOT/folder).rglob('*.py'):
            name=source.relative_to(ROOT);out=directory/'frozen_source'/name;out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,out);source_hashes[name.as_posix()]=digest(out)
    save_signed(directory,'inputs',hashes)
    save_signed(directory,'protocol',{'captured_at':now.isoformat(),'start_utc':start.isoformat(),'end_utc':end.isoformat(),
        'settings':settings,'spec':asdict(spec),'limits':limits,'source_hashes':source_hashes,'account_scope':account_scope(cfg),
        'before_memory_receipt':receipt,'before_memory_sha256':digest(directory/'before_memory.json'),
        'after_memory_sha256':digest(directory/'after_memory.json'),'recorded_entries_sha256':digest(directory/'recorded_entries.json'),
        'actual_deals':actual,'actual_net_cash':gross,'broker_eligible':False,'orders_sent':0,
        'limitations':['Closed-M5 next-open replay is not the live intrabar path and cannot reproduce both entries within one candle.',
            'Applying after-loss memory to earlier candles is hindsight, not evidence of prospective learning or improved profitability.',
            'Archived memory is sampled after publication, not an atomic pre-decision checkpoint.',
            'Full macro, visual, approval, actual fill and exact adaptive state parity are unavailable.',
            'Current conversion/margin and previous closed-bar spread plus three adverse points per side are modeled costs.']})
    print('Frozen today inputs, causal memory samples and current memory; no orders.',flush=True)


def learning_probe(trader,status,at):
    import atlas_ai.trader as module
    from datetime import datetime as NativeDatetime
    class Clock(NativeDatetime):
        @classmethod
        def now(cls,tz=None):return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    chosen=status['chosen'];signal=TradeSignal(**{k:chosen[k] for k in ['strategy','side','confidence','stop_loss_points','take_profit_points']})
    context=(status.get('signal_generation') or {}).get('context') or status.get('context_snapshot') or {}
    with patch.object(module,'datetime',Clock):
        lesson_conf,lesson=trader._loss_pattern_lesson_adjustment(signal,context)
        online_conf,online=trader._online_learning_adjustment(signal,status)
        memory=trader._load_loss_memory();hour=trader._loss_pattern_penalty_detail(signal.side,at,memory)
        side=trader._recent_side_penalty_detail(signal.side,memory,current_session=status.get('context_snapshot',{}).get('session',''))
        recovery=trader._loss_learning_recovery_evidence(side=signal.side,status=status,hour_detail=hour,side_detail=side)
        factor=float(recovery.get('reduction_factor',1.))
        penalty=min(.42,(float(hour.get('penalty',0))+float(side.get('penalty',0)))*factor)
        confidence=online_conf*(1-penalty)
        block=trader._loss_pattern_block_detail(signal.side,memory,at)
    threshold=float(status.get('min_confidence_threshold') or get_active_thresholds(trader.settings)['confidence'])
    return {'lesson':lesson,'lesson_confidence_before_conviction_overwrite':lesson_conf,'online':online,
        'lesson_adjustment_used_by_entry_timing_path':str(getattr(trader.settings,'timeframe','M5')).upper()=='M1',
        'lesson_probe_is_diagnostic_on_M5':str(getattr(trader.settings,'timeframe','M5')).upper()=='M5',
        'hour':hour,'side':side,'recovery':recovery,'hard_block':block,'post_conviction_confidence':confidence,
        'threshold':threshold,'learning_would_block':bool(block.get('reason')) or confidence<threshold,
        'stop_loss_points':signal.stop_loss_points,'take_profit_points':signal.take_profit_points,
        'scope':'Learning components for fixed recorded candidate; not a complete execution approval.'}


def run(directory,*,cached=False):
    p=signed(directory,'protocol')
    for name,h in p['source_hashes'].items():
        if digest(ROOT/name)!=h:raise ValueError('frozen_source_changed:'+name)
    for name in ('before_memory','after_memory','recorded_entries'):
        if digest(directory/(name+'.json'))!=p[name+'_sha256']:raise ValueError('frozen_evidence_changed:'+name)
    frames={}
    for tf,h in signed(directory,'inputs').items():
        path=directory/(tf+'.csv')
        if digest(path)!=h:raise ValueError('candles_changed:'+tf)
        frames[tf]=pd.read_csv(path);frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
    frame=prepare_frame(frames['M5']);start=pd.Timestamp(p['start_utc']);end=pd.Timestamp(p['end_utc'])
    entries=signed(directory,'recorded_entries')['entries'];results={};probes=[]
    before=signed(directory,'before_memory');after=signed(directory,'after_memory')
    # Hold the same captured subset of archived state fields in both replay lanes.
    common=set(before)&set(after)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory() as temporary:
        cfg=settings_for(p,temporary);spec=BrokerSpec(**p['spec'])
        for lane,state in [('before_today',before),('after_losses_hindsight',after)]:
            store=KnowledgeStore(str(Path(temporary)/lane));store.update_learning_state(lambda _,state=state:{k:state[k] for k in common})
            trader=policy_trader(cfg,store);feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES});rows=[]
            strategies=[s for s in base_inventory('M5',top_down=True) if trader._strategy_enabled(s.name)]
            for i in ([] if cached else range(250,len(frame)-1)):
                at=pd.Timestamp(frame.time.iloc[i],tz='UTC')+pd.Timedelta(minutes=5)
                if not start<=at<end:continue
                if pd.Timestamp(frame.time.iloc[i+1],tz='UTC')!=at:continue
                window=frame.iloc[max(0,i-1199):i+1];context=trader._signal_generation_context(window,at.to_pydatetime())
                signals=[asdict(trader._apply_signal_generation_gating(trader._sanitize_signal(s.generate_signal(window)),context)) for s in strategies]
                feed.now=at;higher=collect(feed,at,broker_timezone=cfg.mt5_server_timezone or 'UTC')
                rows.append({'index':i,'available_at':at.isoformat(),'signals':signals,'higher_context':higher,
                    'higher_tf_bias':higher['bias'],'regime':trader._market_regime(list(window.close.tail(60)))})
            if cached:
                source=Path(p['candidate_cache_source'])
                if digest(source/(lane+'_candidates.json'))!=p['candidate_cache_hashes'][lane]:raise ValueError('candidate_cache_changed')
                rows=signed(source,lane+'_candidates')['rows']
            save_signed(directory,lane+'_candidates',{'rows':rows})
            execution=frame.copy();execution['spread']=frame.spread.shift(1)
            results[lane]=replay(execution,rows,cfg,spec,ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                store,p['limits'],start=start.to_pydatetime(),end=end.to_pydatetime())
            atomic_json(directory/'progress.json',{'lane':lane,'completed':True})
        for index,entry in enumerate(entries):
            comparison={}
            for lane,state in [('causally_available_before_entry',signed(directory,'entry_memory_'+str(index))),('current_after_losses_hindsight',after)]:
                store=KnowledgeStore(str(Path(temporary)/('probe'+str(index)+lane)));store.update_learning_state(lambda _,state=state:state)
                trader=policy_trader(cfg,store)
                comparison[lane]=learning_probe(trader,deepcopy(entry['status']),pd.Timestamp(entry['at']).to_pydatetime())
            probes.append({'entry_at':entry['at'],'strategy':entry['status']['chosen']['strategy'],'comparison':comparison,
                'causal_memory_receipt':entry['causal_memory_receipt']})
        fresh=[r for r in after.get('loss_memory',{}).get('recent_outcomes',[]) if start<=pd.Timestamp(r.get('time','1970-01-01T00:00Z'))<end]
    report={'state':'completed_diagnostic_only','protocol_sha256':digest(directory/'protocol.json'),'results':results,
        'recorded_entry_probes':probes,'today_learning_outcomes':fresh,'actual_net_cash':p['actual_net_cash'],
        'common_archived_state_fields':sorted(common),'limitations':p['limitations']+[
            'The M5 lesson probe explains matching only: the entry-timing lesson adjustment and loss-pattern hard block are M1-only in current code.',
            'The generic portfolio allocator starts from its fixed research prior, not stored live allocator weights; inspect stored weight deltas separately.',
            'Generic closed-bar portfolio replay does not implement the full live online/hour/side learning path; recorded-entry probes test those components separately.',
            'No replay result is independent validation or permission to change parameters.'],
        'broker_eligible':False,'orders_sent':0,'live_state_changed':False}
    save_signed(directory,'report',report);atomic_json(directory/'progress.json',{'state':'completed_diagnostic_only'})
    print(json.dumps({'state':report['state'],'replay':{k:{f:v[f] for f in ['trades','wins','net_cash','rejections']} for k,v in results.items()},
        'learning_probes':[{k:r[k] for k in ['entry_at','strategy']}|{'would_block':{k:v['learning_would_block'] for k,v in r['comparison'].items()}} for r in probes],
        'today_learning_outcomes':len(fresh)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['capture','run','run_cached']);parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='capture':capture(args.directory.resolve())
    else:run(args.directory.resolve(),cached=args.mode=='run_cached')
