"""Process-scoped Windows idle-sleep inhibition for the live trading worker."""
from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import logging
import os
from pathlib import Path

from atlas_ai.atomic_files import atomic_json

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def live_power_guard(storage_dir, *, native=None, enabled=None):
    """Leave display/manual sleep policy alone; release on the acquiring thread."""
    enabled = (os.getenv("ATLAS_PREVENT_IDLE_SLEEP", "1").lower() not in {"0", "false", "off"}
               if enabled is None else enabled)
    state = {"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(),
             "scope": "live_worker_lifetime", "display_required": False,
             "manual_sleep_prevented": False, "active": False}
    setter = None
    previous = None
    def publish():
        try:
            atomic_json(Path(storage_dir) / "runtime_power" / f"power_{os.getpid()}.json", state)
        except Exception:
            logging.warning("Could not publish runtime power evidence", exc_info=True)
    try:
        if enabled and (native is not None or os.name == "nt"):
            kernel = native if native is not None else ctypes.windll.kernel32
            setter = kernel.SetThreadExecutionState
            setter.argtypes = [ctypes.c_uint32]
            setter.restype = ctypes.c_uint32
            previous = setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            if not previous:
                raise OSError("SetThreadExecutionState failed")
            state.update(active=True, state="idle_sleep_inhibited")
        else:
            state["state"] = "disabled" if not enabled else "unsupported_platform"
    except Exception as exc:
        state.update(state="power_request_failed", error=type(exc).__name__)
        logging.warning("Atlas cannot inhibit automatic sleep: %s", type(exc).__name__)
    publish()
    try:
        yield state
    finally:
        if state["active"]:
            try:
                if not setter(previous | ES_CONTINUOUS):
                    raise OSError("power request release failed")
                state.update(active=False, state="released")
            except Exception as exc:
                state.update(state="power_release_failed", error=type(exc).__name__)
                logging.warning("Atlas power request release failed: %s", type(exc).__name__)
        state["ended_at"] = datetime.now(timezone.utc).isoformat()
        publish()
