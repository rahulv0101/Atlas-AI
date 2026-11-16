import json
import pytest
from tools.learn_candidate_ranker import digest, save_signed
from tools.publish_entry_horizon import publish
from atlas_ai.research_status import load_research_progress


def fixture_run(tmp_path):
    run = tmp_path/'run'
    run.mkdir()
    flags = dict(broker_eligible=False, orders_sent=0, auto_promotion=False, live_policy_changed=False)
    save_signed(run, 'protocol', {**flags, 'interpretation': 'Previously inspected history; no live authority.'})
    protocol_hash = digest(run/'protocol.json')
    save_signed(run, 'source_receipt', {'protocol_sha256': protocol_hash, 'hashes': {}})
    variants = ['control', 'entry_only', 'target_only', 'combined']
    periods = {}
    for period in ['primary', 'separate']:
        for suffix in ['raw', 'observations']:
            (run/(period+'_'+suffix+'.jsonl')).write_text('{}\n')
        save_signed(run, period+'_candidates', {'rows': {v: [] for v in variants}})
        save_signed(run, period+'_raw_receipt', {'protocol_sha256': protocol_hash,
            'predictions_completed_before_labels': True, 'sha256': digest(run/(period+'_raw.jsonl'))})
        save_signed(run, period+'_prediction_receipt', {'protocol_sha256': protocol_hash,
            'predictions_completed_before_labels': True,
            'observations_sha256': digest(run/(period+'_observations.jsonl')),
            'candidates_sha256': digest(run/(period+'_candidates.json'))})
        periods[period] = {v: {'eligible_candidates': 0, 'counts': {}, 'stages': {'test': {
            'trades': 0, 'wins': 0, 'net_cash': 0., 'mean_net_r': 0., 'profit_factor': None,
            'max_drawdown_r': 0., 'review': {'passed': False}}}} for v in variants}
    save_signed(run, 'report', {**flags, 'protocol_sha256': protocol_hash,
        'state': 'completed_research_only', 'selected_for_broker': None,
        'combined_review_passed': False, 'periods': periods})
    return run


def test_publish_preserves_all_lanes_and_never_selects_a_strategy(tmp_path):
    run = fixture_run(tmp_path)
    paper = tmp_path/'smc_validation_active.json'
    paper.write_text('{"run_dir":"existing_observer"}')
    before = paper.read_bytes()
    view = publish(run, tmp_path)
    report = json.loads((view/'report.json').read_text())
    assert len(report['models']) == 8
    assert report['selection']['selected_for_broker'] is None
    assert report['selection']['selected_for_forward_paper'] is None
    assert report['broker_eligible'] is False
    assert json.loads((tmp_path/'smc_entry_comparison_active.json').read_text())['run_dir'] == str(view)
    assert paper.read_bytes() == before
    status = load_research_progress(tmp_path)['entry_comparison']
    assert status['state'] == 'completed_research_only' and status['stale'] is False
    assert status['models'] == report['models']


@pytest.mark.parametrize('tamper', ['observations', 'raw', 'authority', 'count'])
def test_invalid_evidence_cannot_replace_existing_status(tmp_path, tamper):
    run = fixture_run(tmp_path)
    pointer = tmp_path/'smc_entry_comparison_active.json'
    pointer.write_text('old pointer')
    if tamper in ['observations', 'raw']:
        (run/('primary_'+tamper+'.jsonl')).write_text('changed')
    else:
        report = json.loads((run/'report.json').read_text())
        if tamper == 'authority':
            report['broker_eligible'] = True
        else:
            report['periods']['primary']['combined']['eligible_candidates'] = 1
        save_signed(run, 'report', report)
    with pytest.raises(ValueError):
        publish(run, tmp_path)
    assert pointer.read_text() == 'old pointer'
    assert not (run/'operator_view').exists()
