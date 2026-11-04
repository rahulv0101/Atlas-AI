from __future__ import annotations

from pathlib import Path

from atlas_ai.testing.replay_harness import (
    ReplayDiffError,
    assert_behavior_matches_baseline,
    default_replay_scenarios,
    load_replay_baselines,
    run_replay_scenario,
)


def test_replay_harness_matches_behavior_baselines():
    baseline_path = Path(__file__).parent / "fixtures" / "replay_baselines.json"
    baselines = load_replay_baselines(baseline_path)

    for scenario in default_replay_scenarios():
        actual = run_replay_scenario(scenario)
        assert_behavior_matches_baseline(scenario.name, actual, baselines[scenario.name])


def test_replay_harness_reports_exact_diffs():
    actual = {
        "action": "paper",
        "execution": {"success": False},
    }
    baseline = {
        "action": "blocked",
        "execution": {"success": False},
    }

    try:
        assert_behavior_matches_baseline("demo", actual, baseline)
        assert False, "expected ReplayDiffError"
    except ReplayDiffError as exc:
        text = str(exc)
        assert "scenario=demo" in text
        assert "action: expected 'blocked', got 'paper'" in text


def test_replay_is_isolated_from_current_macro_data_and_refresh(monkeypatch):
    from unittest.mock import Mock
    from atlas_ai.trader import AtlasTrader

    live_context = Mock(return_value={"dxy_alignment": "conflict", "us10y_alignment": "supportive", "vix_regime": "elevated"})
    refresh = Mock(side_effect=AssertionError("Replay attempted a live macro refresh"))
    monkeypatch.setattr("atlas_ai.market_context._fresh_external_context_fields", live_context)
    monkeypatch.setattr(AtlasTrader, "_maybe_refresh_external_macro_context", refresh)
    baseline = load_replay_baselines(Path(__file__).parent / "fixtures" / "replay_baselines.json")
    scenario = default_replay_scenarios()[0]
    actual = run_replay_scenario(scenario)
    assert_behavior_matches_baseline(scenario.name, actual, baseline[scenario.name])
    live_context.assert_not_called()
    refresh.assert_not_called()
