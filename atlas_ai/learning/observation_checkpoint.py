"""Durable, account-scoped observer evidence; no order or promotion authority."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from atlas_ai.atomic_files import atomic_json


def account_scope(settings):
    fields=(settings.hfm_login,settings.hfm_server,settings.symbol,settings.magic_number)
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


@contextmanager
def observation_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a+b") as stream:
        if not path.stat().st_size:stream.write(b"0");stream.flush()
        stream.seek(0)
        if os.name=="nt":
            import msvcrt
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise RuntimeError("lifecycle_observer_already_running") from exc
        else:
            import fcntl
            try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:raise RuntimeError("lifecycle_observer_already_running") from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=="nt":msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def save_checkpoint(path,settings,baseline,seen,managed,summary,*,journal=None):
    atomic_json(path,{"schema":"atlas_lifecycle_observation_checkpoint_v1","scope":account_scope(settings),
        "baseline":sorted(baseline) if baseline is not None else None,"seen":seen,
        "observed_protected_positions":sorted(managed),"summary":summary,
        "journal":str(Path(journal).resolve()) if journal is not None else None,"orders_sent":0})


def load_checkpoint(path,settings,*,journal=None):
    row=json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(row,dict) or row.get("schema")!="atlas_lifecycle_observation_checkpoint_v1"
            or row.get("scope")!=account_scope(settings) or row.get("orders_sent")!=0):
        raise ValueError("invalid_or_wrong_account_observation_checkpoint")
    if journal is not None and row.get("journal")!=str(Path(journal).resolve()):
        raise ValueError("observation_checkpoint_journal_mismatch")
    baseline=row.get("baseline");seen=row.get("seen");managed=row.get("observed_protected_positions")
    if (baseline is not None and (not isinstance(baseline,list) or any(not isinstance(v,str) for v in baseline))
            or not isinstance(seen,dict) or not isinstance(managed,list) or any(not isinstance(v,str) for v in managed)
            or not isinstance(row.get("summary"),dict) or row["summary"].get("orders_sent")!=0):
        raise ValueError("invalid_observation_checkpoint_structure")
    if any(not isinstance(v,dict) or v.get("ticket")!=k for k,v in seen.items()):
        raise ValueError("invalid_checkpoint_fill_identity")
    return set(baseline) if baseline is not None else None,seen,set(managed),row["summary"]
