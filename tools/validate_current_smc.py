"""Declared six-model SMC review with reused verified candles and no broker route."""
import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import shutil
import sqlite3
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.smc_validation import METHOD,HistoricalFeed,historical
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.smc_validation import evaluator_for,validate

MODELS=('smc_composite_v1','smc_pullback_v2','smc_retest_v3','smc_framework_v4','smc_event_retest_v5','smc_sweep_reclaim_v5')


def prepare(directory,source,cost_source):
    settings=load_settings();storage=Path(settings.storage_dir).resolve()
    directory=directory.resolve();source=source.resolve();cost_source=cost_source.resolve()
    for path in (directory,source,cost_source):path.relative_to(storage)
    old=signed(source,'manifest');inputs=signed(source,'inputs');cost=signed(cost_source,'protocol')
    if old['account_scope']!=account_scope(settings):raise ValueError('account_scope_changed')
    if cost.get('broker_eligible') is not False or cost.get('orders_sent')!=0:raise ValueError('research_cost_reference_required')
    for tf,expected in inputs.items():
        if digest(source/(tf+'.csv'))!=expected:raise ValueError('source_candles_changed')
    if set(inputs)!=set((*TIMEFRAMES,'M5')):raise ValueError('native_timeframes_required')
    now=datetime.now(timezone.utc)
    acceptance_deadline=datetime.fromisoformat(signed(storage,'acceptance_plan')['deadline'])
    deadline=min(now+timedelta(days=21),acceptance_deadline)
    if deadline<=now:raise ValueError('acceptance_window_expired')
    directory.mkdir(parents=True,exist_ok=False)
    cfg=replace(settings,backtest_initial_balance=100000.)
    common={'schema':'atlas_smc_validation_v1','method':METHOD,'frozen_at':now.isoformat(),
        'history_reused_after_prior_diagnostic':True,'matched_frozen_cost_reference':True,
        'history_start':old['history_start'],'history_end':old['history_end'],
        'settings':safe_settings(cfg),'spec':cost['spec'],'limits':cost['limits'],
        'cost_evidence':{'reference_protocol_sha256':digest(cost_source/'protocol.json'),
            'interpretation':'Frozen November 18 research conversion, margin and fees; not newly measured fills or future calibrated costs.'},
        'account_scope':account_scope(settings),'broker_eligible':False,'orders_sent':0,
        'deadline':deadline.isoformat()}
    save_signed(directory,'protocol',{'schema':'current_smc_validation_review_v1','declared_at':now.isoformat(),
        'models':list(MODELS),'forward_model_declared_before_results':'smc_framework_v4',
        'virtual_capital':100000.,'capital_rule':'Fixed R100k demo-representative scenario; live settings unchanged.',
        'history_reused_not_blind':True,'source_inputs_sha256':digest(source/'inputs.json'),
        'review_criteria':METHOD,'parameters_tuned':False,'broker_eligible':False,'auto_promotion':False})
    files=[p for folder in ['atlas_ai','tools'] for p in (ROOT/folder).rglob('*.py')]
    hashes={p.relative_to(ROOT).as_posix():digest(p) for p in files}
    for name in MODELS:
        target=directory/name;target.mkdir()
        for p in files:
            output=target/'frozen_source'/p.relative_to(ROOT);output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,output)
        manifest={**common,'model':name,'paper_activation_requested':name=='smc_framework_v4','source_hashes':hashes}
        save_signed(target,'manifest',manifest)
        for tf in inputs:shutil.copyfile(source/(tf+'.csv'),target/(tf+'.csv'))
        save_signed(target,'inputs',inputs)
    atomic_json(directory/'progress.json',{'phase':'frozen_ready','checked_at':now.isoformat()})


class ContextCache:
    def __init__(self,path,feed,timezone):
        self.db=sqlite3.connect(path);self.db.execute('create table if not exists context (at text primary key, value text)')
        from atlas_ai.data.top_down import MINUTES
        for tf,frame in feed.frames.items():
            ts=pd.to_datetime(frame.time,utc=True)
            if not ts.eq(ts.dt.floor('15min')).all():raise ValueError('off_grid_HTF_candles')
        self.feed=feed;self.timezone=timezone;self.writes=0;self.base=None;self.base_at=None;self.equivalence_checks=0
    def __call__(self,now):
        key=now.isoformat();row=self.db.execute('select value from context where at=?',(key,)).fetchone()
        if row:return json.loads(row[0])
        self.feed.now=now
        # Closed HTF bars cannot change inside a quarter-hour bucket. Refresh
        # their clocks exactly, and fall back at any freshness boundary.
        delta=(now-self.base_at).total_seconds() if self.base_at is not None else -1
        reuse=self.base is not None and delta>=0 and now.floor('15min')==self.base_at.floor('15min')
        if reuse:
            from atlas_ai.data.top_down import MINUTES
            value=deepcopy(self.base);value['evaluated_at']=key
            for tf,evidence in value['evidence'].items():
                if evidence.get('status')=='available':
                    evidence['freshness_age_seconds']+=delta
                    if evidence['freshness_age_seconds']>MINUTES[tf]*120:reuse=False
        if not reuse:
            value=collect(self.feed,now,broker_timezone=self.timezone)
            self.base=deepcopy(value);self.base_at=now
        if self.writes%101==0:
            direct=collect(self.feed,now,broker_timezone=self.timezone)
            if value!=direct:raise ValueError('cached_context_not_equivalent_to_direct_collection')
            self.equivalence_checks+=1
        self.db.execute('insert into context values (?,?)',(key,json.dumps(value,allow_nan=False)));self.writes+=1
        if self.writes%200==0:self.db.commit()
        return value
    def close(self):self.db.commit();self.db.close()


def run(directory):
    directory=directory.resolve();protocol=signed(directory,'protocol')
    if protocol['models']!=list(MODELS) or protocol['broker_eligible'] is not False:raise ValueError('review_boundary_changed')
    first=validate(directory/MODELS[0]);inputs=signed(directory/MODELS[0],'inputs');frames={}
    for tf,expected in inputs.items():
        path=directory/MODELS[0]/(tf+'.csv')
        if digest(path)!=expected:raise ValueError('input_changed')
        frames[tf]=pd.read_csv(path);frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
    feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES})
    cache_path=directory/'contexts.sqlite'
    if cache_path.exists():raise FileExistsError('new_review_cache_required')
    cache=ContextCache(cache_path,feed,first['settings'].get('mt5_server_timezone') or 'UTC');results={}
    try:
        with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
            for name in MODELS:
                m=validate(directory/name)
                for key in ['settings','spec','limits','history_start','history_end','source_hashes']:
                    if m[key]!=first[key]:raise ValueError('unmatched_models:'+key)
                if signed(directory/name,'inputs')!=inputs:raise ValueError('unmatched_inputs')
                def progress(**kw):atomic_json(directory/'progress.json',{'phase':'historical_review','model':name,'checked_at':datetime.now(timezone.utc).isoformat(),**kw})
                result=historical(frames,settings_for(m,str(directory/name/'isolated_policy')),BrokerSpec(**m['spec']),m['limits'],
                    pd.Timestamp(m['history_start']),pd.Timestamp(m['history_end']),progress=progress,
                    evaluator=evaluator_for(m),context_provider=cache)
                result['manifest_sha256']=digest(directory/name/'manifest.json');save_signed(directory/name,'history',result)
                results[name]={'stages':result['stages'],'counts':result['counts'],'historical_screen_passed':result['historical_screen_passed']}
                save_signed(directory,'partial_report',{'models':results,'broker_eligible':False})
    finally:cache.close()
    report={'state':'completed_historical_research_review','checked_at':datetime.now(timezone.utc).isoformat(),
        'protocol_sha256':digest(directory/'protocol.json'),'models':results,'history_reused_not_blind':True,
        'historically_qualified':[k for k,v in results.items() if v['historical_screen_passed']],
        'broker_eligible':False,'auto_promotion':False,'full_live_policy_parity':False,'direct_context_equivalence_checks':cache.equivalence_checks,
        'limitations':['Native history already inspected; split results can reject but do not prove a new independent edge.',
            'Frozen conversion/margin/fee approximation, bar outcomes and missing historical full live-gate evidence.',
            'Prospective 30+30 model-specific cases remain required; candidates cannot be pooled across models.']}
    save_signed(directory,'report',report);atomic_json(directory/'progress.json',{'phase':'completed','checked_at':report['checked_at']})
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','run']);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--cost-source',type=Path);a=p.parse_args()
    if a.mode=='prepare':
        if a.source is None or a.cost_source is None:p.error('source and cost-source required')
        prepare(a.directory,a.source,a.cost_source)
    else:
        try:run(a.directory)
        except Exception as exc:
            atomic_json(a.directory/'progress.json',{'phase':'blocked_review_required','reason':str(exc),'broker_eligible':False})
            raise
