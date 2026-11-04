from pathlib import Path
from types import SimpleNamespace

import pytest

import atlas_ai.atlas_wake_config as wake_config


@pytest.mark.parametrize("filename", ["atlas_wake_config.json", "atlas_wake_config.json.example"])
def test_shipped_wake_config_resolves_local_paths_from_another_directory(tmp_path, monkeypatch, filename):
    source = Path(__file__).resolve().parents[1] / filename
    project = tmp_path / "Atlas AI"
    project.mkdir()
    (project / "atlas_wake_config.json").write_bytes(source.read_bytes())
    executable = project / ".venv" / "Scripts" / "python.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(wake_config, "_project_root", lambda: project)
    monkeypatch.setattr(wake_config, "load_settings", lambda: SimpleNamespace(hfm_terminal_path="terminal64.exe"))
    for key in ("ATLAS_WAKE_PYTHON", "ATLAS_AUDIO_MODEL_PATH", "ATLAS_WAKE_COMPARISON_ROOT"):
        monkeypatch.delenv(key, raising=False)

    config = wake_config.load_atlas_wake_config()

    assert Path(config.python_executable) == executable
    assert Path(config.audio_model_path) == project / "models" / "vosk-model-small-en-us-0.15"
    assert Path(config.comparison_root) == project / "storage_compare_runs"
    assert config.backend_launch_command[0] == str(executable)
    assert config.frontend_launch_command[0] == str(executable)
    assert config.launch_profile == ("guarded_demo" if filename.endswith(".json") else "paper_compare")


def test_quoted_windows_launch_command_keeps_executable_and_arguments_intact():
    command = r'"C:\Atlas AI\.venv\Scripts\python.exe" -m atlas_ai.main ui --comparison-root "C:\Atlas AI\runs"'
    assert wake_config._as_command(command) == [
        r"C:\Atlas AI\.venv\Scripts\python.exe", "-m", "atlas_ai.main", "ui",
        "--comparison-root", r"C:\Atlas AI\runs",
    ]


@pytest.mark.parametrize("configured, environment, expected", [
    (False, "true", False), (True, "false", True), ("false", "true", False),
])
def test_explicit_clap_setting_takes_precedence_over_environment(monkeypatch, tmp_path, configured, environment, expected):
    monkeypatch.setattr(wake_config, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(wake_config, "_load_json_config", lambda root: {"audio_clap_enabled": configured})
    monkeypatch.setattr(wake_config, "load_settings", lambda: SimpleNamespace(hfm_terminal_path="terminal64.exe"))
    monkeypatch.setenv("ATLAS_AUDIO_CLAP_ENABLED", environment)

    assert wake_config.load_atlas_wake_config().audio_clap_enabled is expected
