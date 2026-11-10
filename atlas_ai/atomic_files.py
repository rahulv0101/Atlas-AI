"""Atomic JSON publication that tolerates short Windows reader locks."""
import contextlib
import json
import os
from pathlib import Path
import tempfile
import time


def replace_with_retry(source, target):
    for attempt in range(12):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(min(.01 * (attempt + 1), .1))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(name, path)
    finally:
        with contextlib.suppress(OSError):
            Path(name).unlink(missing_ok=True)
