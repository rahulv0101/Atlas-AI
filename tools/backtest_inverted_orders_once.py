"""One requested diagnostic: reverse simulated orders after normal candidate gates."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant, simulate
from atlas_ai.testing.policy_replay import replay
from tools.cost_aware_strategy_audit import prepare_frame
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny

ROOT = Path(__file__).resolve().parents[1]


def inverted_simulation(*args, **kwargs):
    # Preserve caller-owned detection evidence; only the simulated order changes.
    frame, index, signal, *rest = args
    if signal.side not in ('buy', 'sell'): raise ValueError('directional_signal_required')
    opposite = replace(signal, side='sell' if signal.side == 'buy' else 'buy')
    trade = simulate(frame, index, opposite, *rest, **kwargs)
    return {**trade, 'detected_side': signal.side, 'executed_side': opposite.side}


def run():
    source = ROOT/'storage/h1_m5_retest_20261124T142609Z'
    prior, receipt = signed(source,'protocol'), signed(source,'prediction_receipt')
    if receipt['protocol_sha256'] != digest(source/'protocol.json'): raise ValueError('source_protocol_changed')
    if receipt['candidates']['discovery'] != digest(source/'discovery_candidates.json'): raise ValueError('candidate_stream_changed')
    rows = signed(source,'discovery_candidates')['rows']
    path = ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5/M5.csv'
    if digest(path) != receipt['native_inputs']['discovery']['M5']: raise ValueError('candles_changed')
    frame = prepare_frame(pd.read_csv(path)); frame['time'] = pd.to_datetime(frame.time,utc=True)
    execution = frame.copy(); execution['spread'] = frame.spread.shift(1)
    output = ROOT/'storage'/('inverted_orders_once_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    files = [Path(__file__), ROOT/'atlas_ai/testing/policy_replay.py', ROOT/'atlas_ai/testing/historical_broker.py',
             ROOT/'atlas_ai/testing/historical_decision.py', ROOT/'atlas_ai/trader.py', ROOT/'atlas_ai/data/top_down.py',
             ROOT/'atlas_ai/learning/online_allocator.py', ROOT/'atlas_ai/risk/risk_manager.py']
    for p in files:
        target = output/'frozen_source'/p.relative_to(ROOT); target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,target)
    protocol = {'settings': prior['settings'], 'spec': prior['spec'], 'limits': prior['limits'],
        'period_utc': prior['periods']['discovery'], 'comparison': 'normal_orders_vs_inverted_orders_after_normal_gates',
        'signal_inversion': 'BUY -> executed SELL; SELL -> executed BUY; same SL/TP point distances, not swapped',
        'direction_gate_exception': 'Diagnostic inverted orders intentionally oppose the detected side and its H1 confirmation. All gates evaluate the original candidate; only simulated submission is reversed.',
        'costs': 'Same frozen broker conversion/fees, lagged closed spread, 3 points slippage per side.',
        'portfolio': 'Each lane evolves its own balances, holds, allocator and loss counters from its own simulated outcomes; trade identities/counts may diverge.',
        'source_hashes': {p.relative_to(ROOT).as_posix(): digest(p) for p in files},
        'candidates_sha256': digest(source/'discovery_candidates.json'), 'candles_sha256': digest(path),
        'baseline_source_receipt_sha256': digest(source/'prediction_receipt.json'),
        'parameters_frozen_before_outcomes': True, 'orders_sent': 0, 'live_policy_changed': False,
        'limitations': ['Previously inspected historical data; one diagnostic run, not strategy qualification.',
            'Archived signal stream with current H1 confirmation; partial live-policy replay, missing intrabar/visual/macro/adaptive/execution evidence.',
            'Stop-first M5 OHLC handling can make both original and reversed directions lose when both barriers are touched. Outcomes are not simple sign inverses.',
            'Current funded account balance is not used to inflate the historic virtual capital. No deposit is simulated as earnings.',
            'No structural-retest overlay, live configuration change, learning write or automatic activation.']}
    save_signed(output,'protocol',protocol)
    result = {}
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for lane in ('normal','inverted'):
            atomic_json(output/'progress.json',{'lane':lane,'state':'running'})
            with tempfile.TemporaryDirectory() as temp:
                cfg = settings_for(protocol,temp)
                def run_lane():
                    return replay(execution,deepcopy(rows),cfg,BrokerSpec(**protocol['spec']),
                        ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),KnowledgeStore(temp),protocol['limits'],
                        start=pd.Timestamp(protocol['period_utc'][0]).to_pydatetime(),
                        end=pd.Timestamp(protocol['period_utc'][1]).to_pydatetime(),
                        audit=lambda row: atomic_json(output/'progress.json',{'lane':lane,'bar':row['index'],'state':'running'})
                              if row['index']%500==0 else None)
                if lane == 'normal': stats = run_lane()
                else:
                    with patch('atlas_ai.testing.policy_replay.simulate',inverted_simulation): stats = run_lane()
            for trade in stats['trade_list']:
                trade['detected_side'] = trade.get('detected_side',trade['side'])
                trade['executed_side'] = trade.get('executed_side',trade['side'])
                trade['side'] = trade['executed_side']
            stats['win_rate'] = stats['wins']/stats['trades'] if stats['trades'] else None
            stats['ambiguous_stop_first'] = sum(t['ambiguous_stop_first'] for t in stats['trade_list'])
            result[lane] = stats
            save_signed(output,'checkpoint',result)
    report = {'state':'completed_one_off_diagnostic','results':result,'period_utc':protocol['period_utc'],
        'protocol_sha256':digest(output/'protocol.json'),'rule':protocol['signal_inversion'],
        'direction_gate_exception':protocol['direction_gate_exception'], 'portfolio':protocol['portfolio'],
        'limitations':protocol['limitations'],'orders_sent':0,'live_policy_changed':False,'broker_eligible':False}
    save_signed(output,'report',report)
    portable = {**report,'results':{name:{k:v for k,v in s.items() if k!='trade_list'} for name,s in result.items()}}
    (ROOT/'docs/INVERTED_ORDERS_ONCE_20261124.json').write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    atomic_json(output/'progress.json',{'state':report['state']})
    print(json.dumps(portable),flush=True)


if __name__ == '__main__': run()
