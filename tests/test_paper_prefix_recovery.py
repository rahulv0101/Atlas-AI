import hashlib
import json

import pytest

from tools.recover_paper_prefix import recover


@pytest.fixture
def interrupted(tmp_path):
    original=b"time,close\n2026-11-13 07:00:00,4000.0\n"
    (tmp_path/"observer.lock").touch()
    manifest=b'{"schema":"frozen"}'
    (tmp_path/"manifest.json").write_bytes(manifest)
    (tmp_path/"manifest.sha256").write_text(hashlib.sha256(manifest).hexdigest())
    (tmp_path/"signals.json").write_bytes(b"{}")
    (tmp_path/"outcomes.json").write_bytes(b'["retained_loss"]')
    (tmp_path/"observed_candles.csv").write_bytes(original+b"2026-11-13 07:01:00,4001.0\n")
    (tmp_path/"artifacts.json").write_text(json.dumps({"observed_candles.csv":hashlib.sha256(original).hexdigest(),
        "signals.json":hashlib.sha256(b"{}").hexdigest()}))
    return tmp_path, original


def test_only_signed_prefix_can_be_restored_and_suffix_is_preserved(interrupted):
    folder,original=interrupted; before=(folder/"observed_candles.csv").read_bytes()
    assert recover(folder)["state"]=="verified_prefix_available"
    assert (folder/"observed_candles.csv").read_bytes()==before
    result=recover(folder,apply=True)
    assert (folder/"observed_candles.csv").read_bytes()==original
    assert (folder/"outcomes.json").read_bytes()==b'["retained_loss"]'
    from pathlib import Path
    assert (Path(result["backup"])/"observed_candles.csv").read_bytes()==before
    assert recover(folder)["state"]=="already_verified"


@pytest.mark.parametrize("name",["signals.json","manifest.json","observed_candles.csv"])
def test_changed_history_or_other_artifacts_are_not_blessed(interrupted,name):
    folder,_=interrupted
    (folder/name).write_bytes(b"unverified")
    with pytest.raises(ValueError): recover(folder,apply=True)
    assert (folder/name).read_bytes()==b"unverified"
