"""Rerun normal orders after the EMA preference fix against the frozen prior control."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import replay
from tools.cost_aware_strategy_audit import prepare_frame
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny

ROOT=Path(__file__).resolve().parents[1]


def groups(stats):
    rows=defaultdict(list)
    for t in stats['trade_list']: rows[t['strategy']].append(t)
    return {name:{'trades':len(ts),'wins':sum(t['net_cash']>0 for t in ts),
                  'net_cash':sum(t['net_cash'] for t in ts)} for name,ts in rows.items()}


def run():
    baseline=ROOT/'storage/inverted_orders_once_20261124T193044Z'
    before_protocol,before_report=signed(baseline,'protocol'),signed(baseline,'report')
    if before_report['protocol_sha256']!=digest(baseline/'protocol.json'):
        raise ValueError('baseline_receipt_changed')
    # All shared replay, quote, H1 and risk rules remain the same. The trader
    # also gained selection diagnostics, which this replay does not use.
    for name in ('atlas_ai/testing/policy_replay.py','atlas_ai/testing/historical_broker.py',
                 'atlas_ai/testing/historical_decision.py','atlas_ai/data/top_down.py',
                 'atlas_ai/risk/risk_manager.py'):
        if digest(ROOT/name)!=before_protocol['source_hashes'][name]:
            raise ValueError('non_allocator_replay_rule_changed:'+name)
    source=ROOT/'storage/h1_m5_retest_20261124T142609Z'
    if digest(source/'discovery_candidates.json')!=before_protocol['candidates_sha256']:
        raise ValueError('candidate_stream_changed')
    rows=signed(source,'discovery_candidates')['rows']
    path=ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5/M5.csv'
    if digest(path)!=before_protocol['candles_sha256']: raise ValueError('candles_changed')
    frame=prepare_frame(pd.read_csv(path));frame['time']=pd.to_datetime(frame.time,utc=True)
    execution=frame.copy();execution['spread']=frame.spread.shift(1)
    output=ROOT/'storage'/('allocator_fix_backtest_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    protocol={**{k:before_protocol[k] for k in ('settings','spec','limits','period_utc','costs','candles_sha256','candidates_sha256')},
        'change':'Remove EMA fixed 1.08 bonus and inventory-order tie preference; use current allocator. Normal orders only.',
        'control':'Saved, signed normal lane of the previous identical-input experiment; not re-executed this run.',
        'control_report_sha256':digest(baseline/'report.json'),'source_hashes':{},
        'limitations':before_protocol['limitations']+[
            'Fresh neutral allocator priors in both lanes, not restored current live learning history.',
            'Tie handling and exploration RNG consumption changed deliberately; this comparison measures their combined effect with bonus removal.',
            'A retrospective diagnostic, not profitability validation or full live parity.'],
        'orders_sent':0,'live_policy_changed':False,'inverted_orders':False}
    for folder in ('atlas_ai','tools'):
        for p in (ROOT/folder).rglob('*.py'):
            target=output/'frozen_source'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target);protocol['source_hashes'][p.relative_to(ROOT).as_posix()]=digest(p)
    save_signed(output,'protocol',protocol)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory() as temp:
        cfg=settings_for(protocol,temp)
        atomic_json(output/'progress.json',{'state':'running','lane':'current_normal'})
        current=replay(execution,deepcopy(rows),cfg,BrokerSpec(**protocol['spec']),
            ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),KnowledgeStore(temp),protocol['limits'],
            start=pd.Timestamp(protocol['period_utc'][0]).to_pydatetime(),end=pd.Timestamp(protocol['period_utc'][1]).to_pydatetime(),
            audit=lambda row:atomic_json(output/'progress.json',{'state':'running','bar':row['index']}) if row['index']%500==0 else None)
    results={'previous_normal':before_report['results']['normal'],'after_allocator_fix':current}
    for stats in results.values():
        stats['win_rate']=stats['wins']/stats['trades'] if stats['trades'] else None
        stats['by_strategy']=groups(stats)
        stats['ambiguous_stop_first']=sum(t['ambiguous_stop_first'] for t in stats['trade_list'])
    report={'state':'completed_normal_backtest','results':results,'period_utc':protocol['period_utc'],
        'protocol_sha256':digest(output/'protocol.json'),'control_report_sha256':protocol['control_report_sha256'],
        'limitations':protocol['limitations'],'orders_sent':0,'live_policy_changed':False,'inverted_orders':False,'broker_eligible':False}
    save_signed(output,'report',report)
    portable={**report,'results':{name:{k:v for k,v in stats.items() if k!='trade_list'} for name,stats in results.items()}}
    (ROOT/'docs/ALLOCATOR_FIX_BACKTEST_20261125.json').write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    atomic_json(output/'progress.json',{'state':report['state']})
    print(json.dumps(portable),flush=True)


if __name__=='__main__':run()
