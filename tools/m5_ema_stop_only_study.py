"""Frozen, offline EMA stop-only comparison on disjoint archived candidate streams."""
import json
import math
from copy import deepcopy
from pathlib import Path
import tempfile
from unittest.mock import patch

import MetaTrader5 as mt5
import pandas as pd

from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.top_down import collect
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.strategies.indicators import atr
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.policy_replay import replay
from atlas_ai.testing.smc_validation import HistoricalFeed
from tools.cost_aware_strategy_audit import prepare_frame
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.m5_stop_research import review


def stop_only(rows, frame, point):
    if not math.isfinite(point) or point <= 0:
        raise ValueError('positive_point_required')
    result = deepcopy(rows)
    values = atr(frame)
    for row in result:
        i = row['index']
        if not 14 <= i < len(frame)-1:
            raise ValueError('closed_candidate_window_required')
        if pd.Timestamp(row['available_at']) != pd.Timestamp(frame.time.iloc[i]) + pd.Timedelta(minutes=5):
            raise ValueError('closed_candidate_clock_mismatch')
        value = float(values.iloc[i])
        if not math.isfinite(value) or value <= 0:
            raise ValueError('positive_closed_ATR_required')
        for signal in row['signals']:
            if signal['strategy'] == 'ema_crossover' and signal['side'] in {'buy', 'sell'}:
                signal['stop_loss_points'] = max(signal['stop_loss_points'], 2*value/point)
    return result


def run():
    root = Path(__file__).resolve().parents[1]
    output = root/'storage/m5_ema_stop_only_20261124_v2'
    output.mkdir(exist_ok=False)
    recent = root/'storage/deployed_m5_parity_20261117T205724Z'
    separate = root/'storage/m5_stop_research_20261114'
    current = root/'storage/full_day_counter_replay_20261123_after_fix'
    reference, old, cfg = signed(recent, 'protocol'), signed(separate, 'protocol'), signed(current, 'protocol')
    recent_report = signed(recent, 'report')
    if recent_report['candidate_receipt_sha256'] != digest(recent/'candidates.json'):
        raise ValueError('reference_candidates_changed')
    receipt = signed(separate, 'prediction_receipt')
    if receipt['datasets']['separate_validation'] != digest(separate/'separate_validation_candidates.json'):
        raise ValueError('separate_candidates_changed')
    datasets = {
        'discovery': (root/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',
                      reference['historical_inputs'], signed(recent, 'candidates')['rows'],
                      old['discovery_start_utc'], old['discovery_end_utc']),
        'separate_validation': (separate, signed(separate, 'inputs')['hashes'],
                                signed(separate, 'separate_validation_candidates')['lanes']['unchanged_baseline'],
                                old['validation_start_utc'], old['validation_end_utc'])}
    if pd.Timestamp(old['validation_end_utc']) > pd.Timestamp(old['discovery_start_utc']):
        raise ValueError('disjoint_periods_required')
    protocol = {
        'hypothesis': 'EMA-only minimum two closed-M5 ATR stop may reduce noise stopouts; targets and signals remain fixed.',
        'change': 'max(original_stop_points, 2*ATR14_price/point); EMA directional signals only',
        'settings': cfg['settings'], 'spec': cfg['spec'], 'limits': cfg['limits'],
        'costs': 'Frozen broker spec, prior closed spread proxy, 3 points slippage per side; not measured historical fills.',
        'criteria': {'min_trades_each_period': 30, 'min_dates': 2, 'positive_mean_net_R': True,
                     'min_profit_factor': 1.1, 'max_drawdown_R': 6,
                     'improve_mean_net_R_vs_baseline_each_period': True},
        'parameters_frozen_before_outcomes': True, 'parameter_search': False,
        'source_hashes': {p.relative_to(root).as_posix(): digest(p)
                          for folder in ('atlas_ai', 'tools') for p in (root/folder).rglob('*.py')},
        'limitations': [
            'Previously inspected disjoint history, not blind or forward validation.',
            'Archived candidate signals held fixed; HTF contexts rebuilt from native histories with current collect(). Downstream replay uses current policy. Not a regenerated full-system replay.',
            'EMA component study: other strategies excluded, so portfolio ranking and consensus interactions are not tested.',
            'Closed-bar stop-first simulation; live intrabar timing, adaptive cooldown, screenshots, macro/news, lessons and execution gates are incomplete.',
            'Initial balance and broker costs are current frozen approximations for older periods.',
            'No live strategy, risk, execution or learning state writes. No automatic promotion.'],
        'broker_eligible': False, 'orders_sent': 0}
    save_signed(output, 'protocol', protocol)
    prepared = {}
    for name, (directory, hashes, rows, start, end) in datasets.items():
        if digest(directory/'M5.csv') != hashes['M5']:
            raise ValueError('candles_changed:'+name)
        frames = {}
        for tf, expected in hashes.items():
            if digest(directory/(tf+'.csv')) != expected:
                raise ValueError('native_history_changed:'+tf)
            frames[tf] = prepare_frame(pd.read_csv(directory/(tf+'.csv')))
            frames[tf]['time'] = pd.to_datetime(frames[tf].time, utc=True)
        frame = frames['M5']
        rows = [r for r in rows if pd.Timestamp(start) <= pd.Timestamp(r['available_at']) < pd.Timestamp(end)]
        rows = deepcopy(rows)
        feed = HistoricalFeed(frames)
        context = None
        key = None
        for row in rows:
            at = pd.Timestamp(row['available_at'])
            if at.floor('15min') != key:
                key = at.floor('15min')
                feed.now = at
                context = collect(feed, at, broker_timezone=protocol['settings'].get('mt5_server_timezone') or 'UTC')
            row['higher_context'] = {**context, 'evaluated_at': at.isoformat()}
            row['higher_tf_bias'] = context['bias']
        lanes = {'baseline': rows, 'two_ATR_stop_only': stop_only(rows, frame, protocol['spec']['point'])}
        save_signed(output, name+'_candidates', lanes)
        prepared[name] = (frame, lanes, start, end)
    save_signed(output, 'prediction_receipt', {
        'protocol_sha256': digest(output/'protocol.json'),
        'candidate_hashes': {name: digest(output/(name+'_candidates.json')) for name in prepared},
        'data_hashes': {name: hashes for name, (_, hashes, _, _, _) in datasets.items()}})
    results = {}
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'login', deny), patch.object(mt5, 'order_send', deny):
        for name, (frame, lanes, start, end) in prepared.items():
            results[name] = {}
            execution = frame.copy()
            execution['spread'] = frame.spread.shift(1)
            for lane, rows in lanes.items():
                atomic_json(output/'progress.json', {'dataset': name, 'lane': lane, 'state': 'running'})
                with tempfile.TemporaryDirectory() as temp:
                    settings = settings_for(protocol, temp)
                    stats = replay(execution, rows, settings, BrokerSpec(**protocol['spec']),
                                   ExitVariant('configured', settings.backtest_break_even_lock_r, 3.),
                                   KnowledgeStore(temp), protocol['limits'], strategy='ema_crossover',
                                   start=pd.Timestamp(start).to_pydatetime(), end=pd.Timestamp(end).to_pydatetime())
                stats['review'] = review(stats)
                results[name][lane] = stats
                save_signed(output, 'checkpoint', results)
    passed = all(values['two_ATR_stop_only']['review']['passed'] and
                 values['baseline']['mean_net_r'] is not None and
                 values['two_ATR_stop_only']['mean_net_r'] > values['baseline']['mean_net_r']
                 for values in results.values())
    report = {'state': 'completed_research_only', 'results': results,
              'historical_review_passed': passed, 'live_activated': False, 'broker_eligible': False,
              'orders_sent': 0, 'protocol_sha256': digest(output/'protocol.json'),
              'prediction_receipt_sha256': digest(output/'prediction_receipt.json'),
              'limitations': protocol['limitations']}
    save_signed(output, 'report', report)
    portable = {**report, 'results': {name: {lane: {k:v for k,v in stats.items() if k != 'trade_list'}
                                            for lane,stats in values.items()} for name,values in results.items()}}
    (root/'docs/M5_EMA_STOP_ONLY_20261124.json').write_text(json.dumps(portable, indent=2)+'\n', encoding='utf-8')
    atomic_json(output/'progress.json', {'state': report['state']})
    print(json.dumps(portable), flush=True)


if __name__ == '__main__':
    run()
