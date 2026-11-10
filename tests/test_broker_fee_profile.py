from datetime import datetime,timezone
from types import SimpleNamespace as NS

import pytest

from tools.broker_fee_profile import build_profile


def info():
    return NS(name="XAUUSD",point=.01,trade_tick_size=.01,trade_tick_value=1.,trade_stops_level=0,trade_freeze_level=8)


def test_roundtrip_fees_use_both_deal_volumes_without_double_counting():
    deals=[NS(symbol="XAUUSD",type=t,volume=1.,commission=-2.,fee=0.) for t in (0,1)]
    result=build_profile(deals,info(),"ZAR",datetime.now(timezone.utc))
    assert result["roundtrip_fee_per_lot_observed"]==4
    assert result["roundtrip_fee_points_estimate"]==4


def test_no_deals_is_unknown_fees_rather_than_zero():
    result=build_profile([],info(),"ZAR",datetime.now(timezone.utc))
    assert result["fee_samples"]==0 and result["roundtrip_fee_points_estimate"] is None


def test_missing_fee_history_is_not_a_free_broker():
    with pytest.raises(ValueError):build_profile(None,info(),"ZAR",datetime.now(timezone.utc))
