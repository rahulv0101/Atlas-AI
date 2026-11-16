"""Fresh matched SMC backtest plus unchanged shared-policy compatibility replay.

Research only: no model activation, settings edits, or order dispatch.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
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
from atlas_ai.strategies.smc_entry_models import MODELS
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.policy_replay import replay
from atlas_ai.testing.smc_validation import HistoricalFeed, METHOD
from atlas_ai.trader import AtlasTrader
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.smc_validation import initialize, validate


def prepare(directory):
    from atlas_ai.config.settings import load_settings
    storage = Path(load_settings().storage_dir).resolve()
    directory = directory.resolve()
    directory.relative_to(storage)
    directory.mkdir(parents=True, exist_ok=False)
    with patch.object(mt5, 'order_send', deny):
        initialize(directory / MODELS[0], MODELS[0], activate=False)
        initialize(directory / MODELS[1], MODELS[1], directory / MODELS[0],
                   activate=False, reuse_costs=True)
    first = signed(directory / MODELS[0], 'manifest')
    save_signed(directory, 'protocol', {
        'schema': 'atlas_smc_entry_comparison_v1', 'models': list(MODELS),
        'declared_at': datetime.now(timezone.utc).isoformat(),
        'data_status': 'fresh_download_rolling_180_days_previously_inspected_history_not_blind',
        'history_start': first['history_start'], 'history_end': first['history_end'],
        'review_criteria': METHOD, 'parameter_search': False, 'retuning_after_outcomes': False,
        'cost_policy': 'Identical frozen current specification, nominal capital, risk and costs for both models.',
        'broker_eligible': False, 'orders_sent': 0, 'automatic_broker_activation': False,
        'paper_activation': 'none; existing observers and active pointers unchanged',
        'additional_replay': 'Existing shared Atlas deterministic gates, same inputs and candidates; missing visual/macro/news state remains unavailable.'})
    return directory / MODELS[0] / 'frozen_source' / 'tools' / 'rerun_smc_backtest.py'


def run_offline(directory):
    from tools.research_smc_entries import run
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'order_send', deny):
        run(directory)
        manifest = validate(directory / MODELS[0])
        inputs = signed(directory / MODELS[0], 'inputs')
        frames = {}
        for tf, expected in inputs.items():
            path = directory / MODELS[0] / (tf + '.csv')
            if digest(path) != expected:
                raise ValueError('input_changed_before_policy_audit')
            frames[tf] = pd.read_csv(path)
            frames[tf]['time'] = pd.to_datetime(frames[tf].time, utc=True)
        frame = frames['M5']
        indices = {t: i for i, t in enumerate(frame.time)}
        feed = HistoricalFeed({tf: frames[tf] for tf in TIMEFRAMES})
        rows = {name: [] for name in MODELS}
        receipt = signed(directory, 'prediction_receipt')
        if digest(directory / 'predictions.jsonl') != receipt['sha256']:
            raise ValueError('predictions_changed_before_policy_audit')
        with tempfile.TemporaryDirectory(prefix='atlas_smc_shared_policy_') as temp:
            cfg = settings_for(manifest, temp)
            trader = AtlasTrader.__new__(AtlasTrader)
            with (directory / 'predictions.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    record = json.loads(line)
                    candidates = {name: v['candidate'] for name, v in record['predictions'].items() if v.get('candidate')}
                    if not candidates:
                        continue
                    now = pd.Timestamp(record['now'])
                    i = indices[pd.Timestamp(record['input_last_bar'])]
                    feed.now = now
                    context = collect(feed, now, broker_timezone=cfg.mt5_server_timezone or 'UTC')
                    regime = trader._market_regime(list(frame.close.iloc[max(0, i-59):i+1]))
                    for name, signal in candidates.items():
                        rows[name].append({'index': i, 'available_at': now.isoformat(), 'signals': [signal],
                                           'regime': regime, 'higher_tf_bias': context['bias'], 'higher_context': context})
            save_signed(directory, 'shared_policy_candidates', {
                'source_predictions_sha256': receipt['sha256'], 'rows': rows,
                'note': 'Derived from the original frozen predictions; not new outcome-tuned signals.'})
            execution = frame.copy()
            execution['spread'] = frame.spread.shift(1)
            start, end = pd.Timestamp(manifest['history_start']), pd.Timestamp(manifest['history_end'])
            bounds = [start, start + (end-start)*.6, start + (end-start)*.8, end]
            result = {'schema': 'atlas_smc_shared_policy_replay_v1', 'models': {},
                      'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False,
                      'full_live_pipeline_recreated': False,
                      'limitation': 'No historical visual/macro/news evidence or real fills; SMC screening and shared-policy replay are different evidence lanes.',
                      'protocol_sha256': digest(directory / 'protocol.json'),
                      'prediction_receipt_sha256': digest(directory / 'prediction_receipt.json')}
            for name in MODELS:
                result['models'][name] = {}
                for j, stage in enumerate(['development', 'validation', 'holdout']):
                    atomic_json(directory / 'progress.json', {'phase': 'shared_policy_replay', 'model': name, 'stage': stage})
                    result['models'][name][stage] = replay(execution, rows[name], cfg, BrokerSpec(**manifest['spec']),
                        ExitVariant('configured', cfg.backtest_break_even_lock_r, 3.), KnowledgeStore(temp), manifest['limits'],
                        start=bounds[j].to_pydatetime(), end=bounds[j+1].to_pydatetime())
            if digest(directory / 'predictions.jsonl') != receipt['sha256']:
                raise ValueError('predictions_changed_during_policy_audit')
            result['state'] = 'completed_research_only'
            save_signed(directory, 'shared_policy_report', result)
            atomic_json(directory / 'progress.json', {'phase': 'completed_research_only',
                        'checked_at': datetime.now(timezone.utc).isoformat()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    try:
        if args.offline:
            run_offline(directory)
        else:
            frozen = prepare(directory)
            subprocess.run([sys.executable, str(frozen), '--offline', '--run-dir', str(directory)],
                           cwd=ROOT, check=True)
    except Exception as exc:
        if directory.exists():
            atomic_json(directory / 'progress.json', {'phase': 'failed_review_required', 'error_type': type(exc).__name__})
        raise
