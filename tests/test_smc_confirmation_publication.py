import pytest
from atlas_ai.atomic_files import atomic_json
from atlas_ai.research_status import load_research_progress
from tools.learn_candidate_ranker import save_signed, digest
from tools.publish_smc_confirmation import publish


def fixture(storage):
    storage.mkdir()
    directory = storage/'study'
    directory.mkdir()
    atomic_json(storage/'smc_validation_active.json', {'run_dir': 'original_paper_observer'})
    atomic_json(storage/'smc_entry_comparison_active.json', {'run_dir': 'original_operator_view'})
    (directory/'observations.jsonl').write_text('[]\n')
    save_signed(directory, 'candidate_cache', {'rows': {}})
    save_signed(directory, 'protocol', {'broker_eligible': False})
    save_signed(directory, 'prediction_receipt', {
        'protocol_sha256': digest(directory/'protocol.json'),
        'observations_sha256': digest(directory/'observations.jsonl'),
        'candidate_cache_sha256': digest(directory/'candidate_cache.json')})
    save_signed(directory, 'report', {'state': 'completed_research_only', 'broker_eligible': False,
        'auto_promotion': False, 'orders_sent': 0, 'selected_for_broker': None,
        'models': {'model_v6': {'eligible_candidates': 0, 'counts': {}, 'stages': {}}},
        'protocol_sha256': digest(directory/'protocol.json'),
        'prediction_receipt_sha256': digest(directory/'prediction_receipt.json')})
    return directory


def test_verified_view_reaches_existing_answer_path_without_changing_paper_authority(tmp_path):
    storage = tmp_path/'storage'
    directory = fixture(storage)
    paper = (storage/'smc_validation_active.json').read_bytes()
    previous = (storage/'smc_entry_comparison_active.json').read_bytes()
    view = publish(directory, storage)
    assert (storage/'smc_validation_active.json').read_bytes() == paper
    assert (view/'previous_operator_pointer.json').read_bytes() == previous
    result = load_research_progress(storage)['entry_comparison']
    assert result['state'] == 'completed_research_only' and result['stale'] is False
    assert result['selection']['selected_for_broker'] is None
    assert result['selection']['selected_for_forward_paper'] is None
    assert list(result['models']) == ['model_v6']


def test_changed_observations_cannot_replace_the_operator_report(tmp_path):
    storage = tmp_path/'storage'
    directory = fixture(storage)
    before = (storage/'smc_entry_comparison_active.json').read_bytes()
    (directory/'observations.jsonl').write_text('tampered\n')
    with pytest.raises(ValueError, match='research_receipt_changed'):
        publish(directory, storage)
    assert (storage/'smc_entry_comparison_active.json').read_bytes() == before
