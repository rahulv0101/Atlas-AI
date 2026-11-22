"""Matched research-only follow-through comparison; no broker execution route."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import normalize_rates
from atlas_ai.data.top_down import TIMEFRAMES, collect
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.strategies.smc_entry_models import sweep_reclaim
from atlas_ai.testing.smc_followthrough import evaluate
from atlas_ai.testing.smc_validation import historical, HistoricalFeed
from atlas_ai.testing.historical_broker import BrokerSpec
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.validate_current_smc import ContextCache


def capture(directory):
    p=signed(directory,'protocol')
    if p['model_sha256']!=digest(ROOT/'atlas_ai/testing/smc_followthrough.py'):raise ValueError('model_changed')
    # Freeze all executable sources before reading any later test candles.
    hashes={}
    for folder in ('atlas_ai','tools'):
        for source in (ROOT/folder).rglob('*.py'):
            relative=source.relative_to(ROOT);out=directory/'frozen_source'/relative
            out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,out)
            hashes[relative.as_posix()]=digest(source)
    save_signed(directory,'source_receipt',{'hashes':hashes,'protocol_sha256':digest(directory/'protocol.json')})
    cfg=load_settings()
    reference=signed(ROOT/'storage/smc_validation_review_20261120_v2/smc_sweep_reclaim_v5','manifest')
    if account_scope(cfg)!=reference['account_scope']:raise ValueError('account_scope_changed')
    target=directory/'separate_inputs';target.mkdir(exist_ok=False)
    hashes={}
    with patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        if not mt5.initialize(path=cfg.hfm_terminal_path):raise ValueError('attach_failed')
        account=mt5.account_info()
        if account is None or account.login!=cfg.hfm_login or account.server!=cfg.hfm_server or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise ValueError('matching_demo_required')
        for tf,n in [('D1',90),('H4',180),('H1',300),('M15',1000),('M5',1500)]:
            rates=mt5.copy_rates_from_pos(cfg.symbol,getattr(mt5,'TIMEFRAME_'+tf),0,n)
            if rates is None or len(rates)<60:raise ValueError('insufficient_rates:'+tf)
            frame=normalize_rates(rates,cfg);path=target/(tf+'.csv');frame.to_csv(path,index=False);hashes[tf]=digest(path)
    save_signed(target,'inputs',hashes)
    save_signed(target,'window',{'start':p['separate_test_start'],'end':datetime.now(timezone.utc).isoformat(),
        'captured_after_declaration':True,'not_prospective':True,'broker_eligible':False,'orders_sent':0})
    print('Frozen sources and separate later native candles captured.',flush=True)


def run(directory):
    p=signed(directory,'protocol');receipt=signed(directory,'source_receipt')
    if receipt['protocol_sha256']!=digest(directory/'protocol.json'):raise ValueError('protocol_changed')
    for name,h in receipt['hashes'].items():
        if digest(ROOT/name)!=h:raise ValueError('source_changed:'+name)
    # Frozen ROOT is nested below the real storage; locate inputs from directory.
    project=directory.resolve().parent.parent
    source=project/'storage/smc_validation_review_20261120_v2/smc_sweep_reclaim_v5'
    m=signed(source,'manifest')
    if digest(source/'manifest.json')!=p['baseline_manifest_sha256']:raise ValueError('baseline_changed')
    results={}
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for period,folder,bounds in [('reused_development',source,(m['history_start'],m['history_end'])),
                ('separate_later',directory/'separate_inputs',tuple(signed(directory/'separate_inputs','window')[k] for k in ('start','end')))]:
            frames={}
            for tf,h in signed(folder,'inputs').items():
                path=folder/(tf+'.csv')
                if digest(path)!=h:raise ValueError('input_changed:'+tf)
                frames[tf]=pd.read_csv(path);frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
            feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES})
            cache=ContextCache(directory/(period+'.sqlite'),feed,m['settings']['mt5_server_timezone'] or 'UTC')
            # Reuse only exact-time, previously directly checked historical contexts.
            prior=sqlite3.connect(project/'storage/smc_validation_review_20261120_v2/contexts.sqlite') if period=='reused_development' else None
            def context(now):
                row=prior.execute('select value from context where at=?',(now.isoformat(),)).fetchone() if prior else None
                return json.loads(row[0]) if row else cache(now)
            results[period]={}
            try:
                for lane,evaluator in [('baseline',sweep_reclaim),('two_closed_candles',evaluate)]:
                    def progress(**kw):atomic_json(directory/'progress.json',{'period':period,'lane':lane,**kw})
                    result=historical(frames,settings_for(m,str(directory/'isolated')),BrokerSpec(**m['spec']),m['limits'],
                        pd.Timestamp(bounds[0]),pd.Timestamp(bounds[1]),evaluator=evaluator,context_provider=context,progress=progress)
                    save_signed(directory,period+'_'+lane,result)
                    results[period][lane]={k:result[k] for k in ('stages','counts','historical_screen_passed')}
                    save_signed(directory,'partial_report',{'results':results,'broker_eligible':False})
            finally:
                cache.close()
                if prior:prior.close()
    report={'state':'completed_research_only','protocol_sha256':digest(directory/'protocol.json'),'results':results,
        'broker_eligible':False,'orders_sent':0,'auto_promotion':False,'live_policy_changed':False,
        'limitations':['Historical development data previously inspected. Later test is separate but retrospective and short.',
            'Costs are frozen approximations; no natural fills or full historical live-gate parity.',
            'A failed or undersampled result cannot qualify; no tuning or automatic promotion.']}
    save_signed(directory,'report',report)
    atomic_json(directory/'progress.json',{'phase':'completed','broker_eligible':False,'orders_sent':0})
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['capture','run']);parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();directory=args.directory.resolve()
    (capture if args.mode=='capture' else run)(directory)
