import json

import pytest

from tools.repair_event_journal import repair_lfs_journal


POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 12345\n"


def test_repair_preserves_pointer_and_declares_history_gap(tmp_path):
    journal = tmp_path / "events.jsonl"
    journal.write_bytes(POINTER)
    result = repair_lfs_journal(tmp_path)
    assert result["status"] == "reinitialized"
    assert result["recovered"] is False
    assert (tmp_path / result["pointer_backup"]).read_bytes() == POINTER
    event = json.loads(journal.read_text())
    assert event["type"] == "system"
    assert event["meta"]["repair_state"] == "initialized"
    assert event["meta"]["expected_bytes"] == 12345
    assert json.loads((tmp_path / "event_history_gap.json").read_text())["recovered"] is False
    assert repair_lfs_journal(tmp_path)["status"] == "unchanged"
    assert len(list((tmp_path / "archive").glob("*.pointer"))) == 1


def test_ordinary_journal_is_never_rewritten(tmp_path):
    journal = tmp_path / "events.jsonl"
    original = b'{"type":"decision","message":"original"}\n'
    journal.write_bytes(original)
    assert repair_lfs_journal(tmp_path)["status"] == "unchanged"
    assert journal.read_bytes() == original
    assert not (tmp_path / "event_history_gap.json").exists()


def test_pointer_with_appended_records_is_not_truncated(tmp_path):
    journal = tmp_path / "events.jsonl"
    original = POINTER + b'{"type":"decision"}\n'
    journal.write_bytes(original)
    with pytest.raises(ValueError, match="appended data"):
        repair_lfs_journal(tmp_path)
    assert journal.read_bytes() == original


def test_existing_manifest_requires_review_before_second_repair(tmp_path):
    journal = tmp_path / "events.jsonl"
    journal.write_bytes(POINTER)
    manifest = tmp_path / "event_history_gap.json"
    manifest.write_text('{"recovered":false,"original":true}')
    with pytest.raises(FileExistsError):
        repair_lfs_journal(tmp_path)
    assert journal.read_bytes() == POINTER
    assert json.loads(manifest.read_text())["original"] is True


def test_existing_local_lfs_object_prevents_reinitialization(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "events.jsonl").write_bytes(POINTER)
    oid = "a" * 64
    cached = tmp_path / ".git" / "lfs" / "objects" / "aa" / "aa" / oid
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"recoverable data")
    with pytest.raises(RuntimeError, match="available locally"):
        repair_lfs_journal(storage)
    assert (storage / "events.jsonl").read_bytes() == POINTER
