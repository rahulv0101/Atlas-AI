from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from atlas_ai.data.freshness import execution_freshness
from atlas_ai.execution.execution_gate import ExecutionGate
from atlas_ai.trader import AtlasTrader

NOW = datetime(2026, 11, 5, 8, tzinfo=timezone.utc)


def market():
    return {"ok": True, "timestamp_basis": "UTC", "latest_tick_utc": (NOW-timedelta(seconds=1)).isoformat(), "latest_bar_utc": (NOW-timedelta(seconds=30)).isoformat(), "bar_stale_after_ms": 480000}


@pytest.mark.parametrize("key,value", [
    ("latest_tick_utc", (NOW-timedelta(minutes=3)).isoformat()),
    ("latest_bar_utc", (NOW-timedelta(minutes=9)).isoformat()),
    ("latest_tick_utc", (NOW+timedelta(minutes=1)).isoformat()),
    ("latest_tick_utc", ""), ("latest_bar_utc", "2026-11-05 08:00:00"),
    ("timestamp_basis", "unknown"), ("bar_stale_after_ms", float("nan")),
])
def test_fresh_cycle_cannot_authorize_stale_or_unverified_market_data(key, value):
    data = market();data[key] = value
    freshness = execution_freshness(status_age_ms=100, market_fetch=data, now=NOW)
    assert freshness["is_stale"]
    result = ExecutionGate()._check_runtime_freshness({"freshness_runtime": freshness, "max_freshness_age_ms": 120000}, strict=True)
    assert not result["ok"]


def test_market_age_is_recomputed_at_submission_instead_of_trusting_fetch_age():
    assert not execution_freshness(status_age_ms=1, market_fetch=market(), now=NOW)["is_stale"]
    assert execution_freshness(status_age_ms=1, market_fetch=market(), now=NOW+timedelta(minutes=3))["is_stale"]


@pytest.mark.parametrize("age", [None, -1, float("nan"), float("inf"), 120001])
def test_invalid_cycle_age_is_never_fresh(age):
    assert execution_freshness(status_age_ms=age)["is_stale"]


def test_forward_journal_retains_risk_distances_and_clock_for_counterfactuals():
    trader = AtlasTrader.__new__(AtlasTrader)
    trader._current_cycle_timing = {"market_fetch": market()}
    record = trader._compact_runtime_event_meta({"chosen": {"strategy": "test", "side": "buy", "stop_loss_points": 110, "take_profit_points": 170}}, "risk")
    assert record["chosen"]["stop_loss_points"] == 110
    assert record["chosen"]["take_profit_points"] == 170
    assert record["market_data_clock"]["timestamp_basis"] == "UTC"
