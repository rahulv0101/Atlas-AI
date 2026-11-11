"""Read-only research continuation, called by the existing acceptance supervisor."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from atlas_ai.learning.observation_checkpoint import observation_lock


def ensure_research(storage,state,*,can_start,now,start=subprocess.Popen):
    pointer=Path(storage)/"guarded_research_active.json"
    if not pointer.exists():return {"state":"not_configured"}
    directory=Path(json.loads(pointer.read_text())["run_dir"]).resolve()
    directory.relative_to(Path(storage).resolve())
    manifest=json.loads((directory/"manifest.json").read_text())
    selection=json.loads((directory/"selection.json").read_text())
    for name in ("manifest","selection"):
        if hashlib.sha256((directory/f"{name}.json").read_bytes()).hexdigest()!=(directory/f"{name}.sha256").read_text().strip():
            raise ValueError("research_protocol_changed")
    if not selection["selected_for_forward"]:return {"state":"no_training_candidate"}
    if now>=datetime.fromisoformat(manifest["deadline"]):return {"state":"deadline_reached"}
    report=directory/"forward_status.json"
    if report.exists():
        saved=json.loads(report.read_text())
        if saved.get("state") in {"completed_evidence_requires_review","blocked_evidence_review_required"}:return saved
    try:
        with observation_lock(directory/"forward.lock"):pass
    except RuntimeError:return {"state":"existing_collector_running"}
    if not can_start:return {"state":"waiting_for_backend_and_operator_awake"}
    attempts=state.setdefault("research_starts",[])
    attempts[:]=[at for at in attempts if now.timestamp()-at<3600]
    if len(attempts)>=3:return {"state":"restart_budget_exhausted_review_required"}
    snapshot=directory/"frozen_source"
    for name,expected in manifest["source_hashes"].items():
        source=(snapshot/name).resolve();source.relative_to(snapshot.resolve())
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError("frozen_research_source_changed")
    with (directory/"forward.stdout.log").open("a") as out,(directory/"forward.stderr.log").open("a") as err:
        child=start([sys.executable,str(snapshot/"tools/observe_guarded_research.py"),"--run-dir",str(directory),"--watch"],
            cwd=snapshot,stdout=out,stderr=err,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    attempts.append(now.timestamp())
    return {"state":"paper_observer_launched","pid":child.pid,"orders_sent":0,"broker_eligible":False}
