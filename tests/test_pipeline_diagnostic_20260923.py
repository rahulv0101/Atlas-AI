"""Isolated diagnostic: injected candidate through trader and real ExecutionGate."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

import pytest
import MetaTrader5 as mt5

from atlas_ai.execution.broker_adapter import TestBrokerAdapter
from atlas_ai.execution.execution_gate import ExecutionGate
from atlas_ai.execution.session_control import SessionWindow
from atlas_ai.risk.risk_manager import RiskManager
from atlas_ai.testing.replay_harness import _build_trader, default_replay_scenarios
from atlas_ai.trader import AtlasTrader


def _configured_pipeline(tmp_path):
    scenario = replace(default_replay_scenarios()[2], base_volume=0.01, min_confidence=0.44)
    trader, store = _build_trader(scenario)
    gate = ExecutionGate(state_store_path=str(tmp_path / "automation_state.json"))
    gate.set_gate_enabled(True)
    gate.set_rollout_stage("limited_live_pilot", approved=True)
    gate.set_broker_adapter(TestBrokerAdapter())
    gate.configure_tiny_live_pilot(
        allowed_instrument="XAUUSD", allowed_setup_family="continuation",
        size_cap=0.01, max_trades_per_day=8, daily_loss_cap=0.6, max_consecutive_losses=8,
    )
    gate.approve_tiny_live_pilot(note="isolated diagnostic")
    gate.activate_tiny_live_pilot()
    now = datetime.now(timezone.utc)
    # This scenario injects both deterministic prices and a fresh simulated
    # market clock. The real gate must not waive market-data freshness.
    trader.feed.last_fetch_meta = {
        "ok": True, "timestamp_basis": "UTC", "latest_tick_utc": now.isoformat(),
        "latest_bar_utc": now.isoformat(), "bar_stale_after_ms": 480000,
    }
    gate._session_control._sessions = [SessionWindow(
        name="test", start="00:00", end="23:59", timezone_name="UTC",
        no_trade_buffer_minutes=0, weekdays=tuple(range(7)),
    )]
    trader.execution_gate = gate
    trader.settings.max_weekly_drawdown = 0.05
    trader.settings.max_open_trades = 1
    trader.risk.evaluate = RiskManager(trader.settings).evaluate
    # Controlled entry evidence for the injected candidate; real timing check below.
    trader._derive_runtime_chart_features = lambda **kwargs: {
        "location_state": "pullback", "momentum_state": "strong",
        "trend_state": "uptrend", "trend_structure": "HH/HL", "setup_type_hint": "continuation",
    }
    def timing(signal, context, status=None):
        context = {**context, "entry_location_state": "pullback", "entry_momentum_state": "strong", "entry_trend_state": "uptrend"}
        return AtlasTrader._timing_discipline_snapshot(trader, signal, context, status)
    trader._timing_discipline_snapshot = timing
    return trader, store, gate


@pytest.mark.parametrize("daily_target", [0.0, 1000.0])
@pytest.mark.parametrize("daily_progress", [0.0, 1000.0])
def test_injected_valid_candidate_reaches_real_gate_and_simulated_broker(tmp_path, daily_target, daily_progress):
    trader, store, gate = _configured_pipeline(tmp_path)
    trader.settings.daily_profit_target_zar = daily_target
    snapshot = default_replay_scenarios()[2].risk_snapshot
    trader._risk_snapshot = lambda *args, **kwargs: replace(snapshot, equity=10000.0 + daily_progress, balance=10000.0 + daily_progress)
    with patch("atlas_ai.trader.mt5.account_info", return_value=SimpleNamespace(login=123456)), \
         patch("atlas_ai.trader.mt5.symbol_info", return_value=SimpleNamespace(trade_tick_value=1.0)), \
         patch("atlas_ai.trader.mt5.order_send", side_effect=AssertionError("Real broker submission forbidden")), \
         patch("atlas_ai.trader.evaluate_heartbeat_state", return_value={"is_stale": False}):
        status = trader.step()
    print({"action": status.get("action"), "message": status.get("message"), "chosen": status.get("chosen"), "approval": status.get("guarded_demo_auto_approval"), "execution": status.get("execution")})
    assert status["timing_discipline"]["passed"] is True
    assert status["execution"]["success"] is True
    assert status["guarded_demo_auto_approval"]["approved"] is True
    assert status["daily_profit_objective"]["target_zar"] == daily_target
    assert status["daily_profit_objective"]["guaranteed"] is False
    assert status["daily_profit_objective"]["force_trades"] is False
    reached = daily_target > 0 and daily_progress >= daily_target
    assert status["daily_profit_objective"]["reached"] is reached
    assert bool(status.get("profit_protection_mode", {}).get("active")) is reached
    unprotected, _ = AtlasTrader._volume_multiplier(trader, {}, {})
    protected, _ = AtlasTrader._volume_multiplier(trader, {"protect_gains_mode": True}, {})
    assert protected < unprotected
    sample = next(row["meta"] for row in reversed(store.events) if row["type"] == "decision_sample")
    assert sample["request_origin"] == "trader_guarded"
    assert sample["execution_mode"] == "demo"
    assert "broker_order_id" in sample
    assert any(row["event"] == "order_submit_attempt" for row in gate.recent_audit(limit=100))


@pytest.mark.parametrize("blocker", [None, "risk", "timing", "htf"])
def test_advisory_only_gemini_cannot_veto_or_adjust_guarded_candidate(tmp_path, blocker):
    trader, store, gate = _configured_pipeline(tmp_path)
    baseline, _, _ = _configured_pipeline(tmp_path / "baseline")
    # A persisted explicit operator choice takes precedence over an enabled
    # environment default, and the advisor remains available for commentary.
    trader.settings.gemini_influence_enabled = True
    trader.settings.daily_profit_target_zar = 1000.0
    store.save_runtime_flags({**store.load_runtime_flags(), "gemini_influence_enabled": False})
    trader.gemini.enabled = True
    trader.gemini.health_summary = lambda: {"enabled": True, "providers": []}
    influence = Mock(return_value={"veto": True, "confidence_delta": -.9, "reason": "AI must not decide this trade"})
    trader.gemini.influence_trade_decision = influence
    commentary = Mock(return_value="Advisory note only")
    trader.gemini.summarize_market_context = commentary
    if blocker == "risk":
        trader.risk.evaluate = lambda snapshot: (False, "deterministic risk veto")
    elif blocker == "timing":
        trader._timing_discipline_snapshot = lambda *args: {"hard_block": True, "missing": ["tradable_location"], "detail": "Timing needs a tradable location"}
    elif blocker == "htf":
        trader.settings.require_higher_tf_alignment = True
        trader._higher_tf_context = lambda: {"bias": "sell"}
    with patch("atlas_ai.trader.mt5.account_info", return_value=SimpleNamespace(login=123456)), \
         patch("atlas_ai.trader.mt5.symbol_info", return_value=SimpleNamespace(trade_tick_value=1.0)), \
         patch("atlas_ai.trader.mt5.order_send", side_effect=AssertionError("Real broker submission forbidden")), \
         patch("atlas_ai.trader.evaluate_heartbeat_state", return_value={"is_stale": False}):
        status = trader.step()
        baseline_status = baseline.step() if blocker is None else None
    influence.assert_not_called()
    assert status["gemini_influence_enabled"] is False
    assert "gemini_influence" not in status
    if blocker is None:
        assert status["execution"]["success"] is True
        # Compare against the same deterministic pipeline without Gemini.
        # Other valid adjustments can vary with the market session/date.
        assert status["chosen"]["confidence"] == pytest.approx(baseline_status["chosen"]["confidence"])
        commentary.assert_called_once()
    else:
        assert status["action"] in {"hold", "blocked"}
        assert not status.get("execution", {}).get("success", False)
        assert not any(row["event"] == "order_submit_attempt" for row in gate.recent_audit(limit=100))


@pytest.mark.parametrize("blocker", [None, "risk", "timing", "kill_switch", "htf", "pilot_family", "sizing"])
def test_pipeline_through_production_adapter_and_executor_with_fake_mt5(tmp_path, monkeypatch, blocker):
    from atlas_ai.execution.mt5_broker_adapter import MT5BrokerAdapter
    from atlas_ai.execution.trade_executor import TradeExecutor

    trader, store, gate = _configured_pipeline(tmp_path)
    trader.settings.max_slippage_points = 20
    trader.settings.hfm_login = 123456
    trader.settings.hfm_server = "Demo"
    trader.executor = TradeExecutor(trader.settings)
    gate.set_broker_adapter(MT5BrokerAdapter(trader.executor))
    if blocker == "risk":
        trader._risk_snapshot = lambda runtime_flags=None: replace(default_replay_scenarios()[2].risk_snapshot, daily_loss_pct=.5)
    elif blocker == "timing":
        trader._timing_discipline_snapshot = lambda signal, context, status: AtlasTrader._timing_discipline_snapshot(
            trader, signal, {**context, "entry_location_state": "mid_range", "entry_momentum_state": "weak"}, status
        )
    elif blocker == "kill_switch":
        gate.activate_kill_switch(reason="isolated test")
    elif blocker == "htf":
        trader.settings.require_higher_tf_alignment = True
        trader._higher_tf_context = lambda: {"bias": "sell"}
    elif blocker == "pilot_family":
        gate.configure_tiny_live_pilot(allowed_instrument="XAUUSD", allowed_setup_family="breakout", size_cap=.01, max_trades_per_day=8, daily_loss_cap=.6, max_consecutive_losses=8)

    if blocker == "sizing":
        trader.risk.lot_size = lambda *args, **kwargs: 0.0

    symbol = SimpleNamespace(trade_tick_value=1., point=.01, digits=2, trade_mode=4, visible=True, volume_min=.01, volume_max=100., volume_step=.01, trade_stops_level=10, filling_mode=1)
    sent = []
    def fake_send(request):
        sent.append(dict(request))
        return SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE, order=321, deal=654, comment="fake filled")

    monkeypatch.setattr(mt5, "account_info", lambda: SimpleNamespace(login=123456, server="Demo", trade_mode=0, equity=10000., margin_free=10000., trade_allowed=True))
    monkeypatch.setattr(mt5, "symbol_info", lambda symbol_name: symbol)
    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol_name: SimpleNamespace(ask=3320.20, bid=3320.00))
    monkeypatch.setattr(mt5, "terminal_info", lambda: SimpleNamespace(connected=True, trade_allowed=True))
    monkeypatch.setattr(mt5, "positions_get", lambda **kwargs: [])
    monkeypatch.setattr(mt5, "orders_get", lambda **kwargs: [])
    monkeypatch.setattr(mt5, "symbol_select", lambda *args: True)
    monkeypatch.setattr(mt5, "order_calc_margin", lambda *args: 10.)
    monkeypatch.setattr(mt5, "order_calc_profit", lambda *args: -1.)
    monkeypatch.setattr(mt5, "order_check", lambda request: SimpleNamespace(retcode=0, comment="fake checked"))
    monkeypatch.setattr(mt5, "order_send", fake_send)
    monkeypatch.setattr("atlas_ai.trader.evaluate_heartbeat_state", lambda *args, **kwargs: {"is_stale": False})
    monkeypatch.setattr("atlas_ai.market_context._fresh_external_context_fields", lambda: {})
    status = trader.step()
    if blocker is None:
        assert status["execution"]["success"] is True, (status.get("execution"), gate.snapshot().get("execution_truth"))
        assert len(sent) == 1
        assert sent[0]["volume"] == .01
        assert sent[0]["sl"] < sent[0]["price"] < sent[0]["tp"]
        request_id = status["guarded_demo_auto_approval"]["request_id"]
        gate.execute(request_id, runtime_flags={"execute_trades": True}, risk_policy={})
        assert len(sent) == 1  # Repeating the request cannot send another order.
    else:
        assert status.get("action") in {"blocked", "hold"}, status.get("message")
        assert not sent, status.get("message")


@pytest.mark.parametrize("volume", [.001, .000001])
def test_small_volume_keeps_precision_through_guarded_request(tmp_path, monkeypatch, volume):
    trader, store, gate = _configured_pipeline(tmp_path)
    trader.settings.daily_profit_target_zar = 0
    trader.risk.lot_size = lambda *args, **kwargs: volume
    trader._volume_multiplier = lambda *args: (1.0, "isolated sizing test")
    trader._size_band_multiplier = lambda *args: (1.0, {})
    monkeypatch.setattr("atlas_ai.trader.mt5.account_info", lambda: SimpleNamespace(login=123456))
    monkeypatch.setattr("atlas_ai.trader.mt5.symbol_info", lambda _: SimpleNamespace(
        trade_tick_value=1, point=.01, trade_tick_size=.01, volume_min=volume, volume_step=volume))
    monkeypatch.setattr("atlas_ai.trader.evaluate_heartbeat_state", lambda *args, **kwargs: {"is_stale": False})
    status = trader.step()
    assert status["execution"]["success"] is True, status.get("message")
    request = gate.get_request(status["guarded_demo_auto_approval"]["request_id"])
    assert request["size"] == volume
    assert any(row["event"] == "order_submit_attempt" for row in gate.recent_audit(limit=100))


def test_large_account_proposal_respects_existing_auto_approval_cap(tmp_path, monkeypatch):
    trader, store, gate = _configured_pipeline(tmp_path)
    trader.settings.daily_profit_target_zar = 0
    snapshot = default_replay_scenarios()[2].risk_snapshot
    trader._risk_snapshot = lambda *args, **kwargs: replace(snapshot, equity=120000, balance=120000)
    trader.risk.lot_size = lambda *args, **kwargs: .1
    trader._volume_multiplier = lambda *args: (1.0, "isolated sizing test")
    trader._size_band_multiplier = lambda *args: (1.0, {})
    monkeypatch.setattr("atlas_ai.trader.mt5.account_info", lambda: SimpleNamespace(login=123456))
    monkeypatch.setattr("atlas_ai.trader.mt5.symbol_info", lambda _: SimpleNamespace(
        trade_tick_value=1, point=.01, trade_tick_size=.01, volume_min=.01, volume_step=.01))
    monkeypatch.setattr("atlas_ai.trader.evaluate_heartbeat_state", lambda *args, **kwargs: {"is_stale": False})
    status = trader.step()
    assert status["execution"]["success"] is True, status.get("message")
    request = gate.get_request(status["guarded_demo_auto_approval"]["request_id"])
    assert request["size"] == trader._GUARDED_DEMO_MAX_LOT == .01
    assert status["guarded_demo_size_cap"]["applied"] is True
    assert status["guarded_demo_size_cap"]["proposed_lot"] == .1
