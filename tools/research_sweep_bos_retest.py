"""Freeze one sequence redesign and test through unchanged shared gates. No orders."""
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
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.policy_replay import replay, policy_trader
from atlas_ai.testing.smc_confirmation import affordable
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.testing.sweep_bos_retest import NAME, RULES, evaluate, research_features
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.research_entry_horizon import load_frames
from tools.publish_entry_horizon import verify
from tools.m5_stop_research import review


def run(reference, baseline, archive, output):
    prior, control = verify(reference)
    if output.exists():
        raise FileExistsError('new_output_directory_required')
    output.resolve().relative_to((ROOT/'storage').resolve())
    for name, expected in signed(reference, 'source_receipt')['hashes'].items():
        if name.startswith('atlas_ai/') and digest(ROOT/name) != expected:
            raise ValueError('shared_policy_changed:'+name)
    primary_dir = baseline/'smc_event_retest_v5'
    inputs = {'primary': signed(primary_dir, 'inputs'), 'separate': signed(archive, 'inputs')['hashes']}
    frames = {'primary': load_frames(primary_dir, inputs['primary']), 'separate': load_frames(archive, inputs['separate'])}
    begin, end = map(pd.Timestamp, prior['primary_period'])
    april = list(map(pd.Timestamp, prior['separate_period']))
    if not (april[-1] <= begin or end <= april[0]):
        raise ValueError('disjoint_validation_required')
    bounds = {'primary': [begin, begin+(end-begin)*.6, begin+(end-begin)*.8, end], 'separate': april}
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for folder in ['atlas_ai', 'tools']:
        for path in (ROOT/folder).rglob('*.py'):
            rel = path.relative_to(ROOT)
            target = output/'frozen_source'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            hashes[rel.as_posix()] = digest(target)
    protocol = {'schema': 'atlas_sweep_BOS_retest_research_v1', 'frozen_at': datetime.now(timezone.utc).isoformat(),
        'model': NAME, 'rules': RULES, 'settings': prior['settings'], 'spec': prior['spec'], 'limits': prior['limits'],
        'periods': {p:[t.isoformat() for t in times] for p,times in bounds.items()}, 'input_hashes': inputs,
        'reference_protocol_sha256': digest(reference/'protocol.json'), 'reference_report_sha256': digest(reference/'report.json'),
        'time_grid_sha256': {p:signed(reference,p+'_raw_receipt')['sha256'] for p in frames},
        'control': 'Receipt-bound unchanged v8 control from same corrected-coverage run, inputs, costs, settings and stages; not newly rerun.',
        'interpretation': 'Primary history motivated redesign; April is disjoint but already inspected. Neither is blind or prospective evidence.',
        'review': 'Each of three primary stages plus separate April must pass original 30 trades/two dates/positive net mean/PF1.1/DD6R. No parameter search or automatic activation.',
        'candidate_counts': 'New model counts complete affordable sequences before shared portfolio timing/volatility/conviction checks; control prefilters timing as documented in its original protocol.',
        'broker_eligible': False, 'auto_promotion': False, 'orders_sent': 0, 'live_policy_changed': False}
    save_signed(output,'protocol',protocol)
    save_signed(output,'source_receipt',{'protocol_sha256':digest(output/'protocol.json'),'hashes':hashes})
    def progress(phase, **extra):
        atomic_json(output/'progress.json',{'phase':phase,'checked_at':datetime.now(timezone.utc).isoformat(),**extra})
    caches, lookups, all_counts = {}, {}, {}
    with patch.object(mt5,'initialize',deny), patch.object(mt5,'order_send',deny), tempfile.TemporaryDirectory(prefix='atlas_sequence_') as temp:
        cfg, spec = settings_for(prior,temp), BrokerSpec(**prior['spec'])
        trader = policy_trader(cfg,KnowledgeStore(temp))
        with (output/'observations.jsonl').open('w',encoding='utf-8') as stream:
            for period,fset in frames.items():
                raw_path = reference/(period+'_raw.jsonl')
                if digest(raw_path) != protocol['time_grid_sha256'][period]:
                    raise ValueError('coverage_changed')
                f, rows, lookup, counts = fset['M5'], [], {}, Counter()
                indices = {at:i for i,at in enumerate(f.time)}
                feed = HistoricalFeed({tf:fset[tf] for tf in TIMEFRAMES})
                key = context = None
                seen = set()
                with raw_path.open(encoding='utf-8') as source:
                    for n,line in enumerate(source):
                        record = json.loads(line)
                        now = pd.Timestamp(record['available_at'])
                        inherited = next(iter(record['detectors'].values()))
                        if inherited['stage'] == 'higher_timeframe_confluence':
                            counts['higher_timeframe_confluence:all_four_higher_timeframes_required'] += 1
                            continue
                        i = indices[now-pd.Timedelta(minutes=5)]
                        window = f.iloc[max(0,i-1199):i+1]
                        feed.now = now
                        if key != now.floor('15min'):
                            context = collect(feed,now,broker_timezone=cfg.mt5_server_timezone or 'UTC')
                            key = now.floor('15min')
                        ctx = {**context,'evaluated_at':now.isoformat()}
                        bid = float(f.open.iloc[i+1])
                        quote = {'bid':bid,'ask':bid+float(f.spread.iloc[i])*spec.point,'point':spec.point,'at':now.isoformat()}
                        result = evaluate(window,ctx,quote,now)
                        if result.get('candidate'):
                            if result['setup_id'] in seen:
                                result = {**result,'candidate':None,'stage':'deduplication','reason':'sequence_already_emitted'}
                            else:
                                seen.add(result['setup_id'])
                                allowed,reason,evidence = affordable(result['candidate'],result['entry_reference'],spec,cfg,prior['limits'],spread_points=float(f.spread.iloc[i]))
                                if not allowed:
                                    result = {**result,'candidate':None,'stage':'affordability','reason':reason,'affordability':evidence}
                        counts[result['stage']+':'+result['reason']] += 1
                        stream.write(json.dumps({'period':period,'available_at':now.isoformat(),'observation':result},allow_nan=False)+'\n')
                        if result.get('candidate'):
                            lookup[now.isoformat()] = {'context':ctx,'quote':quote}
                            rows.append({'index':i,'available_at':now.isoformat(),'signals':[result['candidate']],
                                'regime':trader._market_regime(list(window.close.tail(60))), 'higher_tf_bias':ctx['bias'],'higher_context':ctx})
                        if n % 100 == 0:
                            stream.flush()
                            progress('predictions_before_outcomes',period=period,window=n,candidates=len(rows))
                caches[period], lookups[period], all_counts[period] = rows, lookup, dict(counts)
        save_signed(output,'candidate_cache',{'rows':caches,'counts':all_counts})
        save_signed(output,'prediction_receipt',{'protocol_sha256':digest(output/'protocol.json'),
            'observations_sha256':digest(output/'observations.jsonl'),'candidate_cache_sha256':digest(output/'candidate_cache.json'),
            'predictions_completed_before_labels':True})
        stages = {}
        for period,fset in frames.items():
            f = fset['M5'].copy()
            f['spread'] = f.spread.shift(1)
            with research_features(lookups[period]):
                for j in range(len(bounds[period])-1):
                    label = ['development','validation','holdout'][j] if period=='primary' else 'separate_validation'
                    progress('shared_portfolio_replay',period=period,stage=label)
                    stats = replay(f,caches[period],cfg,spec,ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                        KnowledgeStore(temp),prior['limits'],start=bounds[period][j].to_pydatetime(),end=bounds[period][j+1].to_pydatetime())
                    stats['review'] = review(stats)
                    stages[label] = stats
        receipt = signed(output,'prediction_receipt')
        if receipt['observations_sha256'] != digest(output/'observations.jsonl') or receipt['candidate_cache_sha256'] != digest(output/'candidate_cache.json'):
            raise ValueError('predictions_changed')
        report = {'state':'completed_research_only','models':{NAME:{'eligible_candidates':sum(map(len,caches.values())),
            'counts':all_counts,'stages':stages}}, 'control':{p:r['control'] for p,r in control['periods'].items()},
            'historical_review_passed':all(s['review']['passed'] for s in stages.values()),
            'protocol_sha256':digest(output/'protocol.json'),'prediction_receipt_sha256':digest(output/'prediction_receipt.json'),
            'broker_eligible':False,'orders_sent':0,'auto_promotion':False,'live_policy_changed':False,'selected_for_broker':None}
        save_signed(output,'report',report)
        progress(report['state'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ['reference','baseline','archive','output']:
        parser.add_argument('--'+arg,type=Path,required=True)
    args = parser.parse_args()
    result = run(*(getattr(args,k).resolve() for k in ['reference','baseline','archive','output']))
    print(json.dumps({'state':result['state'],'historical_review_passed':result['historical_review_passed']}))
