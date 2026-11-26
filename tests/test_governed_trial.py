from copy import deepcopy
from datetime import datetime, timedelta, timezone

from atlas_ai.strategies.governed_trial import freeze_trial, review, metrics, POLICY
from atlas_ai.strategies.research_protocol import freeze, gene_hash
from atlas_ai.strategies.strategy_inventor import StrategyInventor
from atlas_ai.config.settings import Settings

NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)


def rows(count, start=NOW, net=.5):
    return [{'signal_at': (start+timedelta(minutes=i*15)).isoformat(),
             'entry_at': (start+timedelta(minutes=i*15+5)).isoformat(),
             'exit_at': (start+timedelta(minutes=i*15+10)).isoformat(),
             'net_r': net, 'gross_r': net+.1} for i in range(count)]


def batch():
    chromosome = StrategyInventor().invent()[0].chromosome.to_dict()
    return {'protocol': freeze(Settings(1, '', 'Demo')), 'asof': NOW.isoformat(),
            'dataset_sha256': 'test', 'candidates': [{'chromosome': chromosome,
                'frozen_gene_sha256': gene_hash(chromosome), 'training_rows': rows(40, NOW-timedelta(days=5)),
                'holdout_rows': rows(40, NOW-timedelta(days=3)), 'forward': []}]}


def test_training_selection_does_not_use_holdout_and_no_implicit_broker_authority():
    source = batch()
    other = deepcopy(source['candidates'][0])
    other['training_rows'] = rows(40, net=.2)
    other['holdout_rows'] = rows(40, net=100)
    source['candidates'].append(other)
    trial = freeze_trial(source, NOW)
    assert trial['candidates'][0]['training_rows'][0]['net_r'] == .5
    result = review(trial, NOW)
    assert result['state'] == 'collecting_forward'
    assert not result['broker_eligible'] and result['orders_sent'] == 0
    source['candidates'][0]['training_rows'][0]['net_r'] = -999
    assert review(trial, NOW)['state'] == 'collecting_forward'


def test_forward_stages_are_separate_and_total_minimum_retains_existing_governor():
    trial = freeze_trial(batch(), NOW)
    trial['candidates'][0]['forward'] = rows(60)
    result = review(trial, NOW+timedelta(days=2))
    assert result['stages']['first']['base']['trades'] == 30
    assert result['stages']['validation']['base']['trades'] == 30
    assert result['state'] == 'collecting_forward'
    trial['candidates'][0]['forward'] = rows(100)
    result = review(trial, NOW+timedelta(days=2))
    assert result['state'] == 'independent_validation_required'
    assert not result['broker_eligible'] and not result['auto_promotion']


def test_no_trades_deadline_and_weak_training_do_not_force_entries():
    trial = freeze_trial(batch(), NOW)
    assert review(trial, NOW+timedelta(days=29))['state'] == 'insufficient_activity'
    source = batch(); source['candidates'][0]['training_rows'] = rows(40, net=-.1)
    assert freeze_trial(source, NOW) is None
    assert review(None, NOW)['state'] == 'no_training_candidate'


def test_mutation_gap_overlap_and_drawdown_quarantine():
    original = freeze_trial(batch(), NOW)
    for mutate in (
        lambda t: t['identity']['policy'].update(stage_trades=1),
        lambda t: t['candidates'][0]['chromosome']['genes'][0].update(value=-999),
        lambda t: t['candidates'][0].update(forward_gap=True),
        lambda t: t['candidates'][0].update(forward=rows(2, NOW-timedelta(days=1))),
        lambda t: t['candidates'][0].update(forward=rows(8, net=-1.)),
        lambda t: t.update(forward_integrity='source_changed'),
    ):
        trial = deepcopy(original); mutate(trial)
        assert review(trial, NOW)['state'] == 'quarantined'


def test_cost_stress_can_reject_apparent_profit_without_changing_rules():
    source = batch()
    source['candidates'][0]['holdout_rows'] = [{**r, 'gross_r': 1., 'net_r': .1}
                                              for r in source['candidates'][0]['holdout_rows']]
    trial = freeze_trial(source, NOW)
    assert review(trial, NOW)['state'] == 'rejected_historical'
    assert metrics(rows(3))['net_r'] == 1.5


def test_pinned_trial_survives_outside_rotating_batches_and_aware_cursor(tmp_path, monkeypatch):
    import json
    import threading
    import pandas as pd
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    from atlas_ai.strategies.research_worker import StrategyResearchWorker
    source = batch()
    cfg = Settings(1, '', 'Demo', storage_dir=str(tmp_path), timeframe='M1')
    source['protocol'] = freeze(cfg)
    trial = freeze_trial(source, NOW)
    worker = StrategyResearchWorker(cfg, KnowledgeStore(str(tmp_path)), threading.Event())
    worker.path.parent.mkdir(parents=True, exist_ok=True)
    worker.path.write_text(json.dumps({'schema': 'atlas_strategy_research_v1', 'batches': [],
                                     'last_created_at': NOW.isoformat(), 'governed_trial': trial}))
    frame = pd.DataFrame({'time': pd.date_range(NOW-timedelta(hours=4), periods=800, freq='min'),
                          'open': 2000., 'high': 2001., 'low': 1999., 'close': 2000., 'spread': 20.})
    monkeypatch.setattr('atlas_ai.strategies.research_worker.evaluate', lambda *a, **k: (rows(2), 799))
    result = worker.run_once(frame, NOW+timedelta(hours=8))
    assert result['governed_trial']['identity_sha256'] == trial['identity_sha256']
    assert result['governed_review']['monitoring']['trades'] == 2
    assert result['governed_review']['state'] == 'collecting_forward'
    restored = json.loads(worker.path.read_text())
    assert restored['governed_trial']['identity_sha256'] == trial['identity_sha256']
