import pytest
from atlas_ai.testing.historical_broker import BrokerSpec
from tools.validate_recorded_costs import crosscheck


def test_actual_fill_price_arithmetic_remains_diagnostic_only():
    spec=BrokerSpec(.01,.01,1,1,.01,10,.01,2)
    diagnostic={"type":"automated_demo_diagnostic","natural_strategy_proof":False,
        "balanced_entry_exit":True,"broker_flat":True,"net_profit":-.35,
        "fills":[{"ticket":1,"profit":0},{"ticket":2,"profit":-.35}]}
    shared={"filled":True,"diagnostic":True,"fill_qty":.01,"quote_bid":100.,"quote_ask":100.34,"spread_price":.34}
    rows=[{**shared,"deal_id":"1","source":"entry","side":"buy","requested_price":100.34,
        "fill_price":100.34,"adverse_fill_difference_price":0},
        {**shared,"deal_id":"2","source":"intraday_close","side":"sell","requested_price":100.,
            "fill_price":99.99,"adverse_fill_difference_price":.01}]
    report=crosscheck(diagnostic,rows,spec)
    assert report["recorded_price_arithmetic_valid"]
    assert report["reconstructed_net_cash_current_conversion"]==pytest.approx(-.35)
    assert not report["natural_strategy_proof"] and not report["cost_calibration_ready"]
    rows[1]["diagnostic"]=False
    with pytest.raises(ValueError,match="diagnostic_fills"):crosscheck(diagnostic,rows,spec)
