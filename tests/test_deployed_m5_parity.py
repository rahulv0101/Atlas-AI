from tools.deployed_m5_parity import completeness, MISSING


def test_missing_live_state_forbids_frequency_claims():
    result=completeness(MISSING)
    assert not result['full_live_parity']
    assert not result['frequency_claim_allowed']
    assert result['expected_live_trades_per_day'] is None
    assert 'approval_operator_presence_and_ExecutionGate_state' in result['missing_live_evidence']


def test_completeness_does_not_invent_a_rate_even_without_missing_labels():
    assert completeness([])['expected_live_trades_per_day'] is None
