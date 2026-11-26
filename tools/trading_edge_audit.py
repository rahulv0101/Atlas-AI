"""Frozen, offline evidence review. No tuning, broker access or activation."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from atlas_ai.atomic_files import atomic_json
from atlas_ai.brain.outcomes import load_confirmed_outcomes
from atlas_ai.config.settings import load_settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.policy_replay import cache_candidates, replay
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import digest, signed, save_signed, deny

ROOT = Path(__file__).resolve().parents[1]


def summarize(stats, start, end):
    """Descriptive uncertainty; day blocks retain within-day dependence."""
    rows = stats['trade_list']
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq='B')
    by_day = {day.date().isoformat(): [] for day in days}
    by_strategy = defaultdict(list)
    for trade in rows:
        by_day.setdefault(pd.Timestamp(trade['entry_at']).date().isoformat(), []).append(float(trade['net_r']))
        by_strategy[trade['strategy']].append(trade)
    counts = np.array([len(ts) for ts in by_day.values()])
    totals = np.array([sum(ts) for ts in by_day.values()])
    ci = None
    if counts.sum() and len(counts) >= 2:
        rng = np.random.default_rng(20261126)
        samples = rng.integers(0, len(counts), size=(10000, len(counts)))
        n = counts[samples].sum(axis=1)
        means = totals[samples].sum(axis=1)[n > 0] / n[n > 0]
        ci = np.quantile(means, [.025, .975]).tolist()
    result = {k: v for k, v in stats.items() if k != 'trade_list'}
    result.update(win_rate=stats['wins']/len(rows) if rows else None,
                  mean_net_r_day_block_bootstrap_95_interval=ci,
                  uncertainty_scope='Descriptive day-block bootstrap on reused data; not a prospective confidence guarantee.',
                  observed_weekdays=len(by_day), active_entry_days=int((counts > 0).sum()),
                  ambiguous_stop_first=sum(bool(t.get('ambiguous_stop_first')) for t in rows),
                  by_strategy={name: {'trades': len(ts), 'wins': sum(t['net_cash'] > 0 for t in ts),
                                      'net_cash': sum(t['net_cash'] for t in ts),
                                      'mean_net_r': sum(t['net_r'] for t in ts)/len(ts)}
                               for name, ts in by_strategy.items()})
    return result


def run():
    source = ROOT/'storage/today_learning_replay_20261123_v2'
    previous = ROOT/'storage/allocator_fix_backtest_20261125T213726Z'
    captured = signed(source, 'protocol')
    inputs = signed(source, 'inputs')
    prior_protocol = signed(previous, 'protocol')
    prior = signed(previous, 'report')
    if prior['protocol_sha256'] != digest(previous/'protocol.json'):
        raise ValueError('prior_protocol_changed')
    frames = {}
    for tf, expected in inputs.items():
        path = source/(tf+'.csv')
        if digest(path) != expected: raise ValueError('input_changed:'+tf)
        frame = pd.read_csv(path)
        frame['time'] = pd.to_datetime(frame.time, utc=True)
        if not frame.time.is_monotonic_increasing or frame.time.duplicated().any():
            raise ValueError('unordered_history:'+tf)
        frames[tf] = prepare_frame(frame)
        frames[tf]['time'] = pd.to_datetime(frames[tf].time, utc=True)
    settings = load_settings()
    if settings.timeframe != 'M5' or not settings.top_down_confluence_enabled:
        raise ValueError('expected_current_M5_top_down_policy')
    automation = json.loads((Path(settings.storage_dir)/'automation_state.json').read_text())
    automation = automation.get('payload', automation)
    session, pilot = automation['session_control'], automation['tiny_live_pilot']
    limits = {'day_trades': min(session['daily_trade_limit'], pilot['max_trades_per_day']),
              'loss_streak': min(session['consecutive_loss_limit'], pilot['max_consecutive_losses']),
              'daily_loss_percent': pilot['daily_loss_cap'], 'lot_cap': pilot['size_cap'],
              'setup_family': pilot['allowed_setup_family']}
    start, end = pd.Timestamp('2026-11-16T00:00Z'), pd.Timestamp(captured['end_utc'])
    frame = frames['M5']
    output = ROOT/'storage'/('trading_edge_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    protocol = {'schema': 'atlas_offline_edge_review_v1', 'frozen_at': datetime.now(timezone.utc).isoformat(),
                'settings': safe_settings(settings), 'limits': limits, 'spec': captured['spec'],
                'source_inputs_sha256': digest(source/'inputs.json'), 'inputs': inputs,
                'period_utc': [start.isoformat(), end.isoformat()],
                'earlier_report_sha256': digest(previous/'report.json'),
                'cost_lanes': {'base': {'spread_multiplier': 1, 'slippage_points_per_side': 3},
                               'stress': {'spread_multiplier': 2, 'slippage_points_per_side': 6}},
                'historical_fee_per_lot': captured['spec']['roundtrip_fee_per_lot'],
                'selection': 'Current configuration unchanged; no strategy or parameter search.',
                'data_classification': 'Previously inspected archive; newer nonoverlapping date block is not an untouched holdout.',
                'capital': 'Configured virtual backtest capital, not current funded account balance.',
                'source_hashes': {}, 'orders_sent': 0, 'broker_eligible': False}
    for folder in ('atlas_ai', 'tools'):
        for path in (ROOT/folder).rglob('*.py'):
            relative = path.relative_to(ROOT)
            target = output/'frozen_source'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            protocol['source_hashes'][relative.as_posix()] = digest(path)
    save_signed(output, 'protocol', protocol)
    def progress(**kwargs):
        atomic_json(output/'progress.json', kwargs)
    results = {}
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'login', deny), patch.object(mt5, 'order_send', deny):
        with tempfile.TemporaryDirectory(prefix='edge_audit_') as temporary:
            cfg = replace(settings, execute_trades=False, storage_dir=temporary,
                          gemini_api_key='', openai_api_key='',
                          backtest_persist_learning_state=False, backtest_record_loss_analysis=False)
            store = KnowledgeStore(temporary)
            start_index = max(250, int((frame.time+pd.Timedelta(minutes=5) >= start).to_numpy().nonzero()[0][0]))
            candidates, counts, strategies = cache_candidates(frame, cfg, store, progress,
                                                              start_index=start_index, native_frames=frames)
            save_signed(output, 'candidates', {'rows': candidates, 'counts': counts, 'strategies': strategies})
            candidate_hash = digest(output/'candidates.json')
            for lane, strict in [('base', False), ('stress', False), ('strict_evidence', True)]:
                progress(stage='replay', lane=lane, candidate_bars=len(candidates))
                cost = protocol['cost_lanes']['base' if strict else lane]
                execution = frame.copy()
                execution['spread'] = frame.spread.shift(1)*cost['spread_multiplier']
                stats = replay(execution, deepcopy(candidates), cfg, BrokerSpec(**protocol['spec']),
                               ExitVariant('configured', cfg.backtest_break_even_lock_r, cost['slippage_points_per_side']),
                               store, limits, strict=strict, start=start.to_pydatetime(), end=end.to_pydatetime())
                if digest(output/'candidates.json') != candidate_hash: raise ValueError('candidate_mutation')
                save_signed(output, lane, stats)
                results[lane] = summarize(stats, start, end)
                save_signed(output, 'checkpoint', results)
    earlier = summarize(prior['results']['after_allocator_fix'], *prior_protocol['period_utc'])
    closures = load_confirmed_outcomes(settings.storage_dir, settings)
    report = {'state': 'completed', 'protocol_sha256': digest(output/'protocol.json'),
              'candidate_sha256': candidate_hash, 'period_utc': protocol['period_utc'],
              'candidate_bars': len(candidates), 'strategies': strategies,
              'earlier_retrospective': earlier, 'current_configuration_recent_archive': results,
              'broker_confirmed_linked_closures': {'count': len(closures),
                  'wins': sum(row['net_pnl_zar'] > 0 for row in closures),
                  'net_cash': sum(row['net_pnl_zar'] for row in closures),
                  'scope': 'Linked closed positions only, excludes manual/test records; not protected lifecycle proof or a sufficient edge sample.'},
              'edge_established': False, 'full_live_policy_parity': False,
              'live_frequency_claim_allowed': False, 'broker_eligible': False, 'orders_sent': 0,
              'live_policy_changed': False,
              'limitations': [
                  'Reused retrospective dates, not an untouched out-of-sample or prospective qualification.',
                  'Missing historical visual/macro, adaptive/learning, broker occupancy, approval and ExecutionGate evidence.',
                  'Strict refusals mean unavailable evidence, not demonstrated zero live opportunity.',
                  'Closed M5 next-open fills and stop-first ambiguous bars approximate intrabar execution.',
                  'Prior conversion, margin and fee snapshot is reused; zero fee assumption is not proof of zero future charges.',
                  'Fresh replay allocator priors, not restored historical live learning state.',
                  'Recent archive ends on 23 November, not today. No new broker history queried.',
                  'Bootstrap describes this dependent small sample and cannot remove data reuse or execution-model bias.'
              ]}
    save_signed(output, 'report', report)
    (ROOT/'docs/TRADING_EDGE_AUDIT_20261126.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    progress(stage='completed')
    print(json.dumps({'output': str(output), 'report': report}), flush=True)


if __name__ == '__main__':
    run()
