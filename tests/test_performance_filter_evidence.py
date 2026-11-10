from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from atlas_ai.learning.performance_filter_evidence import confirmed_demo_statistics
from atlas_ai.learning.online_allocator import StrategyState
from atlas_ai.models import TradeSignal
from atlas_ai.trader import AtlasTrader


def evidence(rows=None):
    return {"schema": "atlas_closed_position_ledger_v1", "available": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "strategy_statistics": rows or {}}


def trader(source="allocator_rewards"):
    obj = AtlasTrader.__new__(AtlasTrader)
    obj.settings = NS(win_rate_focus_enabled=True, min_strategy_samples=8,
                      min_strategy_win_rate=.35, strategy_filter_evidence_source=source)
    obj.legacy_stats = {"ema_crossover": StrategyState(wins=100, losses=600, pnl=-100)}
    obj.allocator = NS(stats=lambda: obj.legacy_stats)
    obj._closed_position_evidence = evidence()
    return obj


def signal():
    return TradeSignal("ema_crossover", "buy", .6, 100, 160)


def test_legacy_default_still_excludes_legacy_weak_strategy():
    obj = trader()
    kept, reasons = obj._filter_weak_strategies([signal()])
    assert kept == [] and "severe_blocked" in reasons[0]


def test_confirmed_policy_does_not_invent_losses_from_open_rewards():
    obj = trader("confirmed_demo_positions")
    original = deepcopy(obj.legacy_stats)
    candidate = signal()
    kept, reasons = obj._filter_weak_strategies([candidate])
    assert kept == [candidate] and reasons == []
    assert obj.legacy_stats == original
    assert candidate.confidence == .6


def test_confirmed_bad_results_still_exclude_strategy():
    obj = trader("confirmed_demo_positions")
    obj._closed_position_evidence = evidence({"ema_crossover": {"wins": 1, "losses": 9, "pnl": -10}})
    kept, reasons = obj._filter_weak_strategies([signal()])
    assert kept == [] and "wr=0.10" in reasons[0]


def test_confirmed_good_results_override_legacy_reward_veto_only():
    obj = trader("confirmed_demo_positions")
    obj._closed_position_evidence = evidence({"ema_crossover": {"wins": 8, "losses": 2, "pnl": 10}})
    assert obj._filter_weak_strategies([signal()])[1] == []


@pytest.mark.parametrize("change", [
    {"available": False}, {"schema": "invalid"}, {"updated_at": "bad"},
    {"updated_at": "2026-01-01T00:00:00"},
    {"timestamp_offset_minutes": -4},
    {"timestamp_offset_minutes": 4},
    {"strategy_statistics": None},
    {"strategy_statistics": {"ema_crossover": {"wins": -1, "losses": 2, "pnl": 1}}},
    {"strategy_statistics": {"ema_crossover": {"wins": True, "losses": 2, "pnl": 1}}},
    {"strategy_statistics": {"ema_crossover": {"wins": 1, "losses": 2, "pnl": float("nan")}}},
])
def test_unavailable_or_invalid_confirmed_evidence_fails_closed(change):
    obj = trader("confirmed_demo_positions")
    change = dict(change)
    if "timestamp_offset_minutes" in change:
        change["updated_at"] = (datetime.now(timezone.utc) + timedelta(minutes=change.pop("timestamp_offset_minutes"))).isoformat()
    obj._closed_position_evidence.update(change)
    kept, reasons = obj._filter_weak_strategies([signal()])
    assert kept == [] and reasons[0].startswith("confirmed_evidence_")


def test_unknown_policy_fails_closed():
    obj = trader("typo")
    assert obj._filter_weak_strategies([signal()]) == ([], ["strategy_filter_evidence_source_invalid"])


def test_explicit_shadow_statistics_do_not_depend_on_active_source():
    obj = trader("confirmed_demo_positions")
    obj._closed_position_evidence = None
    candidate = signal()
    assert obj._filter_weak_strategies([candidate], statistics={}) == ([candidate], [])
