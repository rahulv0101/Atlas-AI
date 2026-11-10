import json
from pathlib import Path
import subprocess
import sys

from tools.reproduce_traceback_race import CHILD


def test_plain_reproducer_workload_is_real_and_cannot_import_broker_or_atlas(tmp_path):
    trace=tmp_path/"plain.log"
    result=subprocess.run([sys.executable,"-I","-S","-c",CHILD,"plain","1",str(trace)],
        cwd=tmp_path,capture_output=True,text=True,timeout=15)
    assert result.returncode==0 and not result.stderr
    payload=json.loads(result.stdout)
    assert payload["successful_workers"]>0 and payload["iterations"]>0 and payload["worker_errors"]==[]
    assert payload["atlas_or_broker_imported"] is False
    assert json.loads(trace.read_text().splitlines()[0])["pid"]==payload["pid"]


def test_supported_audit_runner_does_not_use_unsafe_timer_or_disable_fatal_traces(tmp_path,monkeypatch):
    import faulthandler
    import pytest
    from tools import run_system_audit_tests as runner
    def forbidden(*args,**kwargs):raise AssertionError("Unsafe diagnostic instrumentation")
    monkeypatch.setattr(faulthandler,"dump_traceback_later",forbidden)
    monkeypatch.setattr(faulthandler,"disable",forbidden)
    monkeypatch.setattr(pytest,"main",lambda *args,**kwargs:0)
    for name in ("GEMINI_API_KEY","OPENAI_API_KEY","STORAGE_DIR"):
        monkeypatch.setenv(name,"isolated-test-value")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(runner.ROOT))
    assert runner.main(["--output-dir",str(tmp_path)])==0
    assert json.loads((tmp_path/"summary.json").read_text())["exit_code"]==0
