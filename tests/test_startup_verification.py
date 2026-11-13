from datetime import datetime, timezone
import json

from atlas_ai.atomic_files import atomic_json
from atlas_ai.startup_verification import record, verify


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
