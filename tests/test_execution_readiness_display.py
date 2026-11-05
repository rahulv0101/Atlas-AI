from datetime import datetime, timezone, timedelta

import pytest

from atlas_ai.ui_server import _build_execution_readiness


def evaluate(*, action="hold", message="No directional trade signal selected.", timing=False, automation=None, timestamp=None):
    status = {"action": action, "message": message, "blocker_class": "signal_quality", "timing_discipline": {"hard_block": timing, "missing": ["tradable_location"] if timing else []}, "system_health": {"broker_connectivity_status": {"connected": True, "symbol_selected": True}}}
    if timestamp:
        status["updated_at"] = timestamp
    execution = {"automation_enabled": True, "automation_paused": False, "auto_trade_allowed": True, "session_control": {"session_active": True}}
    execution.update(automation or {})
    return _build_execution_readiness(status, {"execute_trades": True}, execution)


def test_no_signal_is_waiting_instead_of_system_failure():
    result = evaluate()
    assert result["display"]["label"] == "WAITING"
    assert not result["ready"]
    assert "No directional" in result["display"]["detail"]


def test_screenshot_timing_rejection_is_a_wait_for_setup():
    result = evaluate(action="blocked", message="Timing discipline blocked trade: Waiting for clean entry timing: tradable location, strong/turning M1 momentum, and visual confirmation missing (location=mid_range, momentum=mixed, session=asia).", timing=True)
    assert result["display"]["label"] == "WAITING"
    assert not result["ready"]
    assert "mid_range" in result["display"]["detail"]


@pytest.mark.parametrize("automation", [
    {"kill_switch_active": True}, {"reconciliation_required": True},
    {"automation_paused": True}, {"automation_enabled": False},
    {"forced_flat_pending": True},
])
def test_directional_candidate_never_masks_operational_block(automation):
    result = evaluate(action="buy", automation=automation)
    assert not result["ready"]
    assert result["display"]["label"] == "BLOCKED"


def test_directional_candidate_still_requires_timing_and_session():
    assert not evaluate(action="buy", timing=True)["ready"]
    result = evaluate(action="buy", automation={"session_control": {"session_active": False}})
    assert not result["ready"]
    assert result["display"]["label"] == "WAITING"


@pytest.mark.parametrize("delta", [-300, 60])
def test_stale_or_future_decision_never_claims_readiness(delta):
    timestamp = (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat()
    result = evaluate(action="buy", timestamp=timestamp)
    assert not result["ready"]
    assert result["display"]["label"] == "BLOCKED"


def test_valid_candidate_is_eligible_for_gates_not_a_claim_of_fill():
    result = evaluate(action="buy")
    assert result["ready"]
    assert result["display"]["label"] == "READY"
    assert "not a fill confirmation" in result["display"]["detail"]
