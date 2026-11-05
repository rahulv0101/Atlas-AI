from types import SimpleNamespace

from atlas_ai.models import TradeSignal
from atlas_ai.trader import AtlasTrader


def test_generation_records_candidate_before_filter_without_changing_result():
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = SimpleNamespace(timeframe="M1", backtest_include_evolved=False)
    context = {"session": "london", "allowed_session": True, "regime": "range", "volatility_state": "low", "trend_strength": .02}
    trader._signal_generation_context = lambda df: context
    trader._load_chromosome_demo_pool = lambda: []
    trader.base_strategies = [SimpleNamespace(name="pullback_trend", generate_signal=lambda df: TradeSignal("pullback_trend", "buy", .7, 100, 150))]

    signals = trader._build_signals(None)
    assert [(s.side, s.confidence) for s in signals] == [("flat", 0)]
    trace = trader._signal_generation_diagnostics
    assert trace["directional_before_filters"] == 1
    assert trace["directional_after_filters"] == 0
    assert trace["suppressed_count"] == 1
    row = trace["candidates"][0]
    assert row["before_filters"] == {"side": "buy", "confidence": .7}
    assert row["after_filters"] == {"side": "flat", "confidence": 0}
    assert row["reason_codes"] == ["low_energy_directional_suppression"]

    trader.base_strategies = []
    assert trader._build_signals(None) == []
    assert trader._signal_generation_diagnostics["candidates"] == []
    assert row["before_filters"]["side"] == "buy"  # Prior evidence remains intact.


def test_flat_strategy_is_distinct_from_suppressed_directional_candidate():
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = SimpleNamespace(timeframe="M1")
    evidence = {}
    result = trader._apply_signal_generation_gating(TradeSignal("example", "flat", 0, 100, 150), {}, diagnostics=evidence)
    assert result.side == "flat"
    assert evidence["reason_codes"] == ["strategy_returned_flat"]


def test_new_signal_evidence_reaches_published_status_and_decision_event():
    from atlas_ai.testing.replay_harness import _build_trader, default_replay_scenarios
    from unittest.mock import patch

    trader, store = _build_trader(default_replay_scenarios()[0])
    trader._signal_generation_diagnostics = {"schema": "test", "candidates": [{"before_filters": {"side": "buy"}}]}
    with patch("atlas_ai.trader.evaluate_heartbeat_state", return_value={"is_stale": False}), patch("atlas_ai.market_context._fresh_external_context_fields", return_value={}):
        trader.step()
    assert store.saved_status["signal_generation"] == trader._signal_generation_diagnostics
    assert store.saved_status["decision_trace"]["signal"]["raw_stage"] == "after_signal_generation_filters"
    assert store.events[-1]["meta"]["signal_generation"] == trader._signal_generation_diagnostics
