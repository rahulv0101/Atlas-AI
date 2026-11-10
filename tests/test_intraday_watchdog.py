from types import SimpleNamespace as NS
from atlas_ai.execution.intraday_watchdog import IntradayExitWatchdog


class Store:
    def __init__(self):self.flags={"execute_trades":True,"unrelated":"preserved"}
    def load_runtime_flags(self):return dict(self.flags)
    def update_runtime_flags(self,fn):self.flags=fn(dict(self.flags))


def test_watchdog_polls_exit_independently_and_preserves_controls():
    calls=[];store=Store()
    gate=NS(enforce_intraday_exit=lambda **kwargs:(calls.append(kwargs) or {"state":"flat_verified","flat_verified":True}))
    worker=IntradayExitWatchdog(gate,store)
    assert worker.tick()["flat_verified"]
    assert len(calls)==1 and store.flags["unrelated"]=="preserved"
    store.flags["execute_trades"]=False
    assert worker.tick()["state"]=="disabled_by_runtime" and len(calls)==1


def test_watchdog_reports_failure_without_claiming_flat():
    store=Store()
    def fail(**kwargs):raise RuntimeError("test")
    worker=IntradayExitWatchdog(NS(enforce_intraday_exit=fail),store,.01)
    worker.start();worker.stop_event.wait(.04);worker.stop()
    assert store.flags["intraday_exit_watchdog"]["state"]=="watchdog_error"
    assert not store.flags["intraday_exit_watchdog"]["flat_verified"]
    assert not worker.thread.is_alive()
