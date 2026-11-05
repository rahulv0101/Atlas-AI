import time

import pytest

from atlas_ai.execution.execution_gate import ExecutionGate


@pytest.mark.parametrize("ok,reason", [(True, ""), (False, "approval_missing"), (False, "broker_rejected:invalid_volume")])
def test_all_old_execution_results_are_historical_without_erasing_audit(ok, reason):
    gate = ExecutionGate()
    saved = {"ok": ok, "reason": reason, "request_id": "old", "ts": time.time() - 86400}
    gate._last_execution_truth = saved.copy()
    truth = gate.snapshot()["execution_truth"]
    assert truth["stale"] is True
    assert truth["current"] is False
    assert truth["reason"] == reason
    assert truth["ok"] is ok
    assert gate._last_execution_truth == saved


def test_active_matching_request_remains_current_but_unrelated_request_does_not():
    gate = ExecutionGate()
    gate._last_execution_truth = {"request_id": "old", "ts": time.time() - 86400}
    gate._active_request_id = "old"
    assert gate.snapshot()["execution_truth"]["current"] is True
    gate._active_request_id = "new"
    assert gate.snapshot()["execution_truth"]["current"] is False


def test_current_runtime_source_wins_over_historical_simulation_display():
    gate = ExecutionGate()
    gate.set_execution_environment("demo")
    gate._last_autonomy_cycle = {"simulation_market_state": True, "ts": time.time() - 86400}
    gate._last_gate_decision = {"allowed": True, "ts": time.time() - 86400}
    snapshot = gate.snapshot(runtime_flags={"data_source": "broker_runtime"})
    assert snapshot["mode_separation"]["market_state_mode"] == "broker_runtime"
    assert snapshot["gate_decisions_last_cycle"]["current"] is False
    assert snapshot["gate_decisions_last_cycle"]["allowed"] is True  # Historical result retained.
    assert gate.snapshot()["mode_separation"]["market_state_mode"] == "unknown"
    assert gate.snapshot(runtime_flags={"data_source": "simulation"})["mode_separation"]["market_state_mode"] == "simulation"
