"""Timely frozen entry-design forecasts on demo quotes. No orders or activation."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.learning.observation_checkpoint import account_scope,observation_lock
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.cost_aware_strategy_audit import prepare_frame
from tools.test_complete_retest_setup import generate as retest_generate
from tools.sweep_reclaim_research import generate as sweep_generate


def merge_closed(saved,incoming):
    """Append new bars only; reject revisions/backfills that could alter past inputs."""
    if not saved:return incoming
    by_time={r['time']:r for r in saved};first,last=saved[0]['time'],saved[-1]['time']
    for row in incoming:
        at=row['time']
        if at<first:continue
        if at in by_time and row!=by_time[at]:raise ValueError('previous_closed_bar_revised')
        if first<=at<=last and at not in by_time:raise ValueError('past_gap_backfilled')
        if at>last:by_time[at]=row
    return [by_time[k] for k in sorted(by_time)]


def timely(available,observed,start):
    return pd.Timestamp(available)>=pd.Timestamp(start) and 0<=(pd.Timestamp(observed)-pd.Timestamp(available)).total_seconds()<=120


def proven_closed_bars(frame,minutes,now):
    raw=frame.copy();raw['time']=pd.to_datetime(raw.time,utc=True)
    if raw.empty or raw.time.duplicated().any() or not raw.time.is_monotonic_increasing:
        raise ValueError('ordered_native_bars_required')
    # MT5's final native row can remain mutable after its nominal close if
    # the next bar has not arrived. Wall-clock age alone is insufficient.
    preceding=raw.iloc[:-1]
    return preceding[preceding.time+pd.Timedelta(minutes=minutes)<=pd.Timestamp(now)].copy()


def initialize(history):
    cfg=load_settings();storage=Path(cfg.storage_dir).resolve();pointer=storage/'entry_forecast_active.json'
    if pointer.exists():
        directory=Path(json.loads(pointer.read_text())['run_dir']).resolve();directory.relative_to(storage)
        plan=signed(directory,'plan')
        if plan['historical_report_sha256']!=digest(history/'report.json') or plan['account_scope']!=account_scope(cfg):
            raise ValueError('existing_registration_requires_review_no_reset')
        return directory
    report=signed(history,'report');p=signed(history,'protocol')
    if report['protocol_sha256']!=digest(history/'protocol.json'):raise ValueError('historical_receipt_changed')
    now=datetime.now(timezone.utc);directory=storage/('entry_forecast_'+now.strftime('%Y%m%dT%H%M%SZ'));directory.mkdir()
    plan={'schema':'atlas_entry_forecast_v1','registered_at':now.isoformat(),'start':pd.Timestamp(now).ceil('5min').isoformat(),
        'deadline':(now+timedelta(days=14)).isoformat(),'account_scope':account_scope(cfg),
        'broker_timezone':cfg.mt5_server_timezone,'settings':p['settings'],'spec':p['spec'],'limits':p['limits'],
        'historical_report_sha256':digest(history/'report.json'),'historical_qualified':report['historical_qualified'],
        'models':['unchanged_retest','sweep_reclaim'],'cost_lanes':{'base':{'spread_multiplier':1,'slippage_points':3},'stress':{'spread_multiplier':2,'slippage_points':6}},
        'purpose':'Diagnostic comparison of frozen failed/unqualified hypotheses; not a qualification-stage promotion.',
        'rules':'Forecasts must be saved within 120 seconds after close and after registration. Never backfill missed forecasts.',
        'source_hashes':{str(f.relative_to(ROOT)):digest(f) for folder in ('atlas_ai','tools') for f in (ROOT/folder).rglob('*.py')},
        'broker_eligible':False,'auto_promotion':False,'orders_sent':0}
    save_signed(directory,'plan',plan)
    save_signed(directory,'checkpoint',{'last_available':None,'bars_evaluated':0,'late_discarded':0,
        'forecasts':{'unchanged_retest':[],'sweep_reclaim':[]},'frame_hash':None,'plan_sha256':digest(directory/'plan.json')})
    atomic_json(pointer,{'run_dir':str(directory)})
    return directory


def once(directory,*,clock=None):
    clock=clock or (lambda:pd.Timestamp.now(tz='UTC'))
    plan=signed(directory,'plan');state=signed(directory,'checkpoint');now=pd.Timestamp(clock())
    if plan.get('schema')!='atlas_entry_forecast_v1' or plan.get('broker_eligible') is not False or plan.get('auto_promotion') is not False or plan.get('orders_sent')!=0:
        raise ValueError('diagnostic_boundary_changed')
    if state['plan_sha256']!=digest(directory/'plan.json'):raise ValueError('plan_changed')
    if now>=pd.Timestamp(plan['deadline']):return {'state':'deadline_review_required','checked_at':now.isoformat(),'orders_sent':0,'broker_eligible':False}
    for name,expected in plan['source_hashes'].items():
        if digest(ROOT/name)!=expected:raise ValueError('frozen_source_changed')
    cfg=load_settings()
    if account_scope(cfg)!=plan['account_scope'] or cfg.mt5_server_timezone!=plan['broker_timezone']:raise ValueError('account_or_clock_changed')
    saved={'M5':[],'H1':[]}
    if state['frame_hash']:
        if digest(directory/'closed_frames.json')!=state['frame_hash']:raise ValueError('saved_frames_changed')
        saved=json.loads((directory/'closed_frames.json').read_text())
    with patch.object(mt5,'order_send',deny),patch.object(mt5,'login',deny):
        try:
            feed=MarketDataFeed(cfg);feed._ensure_initialized();account=mt5.account_info()
            if not account or account.login!=cfg.hfm_login or account.server!=cfg.hfm_server or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:raise ValueError('matching_demo_required')
            incoming={tf:feed.get_rates_for_timeframe(tf,bars=count) for tf,count in [('M5',600),('H1',120)]}
        finally:mt5.shutdown()
    frames={}
    for tf,minutes in [('M5',5),('H1',60)]:
        closed=proven_closed_bars(incoming[tf],minutes,now)
        records=json.loads(closed.to_json(orient='records',date_format='iso',double_precision=15))
        saved[tf]=merge_closed(saved[tf],records)
        frames[tf]=prepare_frame(pd.DataFrame(saved[tf]));frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
    available=frames['M5'].time.iloc[-1]+pd.Timedelta(minutes=5)
    if state['last_available']!=available.isoformat() and available>=pd.Timestamp(plan['start']):
        # Only its timestamp is used to establish that the next bar exists.
        forming=incoming['M5'].copy();forming['time']=pd.to_datetime(forming.time,utc=True)
        forming=forming[forming.time==available]
        prediction_frame=pd.concat([frames['M5'],forming],ignore_index=True)
        if not forming.empty:
            previous=pd.Timestamp(state['last_available']) if state['last_available'] else pd.Timestamp(plan['start'])-pd.Timedelta(minutes=5)
            skipped=max(0,int((available-previous).total_seconds()//300)-1)
            state['missed_closed_bars']=state.get('missed_closed_bars',0)+skipped
            with tempfile.TemporaryDirectory() as temp:
                frozen_cfg=settings_for(plan,temp);generated={}
                for model,generator in [('unchanged_retest',retest_generate),('sweep_reclaim',sweep_generate)]:
                    rows,_=generator(prediction_frame,frames['H1'],frozen_cfg,available,available+pd.Timedelta(seconds=1),lambda **kw:None)
                    generated[model]=rows
                observed=pd.Timestamp(clock())
                if timely(available,observed,plan['start']):
                    for model,rows in generated.items():
                        state['forecasts'][model].extend({**row,'observed_at':observed.isoformat()} for row in rows)
                else:state['late_discarded']+=1
            state['bars_evaluated']+=1;state['last_available']=available.isoformat()
    # Forecasts are recorded before future path evaluation; this collector does
    # not turn paper forecasts into broker fills or qualification evidence.
    atomic_json(directory/'closed_frames.json',saved);state['frame_hash']=digest(directory/'closed_frames.json')
    save_signed(directory,'checkpoint',state)
    data_fresh=0<=(pd.Timestamp(clock())-available).total_seconds()<=120
    return {'state':'collecting_diagnostic_forecasts' if data_fresh else 'waiting_for_fresh_demo_bars','data_fresh':data_fresh,'checked_at':pd.Timestamp(clock()).isoformat(),
        'start':plan['start'],'deadline':plan['deadline'],'bars_evaluated':state['bars_evaluated'],'late_discarded':state['late_discarded'],
        'missed_closed_bars':state.get('missed_closed_bars',0),'closure_basis':'following_native_bar_present_and_close_time_passed',
        'forecasts':{k:len(v) for k,v in state['forecasts'].items()},'latest_closed_M5':frames['M5'].time.iloc[-1].isoformat(),
        'historical_qualified':plan['historical_qualified'],'qualification_cases':0,'natural_broker_cycles':0,
        'note':'Timed predictions on fresh demo data; outcomes require later frozen cost-aware review. Historical failure remains blocked.',
        'orders_sent':0,'broker_eligible':False,'auto_promotion':False}


def ensure(storage,state,*,can_start,now,start=subprocess.Popen):
    storage=Path(storage).resolve();pointer=storage/'entry_forecast_active.json'
    if not pointer.exists():return {'state':'not_configured'}
    directory=Path(json.loads(pointer.read_text())['run_dir']).resolve();directory.relative_to(storage)
    plan=signed(directory,'plan')
    if now>=datetime.fromisoformat(plan['deadline']):return {'state':'deadline_reached'}
    status=json.loads((directory/'status.json').read_text()) if (directory/'status.json').exists() else {}
    # Registered research runs use their own immutable source, so unrelated live
    # repairs cannot change their model or halt evidence collection.
    frozen=directory/'frozen_source'
    recover_source_only=(status.get('state')=='blocked_evidence_review_required'
                         and status.get('reason')=='frozen_source_changed')
    if status.get('state')=='blocked_evidence_review_required' and not recover_source_only:
        return {'state':status['state']}
    try:
        with observation_lock(directory/'observer.lock'):pass
    except RuntimeError:return {'state':'existing_entry_forecast_observer_running'}
    if not can_start:return {'state':'waiting_for_backend_and_operator'}
    for name,expected in plan['source_hashes'].items():
        source=(frozen/name).resolve()
        source.relative_to(frozen.resolve())
        if not source.is_file() or digest(source)!=expected:
            return {'state':'blocked_evidence_review_required','reason':'registered_source_snapshot_changed'}
    attempts=state.setdefault('entry_forecast_starts',[]);attempts[:]=[t for t in attempts if now.timestamp()-t<3600]
    if len(attempts)>=3:return {'state':'restart_budget_exhausted_review_required'}
    with (directory/'stdout.log').open('a') as out,(directory/'stderr.log').open('a') as err:
        if recover_source_only:
            atomic_json(directory/('source_isolation_resume_'+now.strftime('%Y%m%dT%H%M%SZ')+'.json'),
                        {'previous_status':status,'plan_sha256':digest(directory/'plan.json'),
                         'reason':'Resume identical registered code from verified source snapshot; no plan or evidence reset.'})
        child=start([sys.executable,str(frozen/'tools/entry_forecast_observer.py'),'watch','--run-dir',str(directory)],cwd=ROOT,
                    stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    attempts.append(now.timestamp());return {'state':'entry_forecast_observer_started','pid':child.pid,'orders_sent':0,'broker_eligible':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['init','once','watch'])
    parser.add_argument('--historical',type=Path);parser.add_argument('--run-dir',type=Path);a=parser.parse_args()
    if a.mode=='init':
        if a.historical is None:parser.error('--historical required')
        print(json.dumps({'state':'registered','run_dir':str(initialize(a.historical)),'orders_sent':0}));return
    if a.run_dir is None:parser.error('--run-dir required')
    with observation_lock(a.run_dir/'observer.lock'):
        while True:
            try:result=once(a.run_dir)
            except Exception as exc:result={'state':'blocked_evidence_review_required','error':type(exc).__name__,'reason':str(exc),'orders_sent':0,'broker_eligible':False}
            atomic_json(a.run_dir/'status.json',result)
            if a.mode=='once' or result['state'] in {'deadline_review_required','blocked_evidence_review_required'}:return
            time.sleep(30)


if __name__=='__main__':main()
