"""Freeze and compare H1/M5 SMC variants with their unchanged v5 controls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.data.top_down import TIMEFRAMES
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.smc_validation import historical, HistoricalFeed, METHOD
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.smc_validation import evaluator_for, validate, check_account
from tools.validate_current_smc import ContextCache

MODELS=('smc_event_retest_v5','smc_sweep_reclaim_v5','smc_h1_event_retest_v6','smc_h1_sweep_reclaim_v6')


def prepare(directory,source):
    cfg=load_settings();storage=Path(cfg.storage_dir).resolve()
    directory=Path(directory).resolve();source=Path(source).resolve()
    for path in (directory,source):path.relative_to(storage)
    previous=signed(source,'manifest');inputs=signed(source,'inputs')
    if previous['account_scope']!=account_scope(cfg):raise ValueError('account_scope_changed')
    if previous.get('broker_eligible') is not False:raise ValueError('research_source_required')
    for tf,expected in inputs.items():
        if digest(source/(tf+'.csv'))!=expected:raise ValueError('source_candles_changed')
    if set(inputs)!=set((*TIMEFRAMES,'M5')):raise ValueError('all_native_timeframes_required')
    now=datetime.now(timezone.utc)
    end=pd.Timestamp(now).floor('5min');holdout_start=pd.Timestamp('2026-11-24T00:00:00Z')
    if pd.Timestamp(previous['history_end'])>=holdout_start or end<=holdout_start:
        raise ValueError('separate_chronological_holdout_required')
    directory.mkdir(parents=True,exist_ok=False)
    protocol={'schema':'atlas_h1_smc_comparison_v1','declared_at':now.isoformat(),'models':list(MODELS),
        'change':'Separate H1 direction/M5 event variants; original D1/H4-direction controls retained.',
        'parameters_tuned':False,'development_start':previous['history_start'],'development_end':previous['history_end'],
        'holdout_start':holdout_start.isoformat(),'holdout_end':end.isoformat(),'method':METHOD,
        'settings':previous['settings'],'spec':previous['spec'],'limits':previous['limits'],
        'account_scope':previous['account_scope'],'deadline':signed(storage,'acceptance_plan')['deadline'],
        'source_manifest_sha256':digest(source/'manifest.json'),'source_inputs_sha256':digest(source/'inputs.json'),
        'cost_lanes':{'base':'Frozen reference fees/spread, 3 points slippage per side',
                      'stress':'Double reported spread and fees; same 3 points slippage per side'},
        'limitations':['Development candles were previously inspected; this is a bounded hypothesis test.',
                      'Later dates are a chronological holdout, not proof they were never inspected elsewhere.',
                      'Model-only bar replay omits some deployed gates and uses frozen conversion/margin/fee estimates.'],
        'broker_eligible':False,'orders_sent':0,'auto_promotion':False}
    # Declare hypotheses and dates BEFORE acquiring later-period data/results.
    save_signed(directory,'protocol',protocol)
    files=[p for folder in ('atlas_ai','tools') for p in (ROOT/folder).rglob('*.py')]
    hashes={p.relative_to(ROOT).as_posix():digest(p) for p in files}
    for name in MODELS:
        target=directory/name;target.mkdir()
        for p in files:
            out=target/'frozen_source'/p.relative_to(ROOT);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
        manifest={**previous,'model':name,'frozen_at':now.isoformat(),'source_hashes':hashes,
                  'paper_activation_requested':False,'comparison_protocol_sha256':digest(directory/'protocol.json'),
                  'diagnostic_only':True,'historical_screen_required_before_broker_consideration':True}
        save_signed(target,'manifest',manifest)
    for period in ('development','holdout'):(directory/period).mkdir()
    for tf in inputs:shutil.copyfile(source/(tf+'.csv'),directory/'development'/(tf+'.csv'))
    save_signed(directory/'development','inputs',inputs)
    with patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        try:
            check_account(cfg);feed=MarketDataFeed(cfg)
            for tf,count in [('M5',3000),('M15',1500),('H1',600),('H4',200),('D1',100)]:
                frame=feed.get_rates_for_timeframe(tf,bars=count)
                frame.to_csv(directory/'holdout'/(tf+'.csv'),index=False)
        finally:mt5.shutdown()
    save_signed(directory/'holdout','inputs',{tf:digest(directory/'holdout'/(tf+'.csv')) for tf in inputs})
    atomic_json(directory/'progress.json',{'state':'frozen_ready','broker_eligible':False})


def run(directory):
    directory=Path(directory);p=signed(directory,'protocol')
    if p['models']!=list(MODELS) or p['broker_eligible'] is not False:raise ValueError('comparison_changed')
    results={}
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for period in ('development','holdout'):
            frames={}
            for tf,expected in signed(directory/period,'inputs').items():
                path=directory/period/(tf+'.csv')
                if digest(path)!=expected:raise ValueError('input_changed')
                frames[tf]=pd.read_csv(path,float_precision='round_trip');frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
            start=pd.Timestamp(p[period+'_start']);end=pd.Timestamp(p[period+'_end'])
            if frames['M5'].time.min()>=start-pd.Timedelta(hours=7) or frames['M5'].time.max()<end-pd.Timedelta(minutes=5):
                raise ValueError('M5_warmup_or_period_coverage_missing')
            cache=ContextCache(directory/period/'contexts.sqlite',HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES}),p['settings'].get('mt5_server_timezone') or 'UTC')
            results[period]={}
            try:
                for lane in ('base','stress'):
                    lane_frames={tf:f.copy() for tf,f in frames.items()}
                    spec=BrokerSpec(**p['spec'])
                    if lane=='stress':
                        from dataclasses import replace
                        lane_frames['M5']['spread']*=2
                        spec=replace(spec,roundtrip_fee_per_lot=spec.roundtrip_fee_per_lot*2)
                    for model in MODELS:
                        validate(directory/model)
                        def progress(**kw):atomic_json(directory/'progress.json',{'period':period,'lane':lane,'model':model,**kw})
                        r=historical(lane_frames,settings_for(p,str(directory/'unused_no_writes')),spec,p['limits'],
                                     start,end,evaluator=evaluator_for({'model':model}),context_provider=cache,progress=progress)
                        save_signed(directory/period,model+'_'+lane,r)
                        results[period].setdefault(model,{})[lane]={k:r[k] for k in ('stages','counts','historical_screen_passed')}
                        save_signed(directory,'partial_report',{'results':results,'broker_eligible':False})
            finally:cache.close()
    qualified=[name for name in MODELS if all(results[period][name][lane]['historical_screen_passed']
                                             for period in results for lane in ('base','stress'))]
    report={'state':'completed_research_only','checked_at':datetime.now(timezone.utc).isoformat(),
            'protocol_sha256':digest(directory/'protocol.json'),'results':results,'historically_qualified':qualified,
            'broker_eligible':False,'orders_sent':0,'auto_promotion':False,'full_live_policy_parity':False,
            'next_requirement':'Model-specific prospective 30+30 cost-aware outcomes plus live-gate parity and operator review; no automatic activation.'}
    save_signed(directory,'report',report);atomic_json(directory/'progress.json',{'state':report['state']})
    print(json.dumps({'state':report['state'],'historically_qualified':qualified}))


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('mode',choices=['prepare','run']);a.add_argument('--directory',type=Path,required=True);a.add_argument('--source',type=Path)
    args=a.parse_args()
    if args.mode=='prepare':
        if args.source is None:a.error('--source required')
        prepare(args.directory,args.source)
    else:run(args.directory)
