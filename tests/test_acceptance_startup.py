from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import acceptance_startup as module


@pytest.fixture
def plan(tmp_path,monkeypatch):
    value={"deadline":"2026-12-10T19:51:19+00:00","storage_dir":str(tmp_path),"python":"python.exe"}
    monkeypatch.setattr(module,"checked_plan",lambda path:value)
    return tmp_path/"acceptance_plan.json"


def test_expired_plan_cannot_launch_anything(plan):
    launch=Mock(side_effect=AssertionError("Expired plan cannot start"))
    result=module.resume(plan,now=datetime(2026,12,11,tzinfo=timezone.utc),start=launch)
    assert result["state"]=="deadline_reached" and result["orders_sent"]==0


def test_existing_supervisor_is_reused(plan,monkeypatch):
    monkeypatch.setattr(module.supervisor,"busy",lambda *args:True)
    launch=Mock(side_effect=AssertionError("No duplicate"))
    result=module.resume(plan,now=datetime(2026,11,11,tzinfo=timezone.utc),start=launch)
    assert result["state"]=="supervisor_already_running"


def test_resume_only_launches_read_only_supervisor(plan,monkeypatch):
    monkeypatch.setattr(module.supervisor,"busy",lambda *args:False)
    launch=Mock(return_value=SimpleNamespace(pid=123))
    result=module.resume(plan,now=datetime(2026,11,11,tzinfo=timezone.utc),start=launch)
    command=launch.call_args.args[0]
    assert command[1]==str(module.ROOT/"tools/supervise_acceptance.py")
    assert command[2:]==["watch","--plan",str(plan.resolve())]
    assert "--execute" not in command and result["orders_sent"]==0


def test_corrupt_plan_is_rejected_before_settings_or_launch(tmp_path):
    path=tmp_path/"plan.json";path.write_text("{}")
    path.with_suffix(".sha256").write_text("bad")
    with pytest.raises(ValueError,match="plan_changed"):module.checked_plan(path)


def test_shortcut_uses_current_user_folder_hidden_python_and_quoted_paths(tmp_path):
    python=tmp_path/"python.exe";python.with_name("pythonw.exe").touch()
    code=module.shortcut_script("install",tmp_path/"plan.json",root=Path("C:/Atlas's Folder"),python=python)
    assert "GetFolderPath('Startup')" in code and "pythonw.exe" in code
    assert "Atlas''s Folder" in code and "WindowStyle=7" in code
    assert "resume" in code and "--plan" in code
    assert "atlas_ai.main" not in code and "RunLevel" not in code
    removal=module.shortcut_script("remove",tmp_path/"plan.json",python=python)
    assert "Remove-Item -LiteralPath $path" in removal and "-Recurse" not in removal
