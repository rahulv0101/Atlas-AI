from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock

import MetaTrader5 as mt5
import pytest

from atlas_ai.execution import cost_evidence as evidence


@pytest.mark.parametrize("side,price,expected",[(mt5.ORDER_TYPE_BUY,100.1,10),
    (mt5.ORDER_TYPE_SELL,99.9,10),(mt5.ORDER_TYPE_BUY,99.9,-10)])
def test_cost_measurement_preserves_request_and_result_identity(monkeypatch,side,price,expected):
    rows=[];monkeypatch.setattr(evidence,"_append_row",lambda settings,row:rows.append(row))
    request={"type":side,"symbol":"XAUUSD","price":100.,"volume":.01};before=deepcopy(request)
    result=NS(retcode=mt5.TRADE_RETCODE_DONE,price=price,volume=.01,order=1,deal=2)
    send=Mock(return_value=result)
    assert evidence.send_observed(send,request,NS(),source="entry",strategy="ema_crossover",
        decision_id="decision",tick=NS(bid=99.9,ask=100,time_msc=1)) is result
    send.assert_called_once_with(request)
    assert request==before and rows[0]["adverse_fill_difference_bps"]==pytest.approx(expected)
    assert rows[0]["spread_price"]==pytest.approx(.1) and not rows[0]["diagnostic"]


def test_failed_evidence_never_repeats_or_changes_a_successful_send(monkeypatch):
    monkeypatch.setattr(evidence,"_append_row",Mock(side_effect=PermissionError))
    result=NS(retcode=mt5.TRADE_RETCODE_DONE,price=100,volume=.01)
    send=Mock(return_value=result)
    assert evidence.send_observed(send,{"price":100,"type":mt5.ORDER_TYPE_BUY},NS(),source="entry") is result
    assert send.call_count==1


def test_dispatch_exception_propagates_once_with_unknown_outcome_evidence(monkeypatch):
    rows=[];monkeypatch.setattr(evidence,"_append_row",lambda settings,row:rows.append(row))
    error=RuntimeError("unknown broker outcome");send=Mock(side_effect=error)
    with pytest.raises(RuntimeError) as caught:
        evidence.send_observed(send,{},NS(),source="entry")
    assert caught.value is error and send.call_count==1
    assert rows[0]["error"]=="RuntimeError" and not rows[0]["filled"]


@pytest.mark.parametrize("code",[mt5.TRADE_RETCODE_PLACED,mt5.TRADE_RETCODE_REJECT])
def test_submitted_or_rejected_response_does_not_become_measured_fill(monkeypatch,code):
    rows=[];monkeypatch.setattr(evidence,"_append_row",lambda settings,row:rows.append(row))
    evidence.send_observed(lambda request:NS(retcode=code,price=100),{"price":100,"type":0},NS(),
        source="entry",strategy="manual_broker_test")
    assert not rows[0]["filled"] and rows[0]["adverse_fill_difference_bps"] is None
    assert rows[0]["diagnostic"]
