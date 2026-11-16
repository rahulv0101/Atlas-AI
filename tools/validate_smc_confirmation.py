"""Freeze and replay one declared SMC confirmation correction; never activate."""
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
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.risk.risk_manager import RiskSnapshot
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.historical_decision import historical_decision
from atlas_ai.testing.policy_replay import policy_trader, replay
from atlas_ai.testing.smc_confirmation import Confirmation, MODELS, RULES, affordable
from atlas_ai.testing.smc_validation import HistoricalFeed
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.smc_validation import validate
from tools.m5_stop_research import review


def run(source, output):
    original = signed(source, 'protocol')
    report = signed(source, 'report')
    receipt = signed(source, 'prediction_receipt')
    if report['protocol_sha256'] != digest(source/'protocol.json') or receipt['protocol_sha256'] != digest(source/'protocol.json'):
        raise ValueError('source_protocol_changed')
    if digest(source/'predictions.jsonl') != receipt['sha256']:
        raise ValueError('source_predictions_changed')
    manifest = validate(source/next(iter(MODELS)))
    for name, expected in manifest['source_hashes'].items():
        if name.startswith('atlas_ai/') and digest(ROOT/name) != expected:
            raise ValueError('shared_policy_changed_requires_new_baseline')
    frames = {}
    for tf, expected in signed(source/next(iter(MODELS)), 'inputs').items():
        path = source/next(iter(MODELS))/(tf+'.csv')
        if digest(path) != expected:
            raise ValueError('source_candles_changed')
        frames[tf] = pd.read_csv(path)
        frames[tf]['time'] = pd.to_datetime(frames[tf].time, utc=True)
    output = output.resolve()
    output.relative_to(Path(manifest['settings'].get('storage_dir', ROOT/'storage')).resolve())
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for folder in ['atlas_ai', 'tools']:
        for path in (ROOT/folder).rglob('*.py'):
            rel = path.relative_to(ROOT)
            target = output/'frozen_source'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            hashes[rel.as_posix()] = digest(target)
    protocol = {'schema': 'atlas_smc_confirmation_correction_v1', 'models': MODELS, 'rules': RULES,
        'frozen_at': datetime.now(timezone.utc).isoformat(), 'source_protocol_sha256': digest(source/'protocol.json'),
        'source_report_sha256': digest(source/'report.json'), 'source_predictions_sha256': receipt['sha256'],
        'settings': manifest['settings'], 'spec': manifest['spec'], 'limits': manifest['limits'],
        'history_start': manifest['history_start'], 'history_end': manifest['history_end'],
        'scope': 'Only original eligible SMC prediction windows; inherited session/gap/outcome availability screens apply.',
        'data_status': 'Previously inspected retrospective history; not blind or prospective validation.',
        'selection': 'One fixed adapter per model; no search/retuning; all three chronological stages must pass original review.',
        'stage_state': 'Reset pending setups at each chronological split. No cross-split trades.',
        'risk': 'Nominal initial-balance affordability at prediction; unchanged shared portfolio risk and loss limits applied again at replay.',
        'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False, 'live_policy_changed': False}
    save_signed(output, 'protocol', protocol)
    save_signed(output, 'source_receipt', {'protocol_sha256': digest(output/'protocol.json'), 'hashes': hashes})
    frame = frames['M5']
    times = list(frame.time)
    indices = {t: i for i, t in enumerate(times)}
    feed = HistoricalFeed({tf: frames[tf] for tf in TIMEFRAMES})
    start, end = pd.Timestamp(manifest['history_start']), pd.Timestamp(manifest['history_end'])
    bounds = [start, start+(end-start)*.6, start+(end-start)*.8, end]
    counts = {name: Counter() for name in MODELS.values()}
    rows = {name: [] for name in MODELS.values()}
    states = {name: Confirmation(name) for name in MODELS}
    current_stage = None
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'order_send', deny), tempfile.TemporaryDirectory(prefix='atlas_confirmation_') as temp:
        cfg = settings_for(manifest, temp)
        spec = BrokerSpec(**manifest['spec'])
        trader = policy_trader(cfg, KnowledgeStore(temp))
        with (source/'predictions.jsonl').open(encoding='utf-8') as stream, (output/'observations.jsonl').open('w', encoding='utf-8') as out:
            for line in stream:
                record = json.loads(line)
                now = pd.Timestamp(record['now'])
                stage = next(j for j in range(3) if bounds[j] <= now < bounds[j+1])
                if stage != current_stage:
                    states = {name: Confirmation(name) for name in MODELS}
                    current_stage = stage
                if not any(v.get('candidate') for v in record['predictions'].values()) and not any(v.pending for v in states.values()):
                    continue
                i = indices[pd.Timestamp(record['input_last_bar'])]
                window = frame.iloc[max(0, i-1199):i+1]
                feed.now = now
                context = collect(feed, now, broker_timezone=cfg.mt5_server_timezone or 'UTC')
                quote = {**record['quote'], 'digits': spec.digits}
                regime = trader._market_regime(list(window.close.tail(60)))
                snapshot = RiskSnapshot(cfg.backtest_initial_balance, cfg.backtest_initial_balance, 0, 0, (quote['ask']-quote['bid'])/spec.point, 0, 0)
                for source_name, state in states.items():
                    raw = record['predictions'][source_name]
                    if not raw.get('candidate') and not state.pending:
                        continue
                    def timing(signal):
                        chosen = TradeSignal(**signal)
                        return historical_decision(trader, chosen, [chosen], window, regime, context['bias'], snapshot,
                            now.to_pydatetime(), higher_context=context)['timing_passed']
                    def budget(signal, entry):
                        return affordable(signal, entry, spec, cfg, manifest['limits'], spread_points=snapshot.spread_points)
                    observation = state.step(raw, window, context, quote, now, timing, budget)
                    counts[state.name][observation['stage']+':'+observation['reason']] += 1
                    out.write(json.dumps({'available_at': now.isoformat(), 'observation': observation}, allow_nan=False)+'\n')
                    if observation['candidate']:
                        rows[state.name].append({'index': i, 'available_at': now.isoformat(), 'signals': [observation['candidate']],
                            'regime': regime, 'higher_tf_bias': context['bias'], 'higher_context': context})
        save_signed(output, 'candidate_cache', {'rows': rows, 'counts': {k: dict(v) for k, v in counts.items()}})
        save_signed(output, 'prediction_receipt', {'protocol_sha256': digest(output/'protocol.json'),
            'observations_sha256': digest(output/'observations.jsonl'), 'candidate_cache_sha256': digest(output/'candidate_cache.json'),
            'predictions_completed_before_labels': True})
        execution = frame.copy()
        execution['spread'] = frame.spread.shift(1)
        result = {'state': 'running', 'models': {}, 'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False,
                  'live_policy_changed': False, 'protocol_sha256': digest(output/'protocol.json')}
        for name, cache in rows.items():
            stages = {}
            for j, label in enumerate(['development', 'validation', 'holdout']):
                stats = replay(execution, cache, cfg, spec, ExitVariant('configured', cfg.backtest_break_even_lock_r, 3.),
                    KnowledgeStore(temp), manifest['limits'], start=bounds[j].to_pydatetime(), end=bounds[j+1].to_pydatetime())
                stats['review'] = review(stats)
                stages[label] = stats
            result['models'][name] = {'counts': dict(counts[name]), 'eligible_candidates': len(cache), 'stages': stages,
                                     'historical_review_passed': all(v['review']['passed'] for v in stages.values())}
        result.update(state='completed_research_only', selected_for_broker=None,
                      prediction_receipt_sha256=digest(output/'prediction_receipt.json'))
        if digest(source/'predictions.jsonl') != receipt['sha256']:
            raise ValueError('source_predictions_changed_during_test')
        save_signed(output, 'report', result)
        atomic_json(output/'progress.json', {'phase': result['state'], 'checked_at': datetime.now(timezone.utc).isoformat()})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source.resolve(), args.output.resolve())
    print(json.dumps({name: {'eligible_candidates': r['eligible_candidates'], 'historical_review_passed': r['historical_review_passed']}
                      for name, r in result['models'].items()}))
