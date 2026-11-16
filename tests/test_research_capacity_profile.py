from copy import deepcopy
import pandas as pd
import pytest
from tools.learn_candidate_ranker import save_signed
from tools.research_structural_timing import capital_profile


def fixture(tmp_path):
    manifest = {'account_scope': 'matching-demo', 'settings': {'backtest_initial_balance': 10000., 'max_risk_per_trade': .005},
                'spec': {'volume_min': .01}, 'cost_evidence': {'currency': 'ZAR'}}
    capacity = {'state': 'matching_configured_demo_account', 'account_scope': 'matching-demo',
                'currency': 'ZAR', 'checked_at': pd.Timestamp.now(tz='UTC').isoformat(),
                'risk_fraction': .005, 'minimum_lot': .01, 'current_risk_budget': 601.}
    save_signed(tmp_path, 'capacity', capacity)
    return manifest, capacity, tmp_path/'capacity.json'


def test_capacity_profile_is_a_conservative_virtual_bucket_without_policy_mutation(tmp_path):
    manifest, _, path = fixture(tmp_path)
    before = deepcopy(manifest)
    derived, basis = capital_profile(manifest, path)
    assert derived['settings']['backtest_initial_balance'] == 100000.
    assert derived['settings']['max_risk_per_trade'] == .005
    assert derived['spec'] == manifest['spec']
    assert manifest == before
    assert basis['account_or_risk_settings_changed'] is False


@pytest.mark.parametrize('change', [
    {'state': 'real_account'}, {'risk_fraction': .02},
    {'checked_at': (pd.Timestamp.now(tz='UTC')-pd.Timedelta(minutes=20)).isoformat()},
])
def test_capacity_cannot_use_real_account_stale_or_different_risk_evidence(tmp_path, change):
    manifest, evidence, path = fixture(tmp_path)
    save_signed(tmp_path, 'capacity', {**evidence, **change})
    with pytest.raises(ValueError, match='fresh_matching_demo_capacity_required'):
        capital_profile(manifest, path)


def test_prediction_boundary_flushes_buffer_and_rejects_later_mutation(tmp_path):
    from tools.research_structural_timing import freeze_predictions, verify_predictions
    from tools.learn_candidate_ranker import signed, digest
    save_signed(tmp_path, 'protocol', {'research_only': True})
    save_signed(tmp_path, 'candidate_cache', {'rows': []})
    path = tmp_path/'observations.jsonl'
    with path.open('w', encoding='utf-8', buffering=8192) as stream:
        stream.write('{"closed_prediction":true}\n')
        freeze_predictions(tmp_path, stream)
        assert signed(tmp_path, 'prediction_receipt')['observations_sha256'] == digest(path)
        verify_predictions(tmp_path)
        stream.write('{"late_mutation":true}\n')
        stream.flush()
        with pytest.raises(ValueError, match='predictions_changed_after_freeze'):
            verify_predictions(tmp_path)
