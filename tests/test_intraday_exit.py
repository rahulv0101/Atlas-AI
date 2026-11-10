from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from atlas_ai.execution.intraday_exit import IntradayExitManager
from atlas_ai.execution.broker_adapter import BrokerOrderResponse
from atlas_ai.execution.execution_gate import ExecutionGate
from atlas_ai.execution.session_control import SessionWindow

NOW = datetime(2026, 11, 9, 10, 5, tzinfo=timezone.utc)


def position(ticket="P", owned=True, status="open"):
    return dict(broker_order_id=ticket, status=status, owned_by_atlas=owned, size=.01)


class Broker:
    def __init__(self, rows):
        self.rows = rows
        self.sent = []
        self.unknown = False
        self.bad_inventory = False
        self.race = False

    def intraday_inventory(self):
        if self.bad_inventory:
            raise RuntimeError("unavailable")
        return deepcopy(self.rows)

    def cancel_order(self, *, broker_order_id):
        self.sent.append(("cancel", broker_order_id))
        self.rows = [r for r in self.rows if r["broker_order_id"] != broker_order_id]
        if self.race:
            self.rows.append(position("FILLED"))
            return BrokerOrderResponse(False, "unknown", broker_order_id)
        return BrokerOrderResponse(True, "cancelled", broker_order_id)

    def close_position(self, *, position_id):
        self.sent.append(("close", position_id))
        if self.unknown:
            return BrokerOrderResponse(False, "unknown", position_id)
        self.rows = [r for r in self.rows if r["broker_order_id"] != position_id]
        return BrokerOrderResponse(True, "closed", position_id)

    def query_order_status(self, *, broker_order_id):
        return BrokerOrderResponse(True, "filled", broker_order_id)


def run(manager, broker, cutoff=True, allowed=True):
    return manager.run(broker, cutoff_required=cutoff, actions_allowed=allowed, reason="cutoff", now=NOW)


def test_cancel_before_close_and_confirm_owned_flat_only(tmp_path):
    broker = Broker([position(), position("Q", status="pending"), position("MANUAL", owned=False)])
    manager = IntradayExitManager(tmp_path / "exit.json")
    result = run(manager, broker)
    assert broker.sent == [("cancel", "Q"), ("close", "P")]
    assert result["flat_verified"] is True and result["entries_blocked"] is True
    assert result["unmanaged_exposure_count"] == 1
    assert broker.rows[0]["broker_order_id"] == "MANUAL"
    assert run(manager, broker)["flat_verified"] is True
    assert len(broker.sent) == 2


def test_unknown_close_survives_restart_without_duplicate(tmp_path):
    broker = Broker([position()]); broker.unknown = True
    path = tmp_path / "exit.json"
    assert not run(IntradayExitManager(path), broker)["flat_verified"]
    assert not run(IntradayExitManager(path), broker)["flat_verified"]
    assert broker.sent == [("close", "P")]
    broker.rows = []
    assert run(IntradayExitManager(path), broker)["flat_verified"]


def test_inventory_failure_is_not_flat_and_blocks_other_process(tmp_path):
    manager = IntradayExitManager(tmp_path / "exit.json")
    broker = Broker([]); broker.bad_inventory = True
    assert not run(manager, broker)["flat_verified"]
    assert manager.block_reason()


def test_cancel_fill_race_requeries_and_closes_new_position(tmp_path):
    broker = Broker([position("Q", status="pending")]);broker.race = True
    result = run(IntradayExitManager(tmp_path / "exit.json"), broker)
    assert broker.sent == [("cancel", "Q"), ("close", "FILLED")]
    assert result["flat_verified"] is True


def test_no_mutation_while_safety_controls_block_actions(tmp_path):
    broker = Broker([position()]);manager=IntradayExitManager(tmp_path / "exit.json")
    result=run(manager, broker, allowed=False)
    assert result["entries_blocked"] and not result["flat_verified"]
    assert not broker.sent


def test_next_active_session_clears_completed_cutoff_barrier(tmp_path):
    manager=IntradayExitManager(tmp_path / "exit.json");broker=Broker([])
    assert run(manager,broker)["entries_blocked"]
    assert not run(manager,broker,cutoff=False)["entries_blocked"]


def test_overnight_catchup_runs_even_in_active_session(tmp_path):
    row=position();row["opened_at_utc"]="2026-11-08T20:00:00+00:00"
    broker=Broker([row]);result=run(IntradayExitManager(tmp_path / "exit.json"),broker,cutoff=False)
    assert broker.sent == [("close","P")] and result["flat_verified"]


def test_corrupt_journal_preserves_unknown_actions_and_blocks(tmp_path):
    path=tmp_path / "exit.json";path.write_text("bad")
    manager=IntradayExitManager(path);broker=Broker([position()])
    assert not run(manager,broker)["flat_verified"]
    assert path.read_text()=="bad" and not broker.sent and manager.block_reason()


@pytest.mark.parametrize("control", ["kill", "sleep", "gate", "runtime"])
def test_gate_safety_controls_prevent_cutoff_mutation(tmp_path, control):
    gate=ExecutionGate(state_store_path=str(tmp_path / "automation.json"))
    gate.set_execution_environment("demo");gate.set_gate_enabled(True)
    broker=Broker([position()]);gate.set_broker_adapter(broker)
    gate._session_control._sessions=[SessionWindow("test","09:00","10:00","UTC")]
    if control=="kill":gate.activate_kill_switch(reason="test")
    if control=="sleep":gate.activate_sleep_mode(reason="test")
    if control=="gate":gate.set_gate_enabled(False)
    result=gate.enforce_intraday_exit(runtime_flags={"execute_trades":control!="runtime"},now=NOW)
    assert not broker.sent and result["entries_blocked"]


def test_daily_trade_limit_cannot_hide_missed_close_and_recovery_barrier(tmp_path):
    gate=ExecutionGate(state_store_path=str(tmp_path / "automation.json"))
    gate.set_execution_environment("demo");gate.set_gate_enabled(True)
    broker=Broker([position()]);gate.set_broker_adapter(broker)
    gate._session_control._sessions=[SessionWindow("test","09:00","10:00","UTC")]
    result=gate.enforce_intraday_exit(runtime_flags={"execute_trades":True,"day_trade_count":999},now=NOW)
    assert result["flat_verified"] and broker.sent==[("close","P")]
    other=ExecutionGate(state_store_path=str(tmp_path / "automation.json"))
    assert other._intraday_exit_manager().block_reason()


def test_second_process_kill_switch_between_cancel_and_close_is_respected(tmp_path):
    path=str(tmp_path / "automation.json")
    gate=ExecutionGate(state_store_path=path);gate.set_execution_environment("demo");gate.set_gate_enabled(True)
    other=ExecutionGate(state_store_path=path)
    broker=Broker([position(),position("Q",status="pending")]);gate.set_broker_adapter(broker)
    original=broker.cancel_order
    def cancel(**kwargs):
        result=original(**kwargs);other.activate_kill_switch(reason="operator");return result
    broker.cancel_order=cancel
    gate._session_control._sessions=[SessionWindow("test","09:00","10:00","UTC")]
    result=gate.enforce_intraday_exit(runtime_flags={"execute_trades":True},now=NOW)
    assert broker.sent==[("cancel","Q")] and not result["flat_verified"]


def test_two_controllers_cannot_duplicate_a_close(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path=tmp_path / "exit.json";broker=Broker([position()])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:run(IntradayExitManager(path),broker),range(2)))
    assert all(r["flat_verified"] for r in results)
    assert broker.sent==[("close","P")]


def test_partial_close_uses_only_verified_remaining_volume(tmp_path):
    broker=Broker([position()]);sent=[]
    def close(*,position_id):
        sent.append(broker.rows[0]["size"])
        if len(sent)==1:
            broker.rows[0]["size"]=.005
            return BrokerOrderResponse(False,"partially_closed",position_id)
        broker.rows=[]
        return BrokerOrderResponse(True,"closed",position_id)
    broker.close_position=close;manager=IntradayExitManager(tmp_path / "exit.json")
    assert not run(manager,broker)["flat_verified"]
    assert run(manager,broker)["flat_verified"]
    assert sent==[.01,.005]


def test_missed_exit_obligation_survives_new_session_even_without_a_dispatch(tmp_path):
    manager=IntradayExitManager(tmp_path / "exit.json");broker=Broker([position()])
    assert run(manager,broker,allowed=False)["exit_in_progress"]
    resumed=run(manager,broker,cutoff=False,allowed=True)
    assert resumed["flat_verified"] and broker.sent==[("close","P")]


def test_exit_view_uses_newer_watchdog_confirmation_and_preserves_monitor_errors():
    from atlas_ai.ui_server import _intraday_exit_view
    old={"intraday_exit":{"checked_at":"2026-11-09T20:00:00+00:00","flat_verified":True}}
    new={"intraday_exit":{"checked_at":"2026-11-09T20:01:00+00:00","flat_verified":False,"entries_blocked":True}}
    assert _intraday_exit_view(old,new)==new["intraday_exit"]
    broken={"intraday_exit":{"state":"exit_monitor_error","entries_blocked":True,"flat_verified":False}}
    assert _intraday_exit_view(old,broken)==broken["intraday_exit"]


def test_dashboard_reads_fresh_exit_journal_independently_of_strategy_cycle(tmp_path):
    from atlas_ai.ui_server import _load_automation_payload
    from types import SimpleNamespace
    import json
    (tmp_path / "automation_state.json").write_text(json.dumps({"payload":{"gate_enabled":True}}))
    manager=IntradayExitManager(tmp_path / "automation_state.intraday_exit.json")
    result=run(manager,Broker([]))
    loaded=_load_automation_payload(SimpleNamespace(base=tmp_path))
    assert loaded["gate_enabled"] and loaded["intraday_exit"]==result
    manager.path.write_text("corrupt")
    assert not _load_automation_payload(SimpleNamespace(base=tmp_path))["intraday_exit"]["flat_verified"]
