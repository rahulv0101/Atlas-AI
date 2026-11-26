from datetime import datetime, timezone
import json

from atlas_ai.atomic_files import atomic_json
from atlas_ai.startup_verification import record, verify


def test_native_windows_boot_clock_is_stable_and_cached(monkeypatch):
    from types import SimpleNamespace
    from atlas_ai import startup_verification as module
    calls = []
    module.boot_clock.cache_clear()
    monkeypatch.setattr(module.os, 'name', 'nt')
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: calls.append(k) or SimpleNamespace(stdout='2026-11-23T08:15:00.5000000Z\n'))
    try:
        first = module.boot_clock()
        assert first == module.boot_clock()
        assert first[1] == 'windows_last_boot_up_time'
        assert len(calls) == 1 and calls[0]['timeout'] == 10
    finally:
        module.boot_clock.cache_clear()


def test_native_boot_clock_failure_keeps_strict_fallback(monkeypatch):
    from atlas_ai import startup_verification as module
    module.boot_clock.cache_clear()
    def fail(*a, **k):
        raise module.subprocess.TimeoutExpired('powershell', 10)
    monkeypatch.setattr(module.os, 'name', 'nt')
    monkeypatch.setattr(module.subprocess, 'run', fail)
    monkeypatch.setattr(module.psutil, 'boot_time', lambda: 123.)
    try:
        assert module.boot_clock() == (123., 'psutil_fallback')
    finally:
        module.boot_clock.cache_clear()


def test_same_boot_never_counts_as_reboot_verification(tmp_path):
    atomic_json(tmp_path / "startup_verification/baseline.json", {"boot_time": 100})
    assert verify(tmp_path, boot_time=100) == {"state": "pending_reboot", "verified": False}


def test_old_success_and_manual_launch_do_not_prove_post_reboot_logon(tmp_path):
    atomic_json(tmp_path / "startup_verification/baseline.json", {"boot_time": 100})
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    atomic_json(tmp_path / "atlas_fullstack_startup_result.json", {"health": {
        "checked_at": old.isoformat(), "overall_result": "SUCCESS"}})
    receipt = record(tmp_path, datetime.now(timezone.utc), 0, at_logon=True, boot_time=200)
    assert not receipt["health"]
    assert not verify(tmp_path, boot_time=200)["verified"]
    record(tmp_path, old, 0, at_logon=False, boot_time=200)
    assert not verify(tmp_path, boot_time=200)["verified"]


def test_fresh_successful_logon_on_new_boot_can_be_verified(tmp_path):
    atomic_json(tmp_path / "startup_verification/baseline.json", {"boot_time": 100})
    now = datetime.now(timezone.utc)
    atomic_json(tmp_path / "atlas_fullstack_startup_result.json", {"health": {
        "checked_at": now.isoformat(), "overall_result": "SUCCESS"}})
    record(tmp_path, now, 0, at_logon=True, boot_time=200)
    assert verify(tmp_path, boot_time=200)["verified"]
    assert not verify(tmp_path, boot_time=300)["verified"]


def test_invalid_boot_identity_cannot_prove_a_reboot(tmp_path):
    atomic_json(tmp_path / "startup_verification/baseline.json", {"boot_time": "nan"})
    assert not verify(tmp_path, boot_time=200)["verified"]
