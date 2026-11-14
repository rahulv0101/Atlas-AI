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


def test_saved_backend_only_preference_never_starts_desktop_or_audio(launcher,tmp_path,monkeypatch):
    import json
    from unittest.mock import Mock
    (tmp_path/'.venv/Scripts').mkdir(parents=True);(tmp_path/'.venv/Scripts/python.exe').touch()
    (tmp_path/'storage').mkdir()
    (tmp_path/'storage/operator_interface.json').write_text(json.dumps({'desktop_ui_enabled':False}))
    monkeypatch.setattr(launcher,'ROOT',tmp_path);monkeypatch.setattr(launcher,'VENV_ROOT',tmp_path/'.venv')
    launch=Mock(return_value={'health':{'overall_result':'SUCCESS'}})
    monkeypatch.setattr(launcher,'run_backend_launch',launch)
    forbidden=Mock(side_effect=AssertionError('Desktop/audio must stay down'))
    monkeypatch.setattr(launcher,'run_full_launch',forbidden);monkeypatch.setattr(launcher,'_ensure_audio_path',forbidden)
    monkeypatch.setattr(launcher,'_ensure_acceptance_observation',Mock())
    assert launcher._start()==0
    launch.assert_called_once();forbidden.assert_not_called()


def test_backend_launch_retains_readiness_gates_without_frontend(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from atlas_ai import atlas_full_launcher as full
    cfg=SimpleNamespace(launch_profile='guarded_demo')
    monkeypatch.setattr(full,'setup_logging',lambda c:None)
    for name in ['_validate_guarded_demo_commands','_start_mt5_if_needed','_wait_for_mt5','_start_backend_if_needed','_wait_for_backend']:
        monkeypatch.setattr(full,name,Mock(return_value=SimpleNamespace(status='healthy')))
    forbidden=Mock(side_effect=AssertionError('No frontend in backend-only operation'))
    monkeypatch.setattr(full,'_start_frontend_if_needed',forbidden)
    result=full.run_backend_launch(cfg)
    assert result['health']['overall_result']=='SUCCESS' and result['desktop_ui_enabled'] is False
    forbidden.assert_not_called()
    full._wait_for_mt5.return_value=SimpleNamespace(status='failed')
    full._start_backend_if_needed.reset_mock()
    result=full.run_backend_launch(cfg)
    assert result['health']['overall_result']=='FAILED'
    full._start_backend_if_needed.assert_not_called()
