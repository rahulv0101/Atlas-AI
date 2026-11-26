from copy import deepcopy
import pytest
from test_smc_entry_models import event_case, sweep_case
from test_smc_pullback import NOW
from atlas_ai.strategies import smc_entry_models as old
from atlas_ai.strategies import smc_h1_research as new


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('fixture,legacy,variant,name', [
    (event_case, old.event_retest, new.event_retest, new.MODELS[0]),
    (sweep_case, old.sweep_reclaim, new.sweep_reclaim, new.MODELS[1]),
])
def test_h1_direction_can_oppose_other_frames_without_fabricating_confluence(side, fixture, legacy, variant, name):
    f, context, quote = fixture(side)
    context['details'].update(H1=side, D1='sell' if side=='buy' else 'buy', H4='flat', M15='flat')
    context['evidence']['H1']['bias'] = side
    before = deepcopy(context)
    assert legacy(f, context, quote, NOW)['candidate'] is None
    result = variant(f, context, quote, NOW)
    assert result['candidate'], result
    assert result['candidate']['side'] == side and result['candidate']['strategy'] == name
    assert not result['broker_eligible'] and result['orders_sent'] == 0
    assert result['setup_context']['direction_timeframes'] == ['H1']
    assert result['reward_risk_before_fees_slippage'] >= 2
    assert context == before


@pytest.mark.parametrize('bias,status', [('flat','available'), ('unknown','available'), ('buy','unavailable')])
def test_h1_missing_flat_or_unavailable_cannot_create_candidate(bias,status):
    f,c,q = sweep_case()
    c['details']['H1'] = bias
    c['evidence']['H1']['status'] = status
    assert new.sweep_reclaim(f,c,q,NOW)['candidate'] is None


def test_legacy_default_adapter_output_is_unchanged():
    f,c,q = event_case()
    assert old.event_retest(f,c,q,NOW) == old.event_retest(f,c,q,NOW,context_provider=old.context_observation)


def test_research_models_are_not_registered_for_broker_signal_selection():
    from atlas_ai.strategies.inventory import base_inventory
    assert not set(new.MODELS)&{model.name for model in base_inventory('M5',top_down=True)}
