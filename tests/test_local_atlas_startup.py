from pathlib import Path

import pytest
import importlib.machinery
import importlib.util

from tools.install_atlas_startup import shortcut_script


def test_installer_uses_local_hidden_launcher_and_windows_known_folders(tmp_path):
    root = tmp_path / "Atlas's Project"
    (root / ".venv/Scripts").mkdir(parents=True)
    (root / ".venv/Scripts/pythonw.exe").touch()
    (root / "atlas_fullstack_startup.pyw").touch()
    script = shortcut_script(root)
    assert "GetFolderPath($item.folder)" in script
    assert "Start Atlas.lnk" in script and "Atlas Full System.lnk" in script
    assert "pythonw.exe" in script and "atlas_fullstack_startup.pyw" in script
    assert "WindowStyle=7" in script and "Atlas''s Project" in script
    assert "schtasks" not in script and "runas" not in script
    assert "execute_trades" not in script and "mode-override" not in script


def test_missing_environment_is_reported_instead_of_installing_broken_shortcut(tmp_path):
    with pytest.raises(FileNotFoundError): shortcut_script(tmp_path)


@pytest.fixture
def launcher(monkeypatch):
    import os
    for key in ("PATH", "VIRTUAL_ENV"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    path = Path(__file__).resolve().parents[1] / "atlas_fullstack_startup.pyw"
    loader = importlib.machinery.SourceFileLoader("atlas_startup_test", str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def test_duplicate_detection_is_scoped_and_unknown_inspection_blocks(launcher, monkeypatch):
    calls = []
    def process_rows(mode, **kwargs):
        calls.append((mode, kwargs["project_root"]))
        return [{"pid": 1}]
    monkeypatch.setattr("atlas_ai.runtime_processes.atlas_mode_processes", process_rows)
    assert launcher._is_core_stack_running()
    assert calls == [("live", launcher.ROOT), ("ui", launcher.ROOT)]
    monkeypatch.setattr("atlas_ai.runtime_processes.atlas_mode_processes", lambda *a, **kw: None)
    with pytest.raises(RuntimeError): launcher._is_core_stack_running()


def test_existing_observation_plan_resumes_without_changing_trading(launcher, tmp_path, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    (tmp_path / "storage").mkdir()
    (tmp_path / "storage/acceptance_plan.json").write_text("{}")
    resume = Mock(return_value={"state": "supervisor_already_running"})
    monkeypatch.setattr("tools.acceptance_startup.resume", resume)
    launcher._ensure_acceptance_observation()
    resume.assert_called_once_with(tmp_path / "storage/acceptance_plan.json")


def test_simultaneous_shortcut_clicks_do_not_launch_twice(launcher, tmp_path, monkeypatch):
    from unittest.mock import Mock
    from atlas_ai.learning.observation_checkpoint import observation_lock
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "_setup_logging", lambda: None)
    monkeypatch.setattr(launcher.os, "chdir", lambda *args: None)
    start = Mock(side_effect=AssertionError("Duplicate startup"))
    monkeypatch.setattr(launcher, "_start", start)
    with observation_lock(tmp_path / "storage/atlas_fullstack_startup.lock"):
        assert launcher.main() == 0
    start.assert_not_called()
