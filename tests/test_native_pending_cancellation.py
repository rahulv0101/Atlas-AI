from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import MetaTrader5 as mt5
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.execution.broker_adapter import BrokerOrderResponse
from atlas_ai.execution.mt5_broker_adapter import MT5BrokerAdapter
from atlas_ai.execution.trade_executor import TradeExecutor


@pytest.fixture
def pending(monkeypatch):
    settings = Settings(hfm_login=1, hfm_password="test", hfm_server="Demo", execute_trades=True)
    adapter = MT5BrokerAdapter(TradeExecutor(settings))
    order = SimpleNamespace(ticket=123, symbol=settings.symbol, magic=settings.magic_number, comment="AAI_Ddemo_Sema", type=mt5.ORDER_TYPE_BUY_LIMIT)
    monkeypatch.setattr(mt5, "terminal_info", lambda: SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=False))
    monkeypatch.setattr(mt5, "account_info", lambda: SimpleNamespace(login=1, server="Demo", trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO))
    monkeypatch.setattr(mt5, "orders_get", lambda **kwargs: [order])
    monkeypatch.setattr(adapter, "query_order_status", lambda **kwargs: BrokerOrderResponse(ok=True, status="cancelled", broker_order_id="123"))
    send = Mock(return_value=SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE))
    monkeypatch.setattr(mt5, "order_send", send)
    return adapter, order, send


def test_confirmed_pending_cancellation_sends_only_remove(pending):
    adapter, order, send = pending
    response = adapter.cancel_order(broker_order_id="123")
    assert response.ok and response.status == "cancelled"
    send.assert_called_once_with({"action": mt5.TRADE_ACTION_REMOVE, "order": 123, "symbol": order.symbol})


@pytest.mark.parametrize("change", ["other_symbol", "other_magic", "market_order", "real_account", "other_account", "execution_disabled", "api_disabled"])
def test_cancellation_refuses_unowned_or_unauthorized_orders(pending, monkeypatch, change):
    adapter, order, send = pending
    if change == "other_symbol": order.symbol = "EURUSD"
    if change == "other_magic": order.magic += 1
    if change == "market_order": order.type = mt5.ORDER_TYPE_BUY
    if change == "real_account": monkeypatch.setattr(mt5, "account_info", lambda: SimpleNamespace(login=1, server="Demo", trade_mode=mt5.ACCOUNT_TRADE_MODE_REAL))
    if change == "other_account": monkeypatch.setattr(mt5, "account_info", lambda: SimpleNamespace(login=2, server="Demo", trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO))
    if change == "execution_disabled": adapter._executor.settings = replace(adapter._executor.settings, execute_trades=False)
    if change == "api_disabled": monkeypatch.setattr(mt5, "terminal_info", lambda: SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=True))
    response = adapter.cancel_order(broker_order_id="123")
    assert not response.ok
    send.assert_not_called()


@pytest.mark.parametrize("result", [None, RuntimeError("IPC"), SimpleNamespace(retcode=mt5.TRADE_RETCODE_TIMEOUT)])
def test_ambiguous_cancel_never_retries(pending, result):
    adapter, order, send = pending
    if isinstance(result, Exception): send.side_effect = result
    else: send.return_value = result
    response = adapter.cancel_order(broker_order_id="123")
    assert not response.ok
    send.assert_called_once()


def test_successful_remove_still_needs_cancellation_confirmation(pending, monkeypatch):
    adapter, order, send = pending
    monkeypatch.setattr(adapter, "query_order_status", lambda **kwargs: BrokerOrderResponse(ok=True, status="filled", broker_order_id="123"))
    response = adapter.cancel_order(broker_order_id="123")
    assert not response.ok and response.status == "unknown"
    send.assert_called_once()


def test_cancelled_ticket_is_idempotent_without_new_send(pending, monkeypatch):
    adapter, order, send = pending
    monkeypatch.setattr(mt5, "orders_get", lambda **kwargs: [])
    assert adapter.cancel_order(broker_order_id="123").ok
    send.assert_not_called()
