import pytest

from atlas_ai.models import TradeSignal
from atlas_ai.trader import AtlasTrader


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), None, "invalid"])
def test_invalid_strategy_confidence_cannot_become_a_high_confidence_entry(value):
    trader=AtlasTrader.__new__(AtlasTrader)
    signal=TradeSignal("momentum_continuation","buy",value,100,160)
    result=trader._sanitize_signal(signal)
    assert result.side=="flat" and result.confidence==0


@pytest.mark.parametrize("value,expected", [(.3,.3),(1,1),(-1,0),(2,1)])
def test_finite_confidence_preserves_existing_clipping(value,expected):
    trader=AtlasTrader.__new__(AtlasTrader)
    result=trader._sanitize_signal(TradeSignal("momentum_continuation","sell",value,100,160))
    assert result.side=="sell" and result.confidence==expected
