"""Preserve an unresolved LFS pointer and start a valid event journal offline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone


def repair_lfs_journal(storage_dir: Path) -> dict:
    base = Path(storage_dir).resolve()
    journal = base / "events.jsonl"
    if not journal.exists():
        return {"status": "unchanged", "reason": "journal_missing"}
    if journal.resolve().parent != base:
        raise ValueError("Journal must remain within the selected storage directory")
    with journal.open("rb") as stream:
        pointer = stream.read(4097)
    if not pointer.removeprefix(b"\xef\xbb\xbf").startswith(b"version https://git-lfs.github.com/spec/v1"):
        return {"status": "unchanged", "reason": "journal_is_not_an_lfs_pointer"}
    match = re.fullmatch(
        rb"(?:\xef\xbb\xbf)?version https://git-lfs.github.com/spec/v1\r?\n"
        rb"oid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)\r?\n?", pointer,
    )
    if match is None:
        raise ValueError("Pointer is invalid or has appended data; journal was left untouched")
    oid = match[1].decode("ascii")
    cached_object = base.parent / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4] / oid
    if cached_object.exists():
        raise RuntimeError("The LFS object is available locally; restore the original journal instead")
    manifest = base / "event_history_gap.json"
    if manifest.exists():
        raise FileExistsError("A history-gap manifest already exists; review it before repairing another pointer")
    archive = base / "archive"
    archive.mkdir(exist_ok=True)
    if archive.resolve().parent != base:
        raise ValueError("Archive must remain within the selected storage directory")
    fd, backup_name = tempfile.mkstemp(prefix="missing_events_lfs_", suffix=".pointer", dir=archive)
    backup = Path(backup_name)
    with os.fdopen(fd, "wb") as stream:
        stream.write(pointer)
        stream.flush()
        os.fsync(stream.fileno())
    stamp = datetime.now(timezone.utc).isoformat()
    gap = {
        "reason": "missing_lfs_object", "recovered": False,
        "oid": "sha256:" + oid, "expected_bytes": int(match[2]),
        "pointer_backup": str(backup.relative_to(base)), "recorded_at": stamp,
        "repair_state": "prepared",
    }
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(gap, stream, indent=2)
    event = {"time": stamp, "type": "system",
             "message": "Event journal reinitialized after unresolved LFS pointer; historical data remains unavailable.",
             "meta": {**gap, "repair_state": "initialized"}}
    fd, temp_name = tempfile.mkstemp(prefix="events_repair_", suffix=".tmp", dir=base)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if journal.read_bytes() != pointer:
            raise RuntimeError("Journal changed during repair; replacement was cancelled")
        os.replace(temporary, journal)
        gap["repair_state"] = "initialized"
        manifest.write_text(json.dumps(gap, indent=2) + "\n", encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "reinitialized", **gap}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-dir", type=Path, default=Path(__file__).resolve().parents[1] / "storage")
    args = parser.parse_args()
    if os.name == "nt":
        result = subprocess.run([
            "powershell", "-NoProfile", "-Command",
            "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match '-m\\s+atlas_ai\\.main\\s+(live|live-ui|ui|ui-server)(\\s|$)' }; if ($p) { exit 1 } else { exit 0 }",
        ], capture_output=True, check=False)
        if result.returncode != 0:
            parser.error("Atlas runtime is active or process inspection failed; journal repair requires it stopped")
    print(json.dumps(repair_lfs_journal(args.storage_dir), indent=2))


if __name__ == "__main__":
    main()
