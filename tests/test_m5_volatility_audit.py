import pytest
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.m5_proposal import volatility_policy


def test_active_measure_is_mean_absolute_close_change_not_atr_or_standard_deviation():
    trader=AtlasTrader.__new__(AtlasTrader)
    closes=[100+i*.1 for i in range(60)]
    result=trader._market_regime(closes)
    assert result['volatility_pct']==pytest.approx(round((.1/closes[-1])*100,4))


def test_screenshot_value_crosses_current_extreme_boundary_but_not_scaled_boundary():
    trader=AtlasTrader.__new__(AtlasTrader)
    regime={'volatility_pct':.0735}
    assert trader._volatility_safety_state(context_snapshot={},regime=regime)['volatility_action']=='block_new_entries'
    candidate=volatility_policy({},regime,{'elevated_pct':.09876061086549581,'extreme_pct':.1536276169018824})
    assert candidate['volatility_action']=='allow'


@pytest.mark.parametrize('vix',['panic','extreme'])
def test_scaled_price_threshold_never_removes_vix_extreme_veto(vix):
    result=volatility_policy({'vix_regime':vix},{'volatility_pct':.001},
        {'elevated_pct':.09876061086549581,'extreme_pct':.1536276169018824})
    assert result['volatility_action']=='block_new_entries'
