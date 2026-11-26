from copy import deepcopy
from tools.validate_matched_target import historical_gate
from tools.validate_matched_target import existing_registration


def good():
    baseline={'trades':40,'wins':20,'mean_net_r':.1,'profit_factor':1.2,'max_drawdown_r':3.}
    candidate={**baseline,'mean_net_r':.2}
    return {p:{c:{'baseline':deepcopy(baseline),'paired_targets':deepcopy(candidate)}
               for c in ('base','stress')} for p in ('first','separate')}


def test_positive_separate_cost_checked_comparison_can_pass_historical_only():
    assert historical_gate(good())['passed']


def test_win_rate_does_not_override_negative_returns_or_cost_failure():
    results=good()
    results['separate']['stress']['paired_targets'].update(wins=35,mean_net_r=-.1,profit_factor=.8)
    gate=historical_gate(results)
    assert not gate['passed']
    assert 'nonpositive_expectancy' in gate['failures'][0]['reasons']


def test_missing_separate_period_cost_lane_or_sample_fails():
    for change in ('period','cost','sample'):
        results=good()
        if change=='period':results.pop('separate')
        elif change=='cost':results['separate'].pop('stress')
        else:results['separate']['base']['paired_targets']['trades']=2
        assert not historical_gate(results)['passed']


def test_repeat_review_preserves_original_registration_and_cannot_relabel_candidate(tmp_path):
    import json
    import pytest
    from tools.learn_candidate_ranker import save_signed
    directory=tmp_path/'run';directory.mkdir()
    save_signed(directory,'plan',{'candidate_id':'frozen','registered_at':'original','first_stage_cases':3})
    (tmp_path/'matched_target_validation_active.json').write_text(json.dumps({'run_dir':str(directory)}))
    before=(directory/'plan.json').read_bytes()
    assert existing_registration(tmp_path,'frozen')['registered_at']=='original'
    assert (directory/'plan.json').read_bytes()==before
    with pytest.raises(ValueError):existing_registration(tmp_path,'different')
