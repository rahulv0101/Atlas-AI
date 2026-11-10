"""Keep cutoff handling independent of strategy-cycle latency."""
from datetime import datetime, timezone
import threading


class IntradayExitWatchdog:
    def __init__(self, gate, store, interval_seconds=15):
        self.gate=gate;self.store=store;self.interval=interval_seconds
        self.stop_event=threading.Event();self.thread=None

    def tick(self):
        flags=self.store.load_runtime_flags()
        if not flags.get("execute_trades"):
            result={"state":"disabled_by_runtime","flat_verified":False}
        else:
            result=self.gate.enforce_intraday_exit(runtime_flags=flags)
        payload={**result,"watchdog_checked_at":datetime.now(timezone.utc).isoformat()}
        self.store.update_runtime_flags(lambda current:{**current,"intraday_exit_watchdog":payload})
        return payload

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                try:
                    self.store.update_runtime_flags(lambda current:{**current,"intraday_exit_watchdog":{
                        "state":"watchdog_error","reason":type(exc).__name__,"flat_verified":False,
                        "watchdog_checked_at":datetime.now(timezone.utc).isoformat()}})
                except Exception:
                    pass
            self.stop_event.wait(self.interval)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self._run,name="atlas-intraday-exit",daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=5)
