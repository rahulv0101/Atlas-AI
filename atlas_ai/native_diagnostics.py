"""Keep native fault traces in a process-specific file for later diagnosis."""
import faulthandler
import atexit
from importlib import metadata
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

_TRACE_STREAM = None


def _runtime_versions():
    versions={}
    for package in ("MetaTrader5","numpy","pandas","pythonnet","pywebview"):
        try:
            versions[package]=metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package]=None
    return versions


def _mark_orderly_exit(stream):
    try:
        if not stream.closed:
            stream.write(json.dumps({"orderly_python_exit_at":datetime.now(timezone.utc).isoformat()})+"\n")
            stream.flush()
    except Exception:
        pass


def enable_native_diagnostics(storage_dir, mode):
    global _TRACE_STREAM
    if faulthandler.is_enabled():
        return {"enabled": True, "existing_handler": True}
    folder = Path(storage_dir) / "native_crashes"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"native_{os.getpid()}.log"
    stream = path.open("a", encoding="utf-8", buffering=1)
    try:
        stream.write(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
            "python": sys.version.split()[0], "mode": mode, "architecture":platform.machine(),
            "native_dependency_versions":_runtime_versions(),
            "exit_marker_note":"Missing orderly exit marker alone does not establish a native crash; forced termination also bypasses Python cleanup."}) + "\n")
        faulthandler.enable(file=stream, all_threads=True)
    except Exception:
        stream.close()
        raise
    # The stream must remain open for the entire process lifetime. OS teardown
    # closes it; early atexit cleanup could lose a fault during shutdown.
    _TRACE_STREAM = stream
    atexit.register(_mark_orderly_exit,stream)
    return {"enabled": True, "path": str(path)}
