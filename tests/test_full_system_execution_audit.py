from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import MetaTrader5 as mt5
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.execution.trade_executor import TradeExecutor
from atlas_ai.execution.mt5_broker_adapter import MT5BrokerAdapter
from atlas_ai.models import TradeSignal
from atlas_ai.risk.risk_manager import RiskManager, RiskSnapshot


@pytest.fixture
def transport(monkeypatch):
    settings = Settings(hfm_login=1, hfm_password="test", hfm_server="Demo")
    executor = TradeExecutor(settings)
    symbol = SimpleNamespace(point=.01, digits=2, filling_mode=0, volume_step=.01, volume_min=.01, volume_max=100)
    monkeypatch.setattr(mt5, "symbol_info", lambda *args: symbol)
    monkeypatch.setattr(mt5, "symbol_info_tick", lambda *args: SimpleNamespace(ask=3000.2, bid=3000.0))
    monkeypatch.setattr(mt5, "order_check", lambda *args: SimpleNamespace(retcode=0, comment="ok"))
    monkeypatch.setattr(executor, "_preflight_order_request", lambda *args: (True, "ok"))
    return executor


@pytest.mark.parametrize("code,status,qty", [
    (mt5.TRADE_RETCODE_DONE, "filled", .01),
    (mt5.TRADE_RETCODE_DONE_PARTIAL, "partially_filled", .005),
    (mt5.TRADE_RETCODE_PLACED, "submitted", 0.),
])
def test_accepted_order_is_sent_once_with_truthful_fill(transport, monkeypatch, code, status, qty):
    send = Mock(return_value=SimpleNamespace(retcode=code, order=123, deal=456 if qty else 0, volume=qty, price=3000.2, comment="accepted"))
    monkeypatch.setattr(mt5, "order_send", send)
    response = MT5BrokerAdapter(transport).submit_order(idempotency_key="audit", request={"side": "buy", "size": .01, "strategy": "momentum_continuation", "stop_loss_points": 100, "take_profit_points": 150})
    assert send.call_count == 1
    assert response.ok is True
    assert response.status == status
    assert response.fill_qty == qty


@pytest.mark.parametrize("result", [None, RuntimeError("IPC failed"), *[
    SimpleNamespace(retcode=code, order=0, deal=0, comment="uncertain") for code in (
        mt5.TRADE_RETCODE_TIMEOUT, mt5.TRADE_RETCODE_CONNECTION, mt5.TRADE_RETCODE_LOCKED, mt5.TRADE_RETCODE_ERROR
    )
]])
def test_uncertain_dispatch_never_retries_and_enters_unknown_state(transport, monkeypatch, result):
    send = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
    monkeypatch.setattr(mt5, "order_send", send)
    response = MT5BrokerAdapter(transport).submit_order(idempotency_key="audit", request={"side": "sell", "size": .01, "stop_loss_points": 100, "take_profit_points": 150})
    assert send.call_count == 1
    assert response.ok is False
    assert response.status == "unknown"


@pytest.mark.parametrize("field", ["equity", "balance", "daily_loss_pct", "weekly_loss_pct", "open_positions", "spread_points"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_risk_inputs_cannot_bypass_limits(field, value):
    risk = RiskManager(Settings(hfm_login=1, hfm_password="test", hfm_server="Demo"))
    snapshot = replace(RiskSnapshot(10000, 10000, 0, 0, 10), **{field: value})
    allowed, reason = risk.evaluate(snapshot)
    assert allowed is False
    assert field in reason


def test_nonfinite_sizing_does_not_fall_back_to_base_lot():
    risk = RiskManager(Settings(hfm_login=1, hfm_password="test", hfm_server="Demo"))
    assert risk.lot_size(float("nan"), 100, 1) == 0


@pytest.mark.parametrize("login,server,mode", [(2, "Demo", 0), (1, "Other", 0), (1, "Demo", mt5.ACCOUNT_TRADE_MODE_REAL)])
def test_account_switch_blocks_entries_and_housekeeping(transport, monkeypatch, login, server, mode):
    account = SimpleNamespace(login=login, server=server, trade_mode=mode)
    monkeypatch.setattr(mt5, "account_info", lambda: account)
    # The fixture replaces order preflight to isolate response handling. Restore
    # it for this test, which verifies the real account boundary.
    transport._preflight_order_request = TradeExecutor._preflight_order_request.__get__(transport)
    send = Mock(side_effect=AssertionError("A changed account must never receive an order"))
    monkeypatch.setattr(mt5, "order_send", send)
    result = transport.execute(TradeSignal("momentum_continuation", "buy", .9, 100, 150), .01)
    assert result.success is False
    assert "account" in result.comment.lower()
    result = transport.close_stale_positions(allow_close=True)
    assert len(result) == 1 and result[0].success is False
    send.assert_not_called()


@pytest.mark.parametrize("method", ["get_rates", "get_rates_for_timeframe"])
def test_empty_market_data_has_explicit_failure(transport, monkeypatch, method):
    from atlas_ai.data.market_data import MarketDataFeed
    feed = MarketDataFeed(transport.settings)
    monkeypatch.setattr(feed, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(mt5, "symbol_select", lambda *args: True)
    monkeypatch.setattr(mt5, "copy_rates_from_pos", lambda *args: [])
    monkeypatch.setattr("atlas_ai.data.market_data.time.sleep", lambda *args: None)
    with pytest.raises(RuntimeError, match="Failed to fetch MT5 rates"):
        feed.get_rates() if method == "get_rates" else feed.get_rates_for_timeframe("M5")
    if method == "get_rates":
        assert feed.last_fetch_meta["ok"] is False
        assert feed.last_fetch_meta["bars_received"] == 0


@pytest.mark.parametrize("state,expected,remaining", [
    (mt5.ORDER_STATE_FILLED, "filled", 0.),
    (mt5.ORDER_STATE_PARTIAL, "partially_filled", .005),
    (mt5.ORDER_STATE_PLACED, "acknowledged", .01),
    (mt5.ORDER_STATE_CANCELED, "cancelled", .01),
    (mt5.ORDER_STATE_REJECTED, "rejected", .01),
])
@pytest.mark.parametrize("historical", [True, False])
def test_native_reconciliation_uses_actual_order_state(transport, monkeypatch, state, expected, remaining, historical):
    row = SimpleNamespace(ticket=123, state=state, volume_initial=.01, volume_current=remaining)
    monkeypatch.setattr(mt5, "terminal_info", lambda: SimpleNamespace(connected=True))
    monkeypatch.setattr(mt5, "orders_get", lambda **kwargs: [] if historical else [row])
    monkeypatch.setattr(mt5, "history_orders_get", lambda **kwargs: [row])
    response = MT5BrokerAdapter(transport).query_order_status(broker_order_id="123")
    assert response.ok is True
    assert response.status == expected
    assert response.fill_qty == pytest.approx(.01 - remaining)


def test_unknown_status_never_clears_reconciliation_requirement():
    from atlas_ai.execution.broker_adapter import BrokerOrderResponse
    from atlas_ai.execution.order_tracker import OrderTracker
    from atlas_ai.execution.reconciliation import OrderReconciliation
    tracker = OrderTracker()
    tracker.upsert_submission(request_id="r", broker_order_id="123", environment="demo", instrument="XAUUSD", side="buy", size=.01, status="submitted")
    adapter = SimpleNamespace(query_order_status=lambda **kwargs: BrokerOrderResponse(ok=True, status="unknown", broker_order_id="123"))
    response = OrderReconciliation(adapter, tracker).reconcile_request("r")
    assert response.requires_review is True
    assert tracker.get_by_request("r").reconciliation_status == "required"


@pytest.mark.parametrize("history", [None, []])
def test_missing_order_is_unknown_and_not_a_verified_result(transport, monkeypatch, history):
    monkeypatch.setattr(mt5, "terminal_info", lambda: SimpleNamespace(connected=True))
    monkeypatch.setattr(mt5, "orders_get", lambda **kwargs: [])
    monkeypatch.setattr(mt5, "history_orders_get", lambda **kwargs: history)
    response = MT5BrokerAdapter(transport).query_order_status(broker_order_id="123")
    assert response.ok is False
    assert response.status == "unknown"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "NaN", "Infinity"])
def test_execution_gate_rejects_nonfinite_runtime_numbers(value):
    from atlas_ai.execution.execution_gate import ExecutionGate
    assert ExecutionGate._safe_float(value) is None


def test_future_or_negative_freshness_age_cannot_bypass_guard():
    from atlas_ai.execution.execution_gate import ExecutionGate
    result = ExecutionGate()._check_runtime_freshness({"freshness_runtime": {"is_stale": False, "status_age_ms": -100}}, strict=True)
    assert result["ok"] is False


@pytest.mark.parametrize("process_pid,heartbeat_pid,alive,age,expected", [
    (None, 123, False, 0, False),
    (456, 123, True, 0, False),
    (123, 123, True, 1000, False),
    (123, 123, True, -1000, False),
    (123, 123, True, 0, True),
    (None, 123, True, 0, True),
])
def test_startup_health_requires_current_worker_not_just_saved_status(tmp_path, monkeypatch, process_pid, heartbeat_pid, alive, age, expected):
    import json
    import time
    from datetime import datetime, timezone
    from atlas_ai import atlas_process_guard as guard
    config = SimpleNamespace(launch_profile="guarded_demo", health_stale_after_seconds=180)
    status = {"updated_at": datetime.now(timezone.utc).isoformat(), "execute_trades": True}
    (tmp_path / "heartbeat.json").write_text(json.dumps({"pid": heartbeat_pid, "last_heartbeat_ts": time.time() - age}))
    monkeypatch.setattr(guard, "runtime_status", lambda: status)
    monkeypatch.setattr(guard, "load_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    monkeypatch.setattr(guard, "backend_process_state", lambda cfg: SimpleNamespace(running=process_pid is not None, pid=process_pid))
    monkeypatch.setattr(guard, "process_exists", lambda pid: alive)
    result = guard.is_backend_healthy(config)
    assert result[0] is expected, result[1]


def test_pending_mt5_orders_are_included_in_orphan_detection(transport, monkeypatch):
    monkeypatch.setattr(mt5, "terminal_info", lambda: object())
    monkeypatch.setattr(mt5, "symbol_select", lambda *args: True)
    monkeypatch.setattr(mt5, "positions_get", lambda **kwargs: [])
    monkeypatch.setattr(mt5, "orders_get", lambda **kwargs: [SimpleNamespace(ticket=123, type=mt5.ORDER_TYPE_BUY_LIMIT, symbol="XAUUSD", volume_current=.01)])
    rows = MT5BrokerAdapter(transport).list_open_orders()
    assert len(rows) == 1
    assert rows[0]["broker_order_id"] == "123"
    assert rows[0]["side"] == "buy"
    assert rows[0]["status"] == "submitted"


def test_gateway_confirmation_counts_toward_daily_trade_guard():
    from atlas_ai.trader import AtlasTrader
    result = SimpleNamespace(success=True, order_id=0, deal_id=0, broker_order_id="123")
    assert AtlasTrader._execution_result_counts_as_trade(result) is True
    result.broker_order_id = ""
    assert AtlasTrader._execution_result_counts_as_trade(result) is False
    result.broker_order_id = "123"
    result.success = False
    assert AtlasTrader._execution_result_counts_as_trade(result) is False
