"""Matched research-only structural evidence handoff, using frozen v7 detections."""
import argparse
from contextlib import nullcontext
from collections import Counter
from datetime import datetime, timezone
import json
import math
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
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.risk.risk_manager import RiskSnapshot
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.historical_decision import historical_decision
from atlas_ai.testing.policy_replay import policy_trader, replay
from atlas_ai.testing.smc_confirmation import Confirmation, RULES as CONFIRMATION_RULES, affordable
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.testing.structural_timing import RULES, research_features
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.m5_stop_research import review

NAMES = {'smc_aligned_fvg_v7': 'smc_structural_timing_fvg_v8',
         'smc_aligned_micro_sweep_v7': 'smc_structural_timing_sweep_v8'}


def freeze_predictions(output, stream):
    # A checksum of an open buffered stream can otherwise omit its final bytes.
    # Complete the prediction write phase before creating the outcome boundary.
    stream.flush()
    save_signed(output, 'prediction_receipt', {'protocol_sha256': digest(output/'protocol.json'),
        'observations_sha256': digest(output/'observations.jsonl'),
        'candidate_cache_sha256': digest(output/'candidate_cache.json'),
        'predictions_completed_before_labels': True})


def verify_predictions(output):
    receipt = signed(output, 'prediction_receipt')
    if (receipt['observations_sha256'] != digest(output/'observations.jsonl')
            or receipt['candidate_cache_sha256'] != digest(output/'candidate_cache.json')):
        raise ValueError('predictions_changed_after_freeze')


def capital_profile(manifest, capacity):
    """Conservative deterministic demo bucket, not a parameter search or deposit."""
    evidence = signed(capacity.parent, capacity.stem)
    age = (pd.Timestamp.now(tz='UTC')-pd.Timestamp(evidence['checked_at'])).total_seconds()
    if (evidence['state'] != 'matching_configured_demo_account' or evidence['account_scope'] != manifest['account_scope']
            or evidence['currency'] != manifest['cost_evidence']['currency'] or not 0 <= age <= 900
            or evidence['risk_fraction'] != manifest['settings']['max_risk_per_trade']
            or evidence['minimum_lot'] != manifest['spec']['volume_min']):
        raise ValueError('fresh_matching_demo_capacity_required')
    balance = float(evidence['current_risk_budget'])/float(evidence['risk_fraction'])
    if not math.isfinite(balance) or balance <= 0:
        raise ValueError('valid_demo_balance_required')
    bucket = float(10**math.floor(math.log10(balance)))
    settings = {**manifest['settings'], 'backtest_initial_balance': bucket}
    return {**manifest, 'settings': settings}, {'source_sha256': digest(capacity),
        'rule': 'largest_power_of_ten_not_above_current_demo_balance', 'virtual_starting_balance': bucket,
        'account_or_risk_settings_changed': False}


def run(source, baseline, output, *, capacity=None, evidence_enabled=True):
    source_p = signed(source, 'protocol')
    source_r = signed(source, 'report')
    source_receipt = signed(source, 'prediction_receipt')
    if (source_r['protocol_sha256'] != digest(source/'protocol.json')
            or source_r['prediction_receipt_sha256'] != digest(source/'prediction_receipt.json')
            or source_receipt['observations_sha256'] != digest(source/'observations.jsonl')
            or source_p['source_protocol_sha256'] != digest(baseline/'protocol.json')
            or source_p['source_report_sha256'] != digest(baseline/'report.json')):
        raise ValueError('source_evidence_changed')
    for name, h in signed(source, 'source_receipt')['hashes'].items():
        if digest(source/'frozen_source'/name) != h:
            raise ValueError('frozen_source_changed')
        if name.startswith('atlas_ai/') and digest(ROOT/name) != h:
            raise ValueError('existing_shared_policy_changed')
    first = baseline/'smc_event_retest_v5'
    manifest = signed(first, 'manifest')
    capacity_basis = {'rule': 'original_frozen_nominal_starting_balance',
                      'virtual_starting_balance': manifest['settings']['backtest_initial_balance']}
    if capacity is not None:
        manifest, capacity_basis = capital_profile(manifest, capacity)
    frames = {}
    for tf, h in signed(first, 'inputs').items():
        path = first/(tf+'.csv')
        if digest(path) != h:
            raise ValueError('candles_changed')
        frames[tf] = pd.read_csv(path)
        frames[tf]['time'] = pd.to_datetime(frames[tf].time, utc=True)
    output = output.resolve()
    output.relative_to(ROOT/'storage')
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for folder in ['atlas_ai', 'tools']:
        for path in (ROOT/folder).rglob('*.py'):
            rel = path.relative_to(ROOT)
            target = output/'frozen_source'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            hashes[rel.as_posix()] = digest(target)
    save_signed(output, 'protocol', {'schema': 'atlas_structural_timing_handoff_v1',
        'frozen_at': datetime.now(timezone.utc).isoformat(), 'models': NAMES, 'rules': RULES,
        'confirmation_rules': CONFIRMATION_RULES, 'settings': manifest['settings'], 'spec': manifest['spec'], 'limits': manifest['limits'],
        'capital_profile': capacity_basis, 'structural_evidence_enabled': evidence_enabled,
        'source_protocol_sha256': digest(source/'protocol.json'), 'source_report_sha256': digest(source/'report.json'),
        'source_observations_sha256': source_receipt['observations_sha256'],
        'scope': 'Same v7 raw detections and eligible time grid; independently reconstructed structural evidence replaces generic range/momentum labels only for explicit v8 research names.',
        'qualification': 'All three original chronological stages must pass unchanged review; no automatic activation.',
        'data_status': 'Previously inspected retrospective data; not independent or prospective validation.',
        'live_policy_changed': False, 'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False})
    save_signed(output, 'source_receipt', {'protocol_sha256': digest(output/'protocol.json'), 'hashes': hashes})
    f = frames['M5']
    indices = {t: i for i, t in enumerate(f.time)}
    feed = HistoricalFeed({tf: frames[tf] for tf in TIMEFRAMES})
    start, end = pd.Timestamp(manifest['history_start']), pd.Timestamp(manifest['history_end'])
    bounds = [start, start+(end-start)*.6, start+(end-start)*.8, end]
    rows = {name: [] for name in NAMES.values()}
    counts = {name: Counter() for name in NAMES.values()}
    anchors, lookup, audit = {}, {}, {}
    current_stage = None
    states = {}
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'order_send', deny), tempfile.TemporaryDirectory(prefix='atlas_structure_evidence_') as temp:
        cfg = settings_for(manifest, temp)
        spec = BrokerSpec(**manifest['spec'])
        trader = policy_trader(cfg, KnowledgeStore(temp))
        features = research_features(lookup, audit) if evidence_enabled else nullcontext()
        with features, (source/'observations.jsonl').open(encoding='utf-8') as stream, (output/'observations.jsonl').open('w', encoding='utf-8') as out:
            for line in stream:
                record = json.loads(line)
                raw_values = record.get('detectors')
                if raw_values is None:
                    continue
                now = pd.Timestamp(record['available_at'])
                stage = next(j for j in range(3) if bounds[j] <= now < bounds[j+1])
                if stage != current_stage:
                    states = {name: Confirmation(name, research_name=target) for name, target in NAMES.items()}
                    current_stage = stage
                if not any(v.get('candidate') for v in raw_values.values()) and not any(v.pending for v in states.values()):
                    continue
                i = indices[now-pd.Timedelta(minutes=5)]
                window = f.iloc[max(0, i-1199):i+1]
                feed.now = now
                context = collect(feed, now, broker_timezone=cfg.mt5_server_timezone or 'UTC')
                bid = float(f.open.iloc[i+1])
                quote = {'bid': bid, 'ask': bid+float(f.spread.iloc[i])*spec.point,
                         'point': spec.point, 'digits': spec.digits, 'at': now.isoformat()}
                regime = trader._market_regime(list(window.close.tail(60)))
                snapshot = RiskSnapshot(cfg.backtest_initial_balance, cfg.backtest_initial_balance, 0, 0,
                                        (quote['ask']-bid)/spec.point, 0, 0)
                for name, state in states.items():
                    raw = raw_values[name]
                    if raw.get('candidate'):
                        anchors[raw['setup_id']] = (raw, now)
                    if not raw.get('candidate') and not state.pending:
                        continue
                    def timing(signal):
                        anchor, anchor_at = anchors[state.pending['id']]
                        lookup[(state.name, now.isoformat())] = {'context': context, 'quote': quote,
                            'anchor': anchor, 'anchor_at': anchor_at, 'now': now}
                        chosen = TradeSignal(**signal)
                        return historical_decision(trader, chosen, [chosen], window, regime, context['bias'], snapshot,
                            now.to_pydatetime(), higher_context=context)['timing_passed']
                    def budget(signal, entry):
                        return affordable(signal, entry, spec, cfg, manifest['limits'], spread_points=snapshot.spread_points)
                    observation = state.step(raw, window, context, quote, now, timing, budget)
                    counts[state.name][observation['stage']+':'+observation['reason']] += 1
                    evidence = audit.get((state.name, now.isoformat()))
                    out.write(json.dumps({'available_at': now.isoformat(), 'observation': observation, 'structural_evidence': evidence}, allow_nan=False)+'\n')
                    if observation['candidate']:
                        rows[state.name].append({'index': i, 'available_at': now.isoformat(), 'signals': [observation['candidate']],
                            'regime': regime, 'higher_tf_bias': context['bias'], 'higher_context': context})
            save_signed(output, 'candidate_cache', {'rows': rows, 'counts': {n: dict(v) for n, v in counts.items()},
                'verified_feature_records': [{'strategy': name, 'available_at': at, 'evidence': e} for (name, at), e in audit.items()]})
            freeze_predictions(output, out)
            execution = f.copy()
            execution['spread'] = f.spread.shift(1)
            result = {'state': 'running', 'models': {}, 'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False,
                      'live_policy_changed': False, 'protocol_sha256': digest(output/'protocol.json')}
            for name, cache in rows.items():
                stages = {}
                for j, label in enumerate(['development', 'validation', 'holdout']):
                    stats = replay(execution, cache, cfg, spec, ExitVariant('configured', cfg.backtest_break_even_lock_r, 3.),
                        KnowledgeStore(temp), manifest['limits'], start=bounds[j].to_pydatetime(), end=bounds[j+1].to_pydatetime())
                    stats['review'] = review(stats)
                    stages[label] = stats
                result['models'][name] = {'eligible_candidates': len(cache), 'counts': dict(counts[name]),
                    'stages': stages, 'historical_review_passed': all(s['review']['passed'] for s in stages.values())}
            result.update(state='completed_research_only', selected_for_broker=None,
                          prediction_receipt_sha256=digest(output/'prediction_receipt.json'),
                          evidence_counts=dict(Counter(e['reason'] for e in audit.values())))
            if digest(source/'observations.jsonl') != source_receipt['observations_sha256']:
                raise ValueError('source_predictions_changed_during_study')
            verify_predictions(output)
            save_signed(output, 'report', result)
            atomic_json(output/'progress.json', {'phase': result['state'], 'checked_at': datetime.now(timezone.utc).isoformat()})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capacity', type=Path)
    parser.add_argument('--control-without-evidence', action='store_true')
    args = parser.parse_args()
    result = run(args.source.resolve(), args.baseline.resolve(), args.output.resolve(),
                 capacity=args.capacity.resolve() if args.capacity else None,
                 evidence_enabled=not args.control_without_evidence)
    print(json.dumps({n: {'eligible_candidates': m['eligible_candidates'], 'historical_review_passed': m['historical_review_passed']}
                      for n, m in result['models'].items()}))
