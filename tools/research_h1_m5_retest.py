"""Fixed structural-retest overlay versus current H1/M5 timing; offline, no promotion."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd

from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.top_down import collect
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.h1_m5_retest_timing import RULES, overlay
from atlas_ai.testing.policy_replay import replay
from atlas_ai.testing.smc_validation import HistoricalFeed
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.cost_aware_strategy_audit import prepare_frame
from tools.m5_stop_research import review

ROOT = Path(__file__).resolve().parents[1]


def run():
    output = ROOT/'storage'/('h1_m5_retest_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    source = ROOT/'storage/m5_ema_stop_only_20261124_v2'
    receipt = signed(source, 'prediction_receipt')
    current = signed(ROOT/'storage/full_day_counter_replay_20261123_after_fix', 'protocol')
    periods = {
        'discovery': (ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',
                      '2026-10-15T08:10Z', '2026-11-14T08:10Z'),
        'separate_validation': (ROOT/'storage/m5_stop_research_20261114',
                                '2026-04-01T00:00Z', '2026-05-01T00:00Z')}
    protocol = {'rules': RULES, 'settings': current['settings'], 'spec': current['spec'],
                'limits': current['limits'], 'periods': {k: [a,b] for k,(_,a,b) in periods.items()},
                'criteria': 'At least 30 trades and 2 dates each period; positive mean net R; PF >=1.1; drawdown <=6R; improve mean net R versus baseline in both periods.',
                'no_parameter_search': True, 'frozen_before_outcomes': True,
                'costs': 'Frozen prior broker units, lagged M5 spread, 3 points per-side slippage; fees from frozen spec.',
                'limitations': ['Previously inspected retrospective periods, disjoint but not blind or forward validation.',
                    'Archived enabled built-in signal streams held fixed; native HTF contexts rebuilt with current H1 policy.',
                    'Partial policy replay, not complete live parity: missing screenshots, macro/news, adaptive state, cooldown timing and broker execution evidence.',
                    'Unchanged built-in stop/target geometry; one modelled position at a time; stop-first M5 OHLC execution has uncertain intrabar ordering.',
                    'No live activation, no learning state writes, no change to existing SMC research models.'],
                'broker_eligible': False, 'orders_sent': 0}
    hashes = {}
    for folder in ('atlas_ai', 'tools'):
        for p in (ROOT/folder).rglob('*.py'):
            rel = p.relative_to(ROOT)
            target = output/'frozen_source'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            hashes[rel.as_posix()] = digest(target)
    protocol['source_hashes'] = hashes
    save_signed(output, 'protocol', protocol)
    prepared = {}
    for name,(directory,start,end) in periods.items():
        atomic_json(output/'progress.json', {'phase': 'rebuild_native_H1_contexts', 'period': name})
        file = source/(name+'_candidates.json')
        if digest(file) != receipt['candidate_hashes'][name]: raise ValueError('source_candidates_changed')
        rows = deepcopy(signed(source, name+'_candidates')['baseline'])
        frames = {}
        for tf, expected in receipt['data_hashes'][name].items():
            path = directory/(tf+'.csv')
            if digest(path) != expected: raise ValueError('native_input_changed:'+tf)
            frames[tf] = prepare_frame(pd.read_csv(path))
            frames[tf]['time'] = pd.to_datetime(frames[tf].time, utc=True)
        feed = HistoricalFeed(frames)
        previous = None; context = None
        for index,row in enumerate(rows):
            at = pd.Timestamp(row['available_at'])
            if at.floor('15min') != previous:
                previous = at.floor('15min'); feed.now = at
                context = collect(feed, at, broker_timezone=current['settings'].get('mt5_server_timezone') or 'UTC')
            row['higher_context'] = {**context, 'evaluated_at': at.isoformat()}
            row['higher_tf_bias'] = context['bias']
            if index % 500 == 0:
                atomic_json(output/'progress.json', {'phase': 'native_contexts', 'period': name, 'rows': index})
        save_signed(output, name+'_candidates', {'rows': rows})
        prepared[name] = (frames['M5'], rows, start, end)
    save_signed(output, 'prediction_receipt', {
        'protocol_sha256': digest(output/'protocol.json'),
        'candidates': {name: digest(output/(name+'_candidates.json')) for name in prepared},
        'native_inputs': receipt['data_hashes']})
    results = {}; audits = {}
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'login', deny), patch.object(mt5, 'order_send', deny):
        for name,(frame,rows,start,end) in prepared.items():
            results[name] = {}
            contexts = {r['available_at']: r['higher_context'] for r in rows}
            execution = frame.copy(); execution['spread'] = frame.spread.shift(1)
            for lane in ('baseline', 'structural_retest'):
                atomic_json(output/'progress.json', {'phase': 'replay', 'period': name, 'lane': lane})
                evidence = {}
                with tempfile.TemporaryDirectory() as temp:
                    cfg = settings_for(protocol, temp)
                    def replay_lane():
                        return replay(execution, deepcopy(rows), cfg, BrokerSpec(**protocol['spec']),
                            ExitVariant('configured', cfg.backtest_break_even_lock_r, 3.), KnowledgeStore(temp),
                            protocol['limits'], start=pd.Timestamp(start).to_pydatetime(), end=pd.Timestamp(end).to_pydatetime())
                    if lane == 'baseline': result = replay_lane()
                    else:
                        with overlay(contexts, evidence): result = replay_lane()
                result['review'] = review(result)
                results[name][lane] = result
                audits[name] = {'evidence_checks': len(evidence),
                                'passed': sum(r['passed'] for r in evidence.values()),
                                'reasons': dict(Counter(r['reason'] for r in evidence.values()))}
                save_signed(output, 'checkpoint', {'results': results, 'audits': audits})
    passed = all(v['structural_retest']['review']['passed'] and v['baseline']['mean_net_r'] is not None
                 and v['structural_retest']['mean_net_r'] > v['baseline']['mean_net_r'] for v in results.values())
    report = {'state': 'completed_research_only', 'results': results, 'structural_evidence_audit': audits,
              'historical_review_passed': passed, 'live_activated': False, 'broker_eligible': False,
              'orders_sent': 0, 'live_policy_changed': False, 'protocol_sha256': digest(output/'protocol.json'),
              'prediction_receipt_sha256': digest(output/'prediction_receipt.json'),
              'periods': protocol['periods'], 'rules': RULES, 'limitations': protocol['limitations']}
    save_signed(output, 'report', report)
    portable = {**report, 'results': {name: {lane: {k:v for k,v in stats.items() if k!='trade_list'}
                                           for lane,stats in lanes.items()} for name,lanes in results.items()}}
    (ROOT/'docs/H1_M5_RETEST_TIMING_20261124.json').write_text(json.dumps(portable, indent=2)+'\n', encoding='utf-8')
    atomic_json(output/'progress.json', {'state': report['state']})
    print(json.dumps(portable), flush=True)


if __name__ == '__main__': run()
