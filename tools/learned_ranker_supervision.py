"""Resume one frozen learning observer; never activate its model for trading."""
from datetime import datetime
from pathlib import Path
import subprocess
import sys

from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.learn_candidate_ranker import read, signed, validate


def ensure_learning(storage, state, *, can_start, now, start=subprocess.Popen):
    storage = Path(storage); pointer = storage / "learned_ranker_active.json"
    if not pointer.exists(): return {"state": "not_configured"}
    directory = Path(read(pointer)["run_dir"]).resolve(); directory.relative_to(storage.resolve())
    manifest = signed(directory, "manifest"); model = signed(directory, "model")
    if manifest["broker_eligible"] is not False or manifest["orders_sent"] != 0 or manifest["auto_promotion"] is not False:
        raise ValueError("invalid_learning_authority")
    if model["state"] != "fitted_research_only": return {"state": "insufficient_training_evidence"}
    status = directory / "forward_status.json"
    if status.exists():
        report = read(status)
        if report["state"] in {"completed_paper_requires_review", "window_completed_requires_review", "blocked_evidence_review_required"}:
            return {k: report[k] for k in ("state", "broker_eligible", "orders_sent")}
    if now >= datetime.fromisoformat(manifest["deadline"]): return {"state": "deadline_reached"}
    try:
        with observation_lock(directory / "forward.lock"): pass
    except RuntimeError:
        report = read(status) if status.exists() else {}
        return {"state": "existing_learning_observer_running", "learner_paper_trades": report.get("learner_paper_trades", 0),
                "baseline_paper_trades": report.get("baseline_paper_trades", 0), "broker_eligible": False, "orders_sent": 0}
    if not can_start: return {"state": "waiting_for_backend_and_operator_awake"}
    attempts = state.setdefault("learning_starts", [])
    attempts[:] = [at for at in attempts if now.timestamp() - at < 3600]
    if len(attempts) >= 3: return {"state": "restart_budget_exhausted_review_required"}
    validate(directory)
    with (directory / "forward.stdout.log").open("a") as out, (directory / "forward.stderr.log").open("a") as err:
        child = start([sys.executable, str(directory / "frozen_source/tools/learn_candidate_ranker.py"), "watch", "--run-dir", str(directory)],
                      cwd=directory / "frozen_source", stdout=out, stderr=err,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    attempts.append(now.timestamp())
    return {"state": "learning_observer_launched", "pid": child.pid, "broker_eligible": False, "orders_sent": 0}
