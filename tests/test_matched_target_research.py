import pytest
from atlas_ai.testing.historical_broker import BrokerSpec
from tools.matched_target_research import paired_target


@pytest.mark.parametrize('stop',[100.,200.,1000.])
def test_target_covers_cost_adjusted_risk_and_never_shrinks(stop):
    spec=BrokerSpec(.01,.01,1.,1.1,.01,100.,.01,2,roundtrip_fee_per_lot=5.)
    target=paired_target(stop,150.,spec,3.)
    net=(target-3)*spec.tick_value_profit-spec.roundtrip_fee_per_lot
    risk=(stop+6)*spec.tick_value_loss+spec.roundtrip_fee_per_lot
    assert net>=2*risk and target>=150.


def test_wider_stop_gets_larger_target_and_invalid_inputs_fail():
    spec=BrokerSpec(.01,.01,1.,1.,.01,100.,.01,2)
    assert paired_target(200,100,spec,3)>paired_target(100,100,spec,3)
    assert paired_target(100,1000,spec,3)==1000
    with pytest.raises(ValueError):paired_target(0,100,spec,3)
