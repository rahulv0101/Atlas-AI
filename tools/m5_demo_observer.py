"""Prospective M5 closed-bar demo research. No broker orders or promotion."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.learning.observation_checkpoint import observation_lock
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.policy_replay import cache_candidates
from atlas_ai.testing.m5_proposal import proposal_candidates
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for
from tools.m5_calibration_study import validate,fetch_frames,replay_lane,LANES,deny
from tools.m5_stop_research import review


def once(directory,*,now=None):
    started=time.monotonic()
    now=pd.Timestamp(now or datetime.now(timezone.utc));p=validate(directory,verify_running_source=True)
    if signed(directory,'report')['state']!='completed_research_only':return {'state':'historical_study_running'}
    params=signed(directory,'calibration');historical=signed(directory,'report')
    if (params.get('protocol_sha256')!=digest(directory/'protocol.json')
        or historical.get('calibration_sha256')!=digest(directory/'calibration.json')):
        raise ValueError('calibration_or_protocol_changed')
    deadline=pd.Timestamp(p['forward_deadline'])
    if now>=deadline:
        status={'state':'deadline_review_required','checked_at':now.isoformat(),'broker_eligible':False}
        atomic_json(directory/'forward_status.json',status);return status
    checkpoint=directory/'forward_checkpoint.json'
    if checkpoint.exists():
        state=signed(directory,'forward_checkpoint')
        if digest(directory/'forward_predictions.json')!=state['prediction_sha256']:raise ValueError('forward_prediction_receipt_changed')
    else:
        if any((directory/name).exists() for name in ['forward_predictions.json','forward_closed_M5.csv']):
            raise ValueError('unverified_forward_artifacts')
        state={'start':now.ceil('5min').isoformat(),'last_processed_index':249,'baseline':[],
               'late_candidates_discarded':0,'closed_rows':0,'closed_sha256':None,
               'protocol_sha256':digest(directory/'protocol.json'),'calibration_sha256':digest(directory/'calibration.json')}
    if state['protocol_sha256']!=digest(directory/'protocol.json') or state['calibration_sha256']!=digest(directory/'calibration.json'):
        raise ValueError('forward_checkpoint_scope_changed')
    start=pd.Timestamp(state['start'])
    from tools.smc_validation import check_account
    cfg_live=load_settings();check_account(cfg_live)
    with patch.object(mt5,'order_send',deny):
        frames=fetch_frames(cfg_live,start,now);frame=frames['M5'];times=pd.to_datetime(frame.time,utc=True)
        closed=frame[times+pd.Timedelta(minutes=5)<=now].reset_index(drop=True)
        if state['closed_rows']:
            path=directory/'forward_closed_M5.csv'
            if digest(path)!=state['closed_sha256']:raise ValueError('forward_prefix_corrupt')
            import hashlib
            prefix=closed.iloc[:state['closed_rows']].to_csv(index=False).encode('utf-8')
            if hashlib.sha256(prefix).hexdigest()!=state['closed_sha256']:raise ValueError('observed_closed_candles_revised')
            if len(closed)==state['closed_rows']:
                report=json.loads((directory/'forward_status.json').read_text())
                report['checked_at']=now.isoformat();atomic_json(directory/'forward_status.json',report)
                return report
        with tempfile.TemporaryDirectory(prefix='observer_',dir=directory) as folder:
            cfg=settings_for(p,folder)
            first=max(250,state['last_processed_index']+1,int((times+pd.Timedelta(minutes=5)>=start).to_numpy().nonzero()[0][0])
                      if (times+pd.Timedelta(minutes=5)>=start).any() else len(frame))
            extra,_,_=cache_candidates(frame,cfg,KnowledgeStore(folder),start_index=first,native_frames=frames)
            for row in extra:
                observed_at=now+pd.Timedelta(seconds=time.monotonic()-started)
                lag=(observed_at-pd.Timestamp(row['available_at'])).total_seconds()
                if lag<0 or lag>120:state['late_candidates_discarded']+=1;continue
                state['baseline'].append({**row,'observed_at':observed_at.isoformat(),'processing_lag_seconds':lag})
            state['last_processed_index']=max(state['last_processed_index'],len(frame)-2)
            # Forecasts are persisted before outcomes; future forming prices are excluded.
            proposed,_=proposal_candidates(frame,state['baseline'],p['spec']['point'])
            save_signed(directory,'forward_predictions',{'lanes':{'repaired_baseline':state['baseline'],'fixed_M5_proposal':proposed},'checked_at':now.isoformat()})
            report={'state':'collecting_prospective_demo_bars','checked_at':now.isoformat(),'start':state['start'],
                'deadline':p['forward_deadline'],'broker_eligible':False,'auto_promotion':False,'orders_sent':0,
                'observation_type':'timely_closed_candle_predictions_with_simulated_M5_paths; not tick fills or natural broker execution',
                'late_candidates_discarded':state['late_candidates_discarded'],'lanes':{}}
            # Only complete closed M5 bars may supply outcome high/low/close.
            with patch.object(mt5,'initialize',deny):
                for lane,rows in [('repaired_baseline',state['baseline']),('fixed_M5_proposal',proposed)]:
                    eligible=[row for row in rows if row['index']+1<len(closed)]
                    stats=replay_lane(closed,eligible,cfg,BrokerSpec(**p['spec']),p['limits'],params,lane,start,now)
                    trades=stats['trade_list'];stages=[]
                    for subset in [trades[:30],trades[30:60]]:
                        from tools.observe_guarded_research import stage_stats
                        value=stage_stats(subset);value['trade_list']=subset;value['review']=review(value)
                        value.pop('trade_list');stages.append(value)
                    report['lanes'][lane]={'trades':stats['trades'],'net_cash':stats['net_cash'],
                        'first_stage':stages[0],'validation_stage':stages[1],
                        'pending_exit_windows':stats['rejections'].get('incomplete_exit_window',0)+len(rows)-len(eligible),'rejections':stats['rejections']}
            closed.to_csv(directory/'forward_closed_M5.csv',index=False)
            state.update(closed_rows=len(closed),closed_sha256=digest(directory/'forward_closed_M5.csv'),
                         prediction_sha256=digest(directory/'forward_predictions.json'))
            save_signed(directory,'forward_checkpoint',state);atomic_json(directory/'forward_status.json',report)
            return report


def ensure(storage,state,*,can_start,now,start=subprocess.Popen):
    storage=Path(storage);pointer=storage/'m5_calibration_active.json'
    if not pointer.exists():return {'state':'not_configured'}
    directory=Path(json.loads(pointer.read_text())['run_dir']).resolve();directory.relative_to(storage.resolve())
    p=validate(directory)
    if not (directory/'report.json').exists() or signed(directory,'report').get('state')!='completed_research_only':return {'state':'historical_study_running'}
    if pd.Timestamp(now)>=pd.Timestamp(p['forward_deadline']):return {'state':'deadline_reached'}
    status=json.loads((directory/'forward_status.json').read_text()) if (directory/'forward_status.json').exists() else {}
    if status.get('state') in {'blocked_review_required','deadline_review_required'}:return {'state':status['state']}
    try:
        with observation_lock(directory/'forward.lock'):pass
    except RuntimeError:return {'state':'existing_M5_demo_observer_running'}
    if not can_start:return {'state':'waiting_for_backend_and_operator'}
    attempts=state.setdefault('m5_demo_starts',[]);attempts[:]=[t for t in attempts if now.timestamp()-t<3600]
    if len(attempts)>=3:return {'state':'restart_budget_exhausted'}
    with (directory/'forward.stdout.log').open('a') as out,(directory/'forward.stderr.log').open('a') as err:
        child=start([sys.executable,str(directory/'frozen_source/tools/m5_demo_observer.py'),'watch','--run-dir',str(directory)],
            cwd=Path(p['project_root']),stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    attempts.append(now.timestamp());return {'state':'M5_demo_observer_started','pid':child.pid}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['once','watch']);parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    with observation_lock(args.run_dir/'forward.lock'):
        while True:
            try:r=once(args.run_dir)
            except Exception as exc:
                r={'state':'blocked_review_required','error':type(exc).__name__,'reason':str(exc),'checked_at':datetime.now(timezone.utc).isoformat(),'broker_eligible':False}
                atomic_json(args.run_dir/'forward_status.json',r);raise
            if args.mode=='once' or r['state']=='deadline_review_required':break
            time.sleep(30)
