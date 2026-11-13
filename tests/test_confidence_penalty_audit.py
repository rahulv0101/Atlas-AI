from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from atlas_ai.testing.confidence_penalty_audit import audit, make_trader, trace_candidate


def settings():
    return SimpleNamespace(timeframe="M1", learning_mode=False)


def context():
    return {"session": "london", "allowed_session": True, "regime": "trend", "trend_strength": .2, "volatility_state": "normal",
            "entry_location_state": "consolidation", "entry_momentum_state": "weak", "entry_wickiness": .6,
            "entry_expansion": 0., "entry_position": .5}


def payload():
    return {"state": {"historical_loss_analysis": {"source": "historical_backtest",
        "generated_at": "2020-01-01T00:00:00+00:00", "sampled_loss_count": 55,
        "patterns": {"classification": [{"value": "stop_hunt", "count": 55}]},
        "loss_samples": [{"ticket": "bt_1", "outcome": "loss"}]}, "loss_memory": {"pattern_lessons": {}, "recent_outcomes": []}}}


def candidate():
    return {"strategy": "ema_crossover", "before_filters": {"side": "buy", "confidence": .5},
            "after_filters": {"side": "buy", "confidence": .43}}


def test_reconstructs_existing_haircut_without_mutating_state_or_inputs():
    state = payload(); ctx = context(); raw = candidate(); originals = deepcopy((state, ctx, raw))
    traced = trace_candidate(settings(), state, ctx, raw)
    assert traced["heuristic_multiplier"] == pytest.approx(.86)
    assert traced["replayed_confidence"] == pytest.approx(.43)
    assert (state, ctx, raw) == originals
    clean = trace_candidate(settings(), state, {**ctx, "entry_wickiness": .2}, raw)
    assert clean["replayed_confidence"] == .5


def test_audit_distinguishes_source_provenance_and_expiry_from_validated_benefit():
    state = payload()
    state["state"]["loss_memory"]["recent_outcomes"] = [
        {"ticket": "bt_2"}, {"ticket": "123"},
        {"ticket": "456", "strategy": "mabr", "decision_id": "manual", "outcome": "loss"}]
    status = {"signal_generation": {"context": context(), "candidates": [candidate()]}}
    result = audit(settings(), state, status, now=datetime(2026, 11, 13, tzinfo=timezone.utc))
    assert result["historical_count_source"]["age_days"] > 2000
    assert result["candidates"][0]["replay_matches_published"]
    assert result["candidates"][0]["count_sensitivity_only"][0]["count_removed"] == "stop_hunt"
    sources = result["retained_lesson_memory"]
    assert sources["raw_sources"]["manual_test"] == 1 and sources["effective_sources"]["manual_test"] == 0
    assert sources["effective_sources"]["broker_recorded"] == 1
    assert sources["broker_ticket_alone_proves_strategy_execution"] is False
    assert not result["validation"]["confidence_penalty_benefit_established"]
    assert result["policy_changes"] == [] and result["orders_sent"] == 0


def test_lesson_layer_is_reported_separately_and_depends_on_nonempty_global_counts():
    state = payload(); ctx = context(); trader = make_trader(settings(), state)
    fingerprint = trader._build_trade_pattern_fingerprint(strategy="ema_crossover", side="buy",
        setup_family=trader._strategy_to_setup_family("ema_crossover"), session="london", regime="trend", context=ctx)
    state["state"]["loss_memory"]["pattern_lessons"] = {fingerprint: {"fingerprint": fingerprint,
        "samples": 2, "losses": 2, "loss_rate": 1., "execution_lesson": {"classification": "stop_hunt"},
        "post_trade_lesson": {"failure_axis": "execution_friction"}}}
    result = trace_candidate(settings(), state, ctx, candidate())
    assert result["lesson"]["applied"] is True
    assert result["lesson"]["input_confidence"] == pytest.approx(.43)
    assert result["lesson"]["output_confidence"] < .43
    empty = trace_candidate(settings(), state, ctx, candidate(), count_override={})
    assert empty["replayed_confidence"] == .5 and "lesson" not in empty


def test_prior_regime_suppression_does_not_get_mislabelled_as_timing_penalty():
    ctx = {**context(), "regime": "range", "trend_strength": .01, "volatility_state": "low"}
    result = trace_candidate(settings(), payload(), ctx, candidate())
    assert result["replayed_side"] == "flat"
    assert "timing_input_confidence" not in result
