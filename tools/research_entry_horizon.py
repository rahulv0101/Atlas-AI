"""Fixed 2x2 research comparison with disjoint historical validation; no orders."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.top_down import collect, TIMEFRAMES
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.risk.risk_manager import RiskSnapshot
from atlas_ai.testing.aligned_smc import detect
from atlas_ai.testing.entry_horizon import RULES, entry_check, target_plan, eligible_window
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.historical_decision import historical_decision
from atlas_ai.testing.policy_replay import policy_trader, replay
from atlas_ai.testing.smc_confirmation import Confirmation, affordable
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.testing.structural_timing import research_features
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.m5_stop_research import review

SOURCE_MODEL = 'smc_aligned_micro_sweep_v7'
RESEARCH_MODEL = 'smc_structural_timing_sweep_v8'
VARIANTS = {'control': (False, False), 'entry_only': (True, False),
            'target_only': (False, True), 'combined': (True, True)}


def load_frames(directory, hashes):
    result = {}
    for tf, expected in hashes.items():
        path = directory/(tf+'.csv')
        if digest(path) != expected:
            raise ValueError('input_changed:'+tf)
        result[tf] = pd.read_csv(path)
        result[tf]['time'] = pd.to_datetime(result[tf].time, utc=True)
    return result


def generate_period(frames, cfg, spec, bounds, path, progress, period):
    f = frames['M5']
    feed = HistoricalFeed({tf: frames[tf] for tf in TIMEFRAMES})
    times = f.time
    calendar = DayTradingSessionControl()
    key = context = None
    counts = Counter()
    with path.open('w', encoding='utf-8') as stream:
        for i in range(250, len(f)-12):
            now = times.iloc[i]+pd.Timedelta(minutes=5)
            if not bounds[0] <= now < bounds[-1]:
                continue
            session = calendar._detect_session(now.to_pydatetime())
            if not session.allowed or session.minutes_to_close < 70:
                counts['session_or_close_buffer'] += 1
                continue
            boundary = next(t for t in bounds[1:] if now < t)
            if not eligible_window(times, i, boundary):
                counts['input_outcome_or_boundary_gap'] += 1
                continue
            feed.now = now
            if key != now.floor('15min'):
                context = collect(feed, now, broker_timezone=cfg.mt5_server_timezone or 'UTC')
                key = now.floor('15min')
            ctx = {**context, 'evaluated_at': now.isoformat()}
            bid = float(f.open.iloc[i+1])
            quote = {'bid': bid, 'ask': bid+float(f.spread.iloc[i])*spec.point, 'point': spec.point, 'at': now.isoformat()}
            raw = detect(f.iloc[max(0, i-79):i+1], ctx, quote, now)[SOURCE_MODEL]
            counts[raw['stage']+':'+raw['reason']] += 1
            stream.write(json.dumps({'available_at': now.isoformat(), 'detectors': {SOURCE_MODEL: raw}}, allow_nan=False)+'\n')
            if i % 250 == 0:
                stream.flush()
                progress('raw_predictions_before_labels', period=period, bar=i, bars=len(f))
    return dict(counts)


def run(reference, patterns, baseline, archive, output):
    ref = signed(reference, 'protocol')
    ref_report = signed(reference, 'report')
    ref_receipt = signed(reference, 'prediction_receipt')
    if (ref_report['protocol_sha256'] != digest(reference/'protocol.json')
            or ref_report['prediction_receipt_sha256'] != digest(reference/'prediction_receipt.json')
            or ref_receipt['candidate_cache_sha256'] != digest(reference/'candidate_cache.json')
            or ref_receipt['observations_sha256'] != digest(reference/'observations.jsonl')):
        raise ValueError('reference_changed')
    for name, h in signed(reference, 'source_receipt')['hashes'].items():
        if digest(reference/'frozen_source'/name) != h or (name.startswith('atlas_ai/') and digest(ROOT/name) != h):
            raise ValueError('reference_policy_or_frozen_source_changed')
    pp, pr = signed(patterns, 'protocol'), signed(patterns, 'prediction_receipt')
    if (ref['source_protocol_sha256'] != digest(patterns/'protocol.json')
            or pr['observations_sha256'] != digest(patterns/'observations.jsonl')
            or pp['source_protocol_sha256'] != digest(baseline/'protocol.json')):
        raise ValueError('pattern_chain_changed')
    archive_protocol = signed(archive, 'protocol')
    archive_inputs = signed(archive, 'inputs')
    first = baseline/'smc_event_retest_v5'
    primary = load_frames(first, signed(first, 'inputs'))
    separate = load_frames(archive, archive_inputs['hashes'])
    manifest = signed(first, 'manifest')
    begin, end = pd.Timestamp(manifest['history_start']), pd.Timestamp(manifest['history_end'])
    separate_start, separate_end = pd.Timestamp(archive_inputs['first_utc']), pd.Timestamp(archive_inputs['last_utc'])+pd.Timedelta(minutes=5)
    if not (separate_end <= begin or end <= separate_start):
        raise ValueError('separate_period_must_be_disjoint')
    output = output.resolve()
    output.relative_to(ROOT/'storage')
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = {}
    for folder in ['atlas_ai', 'tools']:
        for file in (ROOT/folder).rglob('*.py'):
            rel = file.relative_to(ROOT)
            target = output/'frozen_source'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
            source_hashes[rel.as_posix()] = digest(target)
    protocol = {'schema': 'atlas_entry_horizon_research_v2', 'frozen_at': datetime.now(timezone.utc).isoformat(),
        'rules': RULES, 'variants': VARIANTS, 'settings': ref['settings'], 'spec': ref['spec'], 'limits': ref['limits'],
        'source_reference_sha256': digest(reference/'report.json'), 'source_patterns_sha256': pr['observations_sha256'],
        'separate_archive_protocol_sha256': digest(archive/'protocol.json'),
        'separate_inputs_sha256': digest(archive/'inputs.json'),
        'primary_period': [begin.isoformat(), end.isoformat()],
        'separate_period': [separate_start.isoformat(), separate_end.isoformat()],
        'review': 'Primary three stages and separate period must pass original 30-trade/two-date/positive-mean/PF1.1/DD6R review. No best-lane selection or automatic activation.',
        'interpretation': 'Primary period motivated the proposal and is exploratory. April is disjoint, previously available history, not blind or prospective proof.',
        'coverage': 'Fresh detection on both periods; detector-native 20-bar recent continuity plus complete 12-bar outcome availability. Older closed context may span scheduled closures. Supersedes inherited 80-bar screen without changing strategy parameters.',
        'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False, 'live_policy_changed': False}
    save_signed(output, 'protocol', protocol)
    save_signed(output, 'source_receipt', {'protocol_sha256': digest(output/'protocol.json'), 'hashes': source_hashes})
    def progress(phase, **extra):
        atomic_json(output/'progress.json', {'phase': phase, 'checked_at': datetime.now(timezone.utc).isoformat(), **extra})
    periods = {'primary': (primary, output/'primary_raw.jsonl', [begin, begin+(end-begin)*.6, begin+(end-begin)*.8, end]),
               'separate': (separate, output/'separate_raw.jsonl', [separate_start, separate_end])}
    result = {'state': 'running', 'periods': {}, 'broker_eligible': False, 'orders_sent': 0,
              'auto_promotion': False, 'live_policy_changed': False, 'protocol_sha256': digest(output/'protocol.json')}
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'order_send', deny), tempfile.TemporaryDirectory(prefix='atlas_entry_horizon_') as temp:
        cfg = settings_for(ref, temp)
        spec = BrokerSpec(**ref['spec'])
        for period, (frames, raw_path, bounds) in periods.items():
            raw_counts = generate_period(frames, cfg, spec, bounds, raw_path, progress, period)
            save_signed(output, period+'_raw_receipt', {'sha256': digest(raw_path),
                'protocol_sha256': digest(output/'protocol.json'), 'counts': raw_counts,
                'predictions_completed_before_labels': True})
        for period, (frames, raw_path, bounds) in periods.items():
            progress('intervention_predictions_before_labels', period=period)
            f = frames['M5']
            indices = {t: i for i,t in enumerate(f.time)}
            feed = HistoricalFeed({tf: frames[tf] for tf in TIMEFRAMES})
            states = {}
            current_stage = None
            anchors = {}
            rows = {name: [] for name in VARIANTS}
            lookups = {name: {} for name in VARIANTS}
            audits = {name: {} for name in VARIANTS}
            counts = {name: Counter() for name in VARIANTS}
            trader = policy_trader(cfg, KnowledgeStore(temp))
            with raw_path.open(encoding='utf-8') as stream, (output/(period+'_observations.jsonl')).open('w', encoding='utf-8') as out:
                for line in stream:
                    record = json.loads(line)
                    if 'detectors' not in record:
                        continue
                    raw = record['detectors'][SOURCE_MODEL]
                    now = pd.Timestamp(record['available_at'])
                    stage = next(j for j in range(len(bounds)-1) if bounds[j] <= now < bounds[j+1])
                    if stage != current_stage:
                        states = {v: Confirmation(SOURCE_MODEL, research_name=RESEARCH_MODEL) for v in VARIANTS}
                        current_stage = stage
                    if not raw.get('candidate') and not any(s.pending for s in states.values()):
                        continue
                    if raw.get('candidate'):
                        anchors[raw['setup_id']] = (raw, now)
                    i = indices[now-pd.Timedelta(minutes=5)]
                    window = f.iloc[max(0, i-1199):i+1]
                    feed.now = now
                    context = collect(feed, now, broker_timezone=cfg.mt5_server_timezone or 'UTC')
                    bid = float(f.open.iloc[i+1])
                    quote = {'bid': bid, 'ask': bid+float(f.spread.iloc[i])*spec.point, 'point': spec.point, 'digits': spec.digits, 'at': now.isoformat()}
                    regime = trader._market_regime(list(window.close.tail(60)))
                    snapshot = RiskSnapshot(cfg.backtest_initial_balance, cfg.backtest_initial_balance, 0, 0,
                        (quote['ask']-bid)/spec.point, 0, 0)
                    for variant, (entry_enabled, target_enabled) in VARIANTS.items():
                        state = states[variant]
                        if not raw.get('candidate') and not state.pending:
                            continue
                        detail = {}
                        transformed = {}
                        def timing(signal):
                            if entry_enabled:
                                check = entry_check(trader, window, signal['side'], now)
                                detail['entry'] = check
                                if not check['passed']:
                                    counts[variant]['entry_policy:'+check['reason']] += 1
                                    return False
                            anchor, anchor_at = anchors[state.pending['id']]
                            lookups[variant][(RESEARCH_MODEL, now.isoformat())] = {'context': context, 'quote': quote,
                                'anchor': anchor, 'anchor_at': anchor_at, 'now': now}
                            chosen = TradeSignal(**signal)
                            return historical_decision(trader, chosen, [chosen], window, regime, context['bias'], snapshot,
                                now.to_pydatetime(), higher_context=context)['timing_passed']
                        def budget(signal, entry):
                            if target_enabled:
                                allowed, changed, reason, evidence = target_plan(signal, window, spec.point, now)
                                detail['target'] = {'passed': allowed, 'reason': reason, **evidence}
                                if not allowed:
                                    return False, reason, evidence
                                transformed.update(changed)
                            return affordable(signal, entry, spec, cfg, ref['limits'], spread_points=snapshot.spread_points)
                        with research_features(lookups[variant], audits[variant]):
                            observation = state.step(raw, window, context, quote, now, timing, budget)
                        counts[variant][observation['stage']+':'+observation['reason']] += 1
                        if observation['candidate'] and target_enabled:
                            observation = {**observation, 'candidate': dict(transformed),
                                'original_target_reference': observation['target_reference'],
                                'target_reference': observation['entry_reference']+(1 if transformed['side']=='buy' else -1)*transformed['take_profit_points']*spec.point}
                        out.write(json.dumps({'available_at': now.isoformat(), 'variant': variant, 'observation': observation, 'proposal_review': detail}, allow_nan=False)+'\n')
                        if observation['candidate']:
                            rows[variant].append({'index': i, 'available_at': now.isoformat(), 'signals': [observation['candidate']],
                                'regime': regime, 'higher_tf_bias': context['bias'], 'higher_context': context})
            save_signed(output, period+'_candidates', {'rows': rows, 'counts': {n:dict(v) for n,v in counts.items()}})
            save_signed(output, period+'_prediction_receipt', {'protocol_sha256': digest(output/'protocol.json'),
                'observations_sha256': digest(output/(period+'_observations.jsonl')),
                'candidates_sha256': digest(output/(period+'_candidates.json')), 'predictions_completed_before_labels': True})
            execution = f.copy()
            execution['spread'] = f.spread.shift(1)
            result['periods'][period] = {}
            for variant, cache in rows.items():
                progress('shared_portfolio_replay', period=period, variant=variant)
                stages = {}
                with research_features(lookups[variant], audits[variant]):
                    for j in range(len(bounds)-1):
                        label = ['development', 'validation', 'holdout'][j] if period=='primary' else 'separate_validation'
                        stats = replay(execution, cache, cfg, spec, ExitVariant('configured', cfg.backtest_break_even_lock_r, 3.),
                            KnowledgeStore(temp), ref['limits'], start=bounds[j].to_pydatetime(), end=bounds[j+1].to_pydatetime())
                        stats['review'] = review(stats)
                        stages[label] = stats
                result['periods'][period][variant] = {'eligible_candidates': len(cache), 'counts': dict(counts[variant]), 'stages': stages}
            pred = signed(output, period+'_prediction_receipt')
            if pred['observations_sha256'] != digest(output/(period+'_observations.jsonl')) or pred['candidates_sha256'] != digest(output/(period+'_candidates.json')):
                raise ValueError('frozen_predictions_changed')
        result.update(state='completed_research_only', selected_for_broker=None,
            combined_review_passed=all(s['review']['passed'] for period in result['periods'].values() for s in period['combined']['stages'].values()))
        if digest(patterns/'observations.jsonl') != pr['observations_sha256']:
            raise ValueError('source_predictions_changed')
        for period, (_, raw_path, _) in periods.items():
            if signed(output, period+'_raw_receipt')['sha256'] != digest(raw_path):
                raise ValueError('frozen_raw_predictions_changed')
        save_signed(output, 'report', result)
        progress(result['state'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--patterns', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(*(getattr(args, name).resolve() for name in ['reference','patterns','baseline','archive','output']))
    print(json.dumps({'state': result['state'], 'combined_review_passed': result['combined_review_passed']}))
