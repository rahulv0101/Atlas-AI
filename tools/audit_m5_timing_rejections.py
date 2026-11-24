"""Read-only journal audit with delayed-next-M5 counterfactuals, never broker orders."""
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import tempfile
from unittest.mock import patch

import MetaTrader5 as mt5
import pandas as pd

from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.data.top_down import POLICY
from atlas_ai.learning.evidence_provenance import is_manual_broker_test
from atlas_ai.models import TradeSignal
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant, simulate
from tools.backtest_today_learning import normalize_rates
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny

ROOT = Path(__file__).resolve().parents[1]


def primary(message):
    text = message.lower()
    if text.startswith('timing discipline blocked trade'): return 'timing_discipline'
    if 'volatility protection' in text: return 'volatility'
    if 'h1 direction required' in text or 'higher-timeframe' in text: return 'higher_timeframe'
    if 'cooldown' in text: return 'cooldown'
    if 'session' in text: return 'session'
    if 'confidence' in text or 'conviction' in text: return 'confidence'
    return 'other'


def extract(event):
    meta = event.get('meta') or {}
    if meta.get('timeframe') != 'M5' or meta.get('action') not in ('blocked', 'hold'):
        return None
    chosen = meta.get('chosen') or {}
    if chosen.get('side') not in ('buy', 'sell'):
        return None
    if any(is_manual_broker_test(value) for value in (event, meta, chosen, meta.get('execution') or {})):
        return None
    at = pd.Timestamp(event['time'])
    if at.tzinfo is None: raise ValueError('aware_recorded_clock_required')
    timing = meta.get('timing_discipline') or {}
    htf = meta.get('higher_timeframe') or {}
    observed = timing.get('observed') or {}
    return {'at': at.tz_convert('UTC').isoformat(), 'policy': htf.get('policy', 'unrecorded'),
            'primary': primary(str(event.get('message', ''))), 'chosen': chosen,
            'missing': timing.get('missing') or [], 'timing_passed': timing.get('passed'),
            'observed': {k: observed.get(k) for k in ('location', 'momentum', 'trend_state', 'session')},
            'h1': htf.get('details', {}).get('H1'), 'htf_gate_passed': htf.get('entry_gate', {}).get('passed'),
            'confidence_threshold': meta.get('min_confidence_threshold'),
            'indicator_evidence': (timing.get('evidence_alignment') or {}).get('indicator'),
            'closed_preview': meta.get('closed_bar_entry_preview')}


def unique_timing(rows):
    """First recorded timing rejection per policy/strategy/side/M5 interval."""
    result = {}
    for row in sorted(rows, key=lambda x: x['at']):
        if row['primary'] != 'timing_discipline': continue
        signal = row['chosen']
        key = (row['policy'], signal['strategy'], signal['side'], pd.Timestamp(row['at']).floor('5min'))
        result.setdefault(key, row)
    return list(result.values())


def entry_index(frame, at):
    # Never borrow the opening price of the already-running decision candle.
    target = pd.Timestamp(at).floor('5min') + pd.Timedelta(minutes=5)
    times = pd.to_datetime(frame.time, utc=True)
    matches = times[times == target]
    return int(matches.index[0]) if len(matches) else None


def model(row, frame, settings, spec):
    i = entry_index(frame, row['at'])
    if i is None or i < 1: return {'state': 'entry_bar_not_yet_closed_or_missing'}
    candidate = row['chosen']
    chosen = TradeSignal(**{k: candidate[k] for k in ('strategy', 'side', 'confidence', 'stop_loss_points', 'take_profit_points')})
    spread = float(frame.spread.iloc[i-1])
    if not math.isfinite(spread) or spread < 0: return {'state': 'invalid_spread'}
    # Stop-first shared simulator with lagged spread; fixed minimum lot is a
    # standardized research probe, not a sizing/approval or portfolio replay.
    execution = frame.copy()
    execution['spread'] = frame.spread.shift(1)
    end = min(len(frame)-1, i+settings.backtest_max_hold_bars-1)
    if not pd.to_datetime(frame.time.iloc[i:end+1], utc=True).diff().dropna().eq(pd.Timedelta(minutes=5)).all():
        return {'state': 'gap_in_forward_window'}
    trade = simulate(execution, i, chosen, spec.volume_min, spec, settings,
                     ExitVariant('configured', settings.backtest_break_even_lock_r, 3.))
    if trade['exit_reason'] == 'max_hold' and end < i+settings.backtest_max_hold_bars-1:
        return {'state': 'forward_horizon_pending'}
    return {'state': 'modeled', 'entry_at': pd.Timestamp(frame.time.iloc[i]).isoformat(),
            'exit_at': pd.Timestamp(frame.time.iloc[trade['exit_bar']]).isoformat(),
            'net_r': trade['net_r'], 'net_cash': trade['net_cash'], 'exit_reason': trade['exit_reason'],
            'ambiguous_stop_first': trade['ambiguous_stop_first'], 'entry_index': i, 'exit_index': trade['exit_bar']}


def stats(rows):
    clear = [r for r in rows if not r['ambiguous_stop_first']]
    return {'probes': len(rows), 'positive': sum(r['net_r'] > 0 for r in rows),
            'negative': sum(r['net_r'] < 0 for r in rows),
            'mean_net_R': sum(r['net_r'] for r in rows)/len(rows) if rows else None,
            'ambiguous_stop_first': sum(r['ambiguous_stop_first'] for r in rows),
            'exit_reasons': dict(Counter(r['exit_reason'] for r in rows)),
            'unambiguous_subset': {'probes': len(clear), 'positive': sum(r['net_r'] > 0 for r in clear),
                                  'negative': sum(r['net_r'] < 0 for r in clear),
                                  'mean_net_R': sum(r['net_r'] for r in clear)/len(clear) if clear else None,
                                  'caution': 'Removing ambiguous cases changes the sample; not an unbiased performance estimate.'}}


def run():
    now = datetime.now(timezone.utc)
    start = now-timedelta(days=7)
    cfg = load_settings()
    storage = Path(cfg.storage_dir).resolve()
    output = storage/('m5_rejected_candidates_'+now.strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    reference = storage/'full_day_counter_replay_20261123_after_fix'
    previous = signed(reference, 'protocol')
    spec = BrokerSpec(**previous['spec'])
    save_signed(output, 'protocol', {
        'window_start_utc': start.isoformat(), 'capture_cutoff_utc': now.isoformat(),
        'current_policy': POLICY, 'counterfactual': 'next M5 open strictly after recorded decision, lagged spread, 3 points slippage each side, shared stop-first management, fixed broker minimum lot',
        'spec_basis': 'Frozen Nov23 research snapshot; approximate conversion and commission, not measured later fills.',
        'spec_receipt_sha256': digest(reference/'protocol.json'),
        'source_hashes': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT/'atlas_ai/testing/historical_broker.py']},
        'settings': previous['settings'], 'orders_sent': 0, 'live_policy_changed': False})
    records = []
    hasher = hashlib.sha256()
    path = storage/'events.jsonl'
    boundary = path.stat().st_size
    byte_count = 0
    with path.open('rb') as stream:
        while stream.tell() < boundary:
            line = stream.readline()
            if stream.tell() > boundary: break
            hasher.update(line); byte_count += len(line)
            try:
                event = json.loads(line)
                at = datetime.fromisoformat(event.get('time', '').replace('Z', '+00:00'))
                if at.tzinfo is None or not start <= at <= now: continue
                row = extract(event)
            except (ValueError, TypeError, KeyError): continue
            if row: records.append(row)
    # Deduplicate repeated publications of the same decision, not separate scans.
    records = list({(r['at'], r['policy'], r['primary'], json.dumps(r['chosen'], sort_keys=True)): r for r in records}.values())
    save_signed(output, 'recorded_rejections', {'rows': records, 'journal_prefix_bytes': byte_count, 'journal_prefix_sha256': hasher.hexdigest()})
    with patch.object(mt5, 'order_send', deny), patch.object(mt5, 'login', deny):
        feed = MarketDataFeed(cfg)
        feed._ensure_initialized()
        try:
            account = mt5.account_info()
            if account is None or account.login != cfg.hfm_login or account.server != cfg.hfm_server or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
                raise ValueError('matching_demo_required')
            raw = mt5.copy_rates_from_pos(cfg.symbol, mt5.TIMEFRAME_M5, 0, 2000)
            if raw is None: raise ValueError('short_snapshot_unavailable')
            frame = normalize_rates(raw, cfg)
            frame = frame[pd.to_datetime(frame.time, utc=True)+pd.Timedelta(minutes=5) <= pd.Timestamp(now)].reset_index(drop=True)
            frame.to_csv(output/'M5.csv', index=False)
        finally: mt5.shutdown()
    probes = unique_timing(records)
    groups = defaultdict(list)
    for row in records: groups[row['policy']].append(row)
    modeled = []
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'order_send', deny), tempfile.TemporaryDirectory() as temp:
        settings = settings_for(previous, temp)
        for row in probes:
            modeled.append({**row, 'outcome': model(row, frame, settings, spec)})
    save_signed(output, 'counterfactuals', {'rows': modeled})
    summary = {}
    for policy, rows in groups.items():
        timing = [r for r in rows if r['primary'] == 'timing_discipline']
        outcomes = [r for r in modeled if r['policy'] == policy]
        resolved = [r['outcome'] for r in outcomes if r['outcome']['state'] == 'modeled']
        feature_groups = defaultdict(list)
        for row in outcomes:
            if row['outcome']['state'] == 'modeled':
                key = str(row['observed']['location'])+'/'+str(row['observed']['momentum'])
                feature_groups[key].append(row['outcome'])
        selected = []; busy = -1
        for out in sorted(resolved, key=lambda x: x['entry_index']):
            if out['entry_index'] > busy:
                selected.append(out); busy = out['exit_index']
        summary[policy] = {
            'first_record_utc': min(r['at'] for r in rows), 'last_record_utc': max(r['at'] for r in rows),
            'directional_rejection_publications': len(rows), 'primary_blockers': dict(Counter(r['primary'] for r in rows)),
            'timing_missing_checks': dict(Counter(v for r in timing for v in r['missing'])),
            'timing_location_momentum': dict(Counter(str(r['observed']['location'])+'/'+str(r['observed']['momentum']) for r in timing)),
            'timing_with_htf_gate_passed': sum(r['htf_gate_passed'] is True for r in timing),
            'deduplicated_M5_timing_probes': len(outcomes),
            'probe_statuses': dict(Counter(r['outcome']['state'] for r in outcomes)),
            'all_overlapping_probes': stats(resolved), 'greedy_nonoverlapping_probes': stats(selected),
            'by_location_momentum': {key: stats(values) for key, values in feature_groups.items()}}
    report = {'state': 'completed_read_only_audit', 'current_policy': POLICY, 'by_recorded_policy': summary,
              'data_first_utc': str(frame.time.iloc[0]), 'last_closed_M5_open_utc': str(frame.time.iloc[-1]),
              'protocol_sha256': digest(output/'protocol.json'), 'candles_sha256': digest(output/'M5.csv'),
              'recorded_rejections_sha256': digest(output/'recorded_rejections.json'),
              'limitations': [
                  'Journal publications are not a complete atomic audit of every gate. No-direction scans excluded.',
                  'Current H1 policy is new: older-policy cohorts are separate and cannot establish its performance.',
                  'Probes begin after rejection at a later M5 opening quote. They do not reconstruct same-instant intrabar fills.',
                  'Positive hypothetical outcomes are not broker-executable missed trades; other session, risk, confidence and execution gates are not proven to pass.',
                  'Fixed-minimum-lot probes ignore portfolio sizing, session close limits and simultaneous accepted trades; net R is descriptive only.',
                  'All overlapping probes are correlated. Greedy nonoverlap is a sensitivity, not an independent sample or strategy.',
                  'Stop-first ambiguous candles cannot adjudicate actual missed winners; the unambiguous subset is selection-biased.',
                  'Fresh incomplete outcomes are pending; they are not counted as losses or zero returns.',
                  'Do not lower filters from this observational audit. No strategy, risk, execution or learning state changed.'],
              'orders_sent': 0, 'live_policy_changed': False, 'broker_eligible': False}
    save_signed(output, 'report', report)
    (ROOT/'docs/M5_REJECTED_CANDIDATES_20261124.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'directory': str(output), **report}), flush=True)


if __name__ == '__main__': run()
