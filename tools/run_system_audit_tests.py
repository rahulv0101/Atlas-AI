"""Run the suite with isolated storage, no real AI keys, and durable progress.

Normal pytest/native fault handling remains enabled. Progress is recorded by
Python hooks rather than timer-based all-thread native stack walking.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "diagnostics" / "test_audit")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="atlas-test-audit-")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    import pytest

    class Progress:
        def pytest_runtest_logstart(self, nodeid, location):
            row = {"test": nodeid, "started_at": datetime.now(timezone.utc).isoformat()}
            (out / "current_test.json").write_text(json.dumps(row), encoding="utf-8")

        def pytest_runtest_logreport(self, report):
            if report.when == "call":
                row = {"test": report.nodeid, "outcome": report.outcome, "seconds": report.duration}
                with (out / "test_results.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")

    extra = args.pytest_args
    if extra[:1] == ["--"]:
        extra = extra[1:]
    result = pytest.main(["-q", f"--junitxml={out / 'tests.xml'}", *extra], plugins=[Progress()])
    (out / "summary.json").write_text(json.dumps({"exit_code": int(result)}), encoding="utf-8")
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
