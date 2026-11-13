"""Local receipts for a real post-reboot Windows Startup-folder invocation."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import psutil

from atlas_ai.atomic_files import atomic_json


def baseline(storage):
    path = Path(storage) / "startup_verification/baseline.json"
    if not path.exists():
        atomic_json(path, {"schema": "atlas_startup_baseline_v1", "boot_time": psutil.boot_time(),
                           "installed_at": datetime.now(timezone.utc).isoformat()})


def record(storage, started_at, exit_code, *, at_logon=False, boot_time=None):
    storage = Path(storage)
    health = {}; path = storage / "atlas_fullstack_startup_result.json"
    # Reusing an old successful run must never establish a new boot's health.
    try:
        if path.stat().st_mtime >= started_at.timestamp() and path.stat().st_size <= 16*1024*1024:
            value = json.loads(path.read_text(encoding="utf-8"))
            candidate = value.get("health") or {}
            checked = datetime.fromisoformat(candidate.get("checked_at", "").replace("Z", "+00:00"))
            if checked.tzinfo is not None and checked >= started_at:
                health = {key: candidate.get(key) for key in ("checked_at", "overall_result", "overall_reason")}
    except (OSError, ValueError, TypeError, AttributeError): pass
    receipt = {"schema": "atlas_startup_receipt_v1", "started_at": started_at.isoformat(),
               "finished_at": datetime.now(timezone.utc).isoformat(), "exit_code": exit_code,
               "boot_time": psutil.boot_time() if boot_time is None else boot_time,
               "startup_folder_invocation": bool(at_logon), "health": health}
    atomic_json(storage / "startup_verification" / ("last_logon.json" if at_logon else "last_manual.json"), receipt)
    return receipt


def verify(storage, *, boot_time=None):
    folder = Path(storage) / "startup_verification"
    current = psutil.boot_time() if boot_time is None else boot_time
    try:
        initial = json.loads((folder / "baseline.json").read_text())
        initial_boot = float(initial["boot_time"])
        if not math.isfinite(initial_boot) or not math.isfinite(current) or initial_boot <= 0 or current <= 0:
            raise ValueError("invalid_boot_identity")
        if current <= initial_boot + 1:
            return {"state": "pending_reboot", "verified": False}
        receipt = json.loads((folder / "last_logon.json").read_text())
        verified = (receipt.get("schema") == "atlas_startup_receipt_v1"
                    and abs(float(receipt["boot_time"]) - current) < 2
                    and receipt.get("startup_folder_invocation") is True and receipt.get("exit_code") == 0
                    and (receipt.get("health") or {}).get("overall_result") == "SUCCESS")
        return {"state": "post_reboot_startup_verified" if verified else "startup_health_review_required",
                "verified": verified, "receipt": receipt}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"state": "startup_receipt_unavailable", "verified": False}
