from types import SimpleNamespace

import pandas as pd
import pytest

from atlas_ai.analysis.entry_confirmation import resolve_retest_timing_context
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.minute_pack import GoldBreakoutRetestStrategy
from atlas_ai.trader import AtlasTrader


def frame(side="buy", confirmed=True):
    rows = [{"open": 99.2, "high": 100.0, "low": 98.0, "close": 99.5, "tick_volume": 100} for _ in range(38)]
    values = [
        (100.1, 101.7, 100.0, 101.5), (100.2, 100.6, 99.9, 100.4),
        (100.4, 101.0, 100.2, 100.8), (100.7, 101.4, 100.6, 101.1),
        (101.0, 101.6, 100.9, 101.4), (101.0, 102.3, 100.9, 102.1),
    ]
    if not confirmed:
        values = [(101.0 + i * .3, 101.7 + i * .3, 100.95 + i * .3, 101.5 + i * .3) for i in range(6)]
    for o, h, l, c in values:
        rows.append({"open": o, "high": h, "low": l, "close": c, "tick_volume": 120})
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2026-01-05T08:00:00Z", periods=len(df), freq="min")
    if side == "sell":
        original = df.copy()
        df["open"], df["close"] = 200 - original["open"], 200 - original["close"]
        df["high"], df["low"] = 200 - original["low"], 200 - original["high"]
    return df


def timing(signal, context, status=None):
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = SimpleNamespace(timing_allow_mid_range_strong_momentum=False)
    return trader._timing_discipline_snapshot(signal, context, status or {})


def context():
    return {"entry_location_state": "breakout", "entry_momentum_state": "strong",
            "trend_state": "uptrend", "trend_strength": .3, "session": "london", "setup_type_hint": "breakout"}


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_current_ordered_retest_resolves_label_but_preserves_original_context(side):
    df = frame(side)
    strategy = GoldBreakoutRetestStrategy()
    signal = strategy.generate_signal(df)
    assert signal.side == side
    original = context()
    assert timing(signal, original)["passed"] is False
    resolved, resolution = resolve_retest_timing_context(signal, df, original, [strategy])
    assert original["entry_location_state"] == "breakout"
    assert resolved["entry_location_state"] == "retest"
    assert resolution["applied"] is True
    proof = resolution["evidence"]
    assert proof["breakout_index"] < proof["retest_index"]
    assert proof["signal_bar_time"] == str(df["time"].iloc[-1])
    assert timing(signal, resolved)["passed"] is True


def test_saved_confirmation_cannot_authorize_a_new_unconfirmed_frame():
    strategy = GoldBreakoutRetestStrategy()
    signal = strategy.generate_signal(frame())
    original = {**context(), "saved_entry_confirmation": strategy.confirmed_entry_evidence(frame(), "buy")}
    resolved, resolution = resolve_retest_timing_context(signal, frame(confirmed=False), original, [strategy])
    assert resolution["applied"] is False
    assert timing(signal, resolved)["passed"] is False


@pytest.mark.parametrize("location,strategy_name", [("mid_range", "gold_breakout_retest"), ("breakout", "gold_micro_impulse")])
def test_proof_adapter_does_not_relax_other_locations_or_strategies(location, strategy_name):
    signal = TradeSignal(strategy_name, "buy", .9, 100, 145)
    original = {**context(), "entry_location_state": location}
    resolved, resolution = resolve_retest_timing_context(signal, frame(), original, [GoldBreakoutRetestStrategy()])
    assert resolved == original
    assert resolution["applied"] is False


def test_valid_retest_still_requires_momentum_and_visual_confirmation():
    strategy = GoldBreakoutRetestStrategy()
    signal = strategy.generate_signal(frame())
    resolved, _ = resolve_retest_timing_context(signal, frame(), context(), [strategy])
    assert timing(signal, {**resolved, "entry_momentum_state": "weak"})["passed"] is False
    visual = {"visual_chart_read": {"visual_watch_used_for_decision": True, "visual_confirmation": "does_not_confirm"}}
    result = timing(signal, resolved, visual)
    assert result["passed"] is False
    assert "visual_confirmation" in result["missing"]


def test_flat_signal_does_not_claim_clean_entry_timing():
    result = timing(TradeSignal("gold_breakout_retest", "flat", 0, 100, 145), context())
    assert result["hard_block"] is False
    assert "not applicable" in result["detail"]
    assert "not an entry approval" in result["detail"]


def test_retest_before_breakout_is_not_accepted_as_ordered_confirmation():
    df = frame()
    values = [(99.7, 100.0, 99.6, 99.8), (99.9, 100.1, 99.8, 100.0),
              (99.9, 100.1, 99.8, 100.05), (101.0, 101.8, 100.95, 101.6),
              (101.6, 102.3, 101.3, 102.0), (102.0, 103.6, 101.9, 103.3)]
    for offset, values_row in enumerate(values):
        df.loc[len(df) - 6 + offset, ["open", "high", "low", "close"]] = values_row
    strategy = GoldBreakoutRetestStrategy()
    signal = strategy.generate_signal(df)
    assert signal.side == "buy"  # Existing signal generation is deliberately preserved.
    assert strategy.confirmed_entry_evidence(df, "buy") is None
    resolved, resolution = resolve_retest_timing_context(signal, df, context(), [strategy])
    assert resolution["applied"] is False
    assert timing(signal, resolved)["passed"] is False


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "unordered"])
def test_invalid_bar_times_cannot_supply_confirmation(invalid):
    df = frame()
    if invalid == "missing":
        df = df.drop(columns="time")
    elif invalid == "duplicate":
        df.loc[len(df) - 1, "time"] = df["time"].iloc[-2]
    else:
        df.loc[len(df) - 1, "time"] = df["time"].iloc[0]
    assert GoldBreakoutRetestStrategy().confirmed_entry_evidence(df, "buy") is None


def test_trader_step_uses_current_strategy_evidence_before_timing(monkeypatch):
    from dataclasses import replace
    from unittest.mock import patch
    from atlas_ai.testing.replay_harness import _build_trader, default_replay_scenarios

    strategy = GoldBreakoutRetestStrategy()
    df = frame()
    signal = strategy.generate_signal(df)
    scenario = replace(default_replay_scenarios()[0], chosen_signal=signal,
                       raw_signals=[signal], active_signals=[signal], higher_tf_bias="buy")
    monkeypatch.setenv("ATLAS_TTS_ENABLED", "false")
    trader, store = _build_trader(scenario)
    trader.strategies = [strategy]
    trader.feed = SimpleNamespace(get_rates=lambda bars: df.copy())
    trader._derive_runtime_chart_features = lambda **kwargs: {
        "location_state": "breakout", "momentum_state": "strong", "trend_state": "uptrend",
        "trend_structure": "HH/HL", "setup_type_hint": "breakout", "reliability": "high",
    }
    trader._timing_discipline_snapshot = lambda chosen, ctx, status: AtlasTrader._timing_discipline_snapshot(trader, chosen, ctx, status)
    with patch("atlas_ai.trader.mt5.order_send", side_effect=AssertionError("Real order forbidden")), \
         patch("atlas_ai.trader.mt5.symbol_info", return_value=SimpleNamespace(trade_tick_value=1.0)), \
         patch("atlas_ai.trader.evaluate_heartbeat_state", return_value={"is_stale": False}):
        status = trader.step()
    assert status["entry_location_resolution"]["applied"] is True
    assert status["entry_location_resolution"]["original_location"] == "breakout"
    assert status["timing_discipline"]["observed"]["location"] == "retest"
    assert status["timing_discipline"]["passed"] is True
