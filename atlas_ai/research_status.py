"""Shared, read-only operator view of independent Atlas evidence streams."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from atlas_ai.startup_verification import verify as verify_startup


def _read(path, *, signed=False):
    before = path.stat()
    if before.st_size > 2 * 1024 * 1024: raise ValueError("report_too_large")
    raw = path.read_bytes(); after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("report_changed_during_read")
    if signed and hashlib.sha256(raw).hexdigest() != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("report_checksum_failed")
    value = json.loads(raw)
    if not isinstance(value, dict): raise ValueError("report_not_object")
    return value


def _age(value, now):
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if at.tzinfo is None: return None
        age = (now - at).total_seconds()
        return round(age, 1) if age >= 0 else None
    except (ValueError, TypeError): return None


def _metrics(value):
    return {key: value.get(key) for key in ("trades", "net_r", "mean_net_r", "profit_factor", "max_drawdown_r")}


def load_research_progress(storage, *, now=None):
    """No model activation, broker access, or writes; never conveys trade authority."""
    now = now or datetime.now(timezone.utc); storage = Path(storage)
    result = {"schema": "atlas_research_progress_v1", "checked_at": now.isoformat(),
              "broker_eligible": False, "auto_promotion": False, "orders_sent": 0,
              "profitability_proven": False, "errors": [],
              "boundary": "Research informs review; the trader retains its strategy, risk and execution gates."}
    try:
        startup = verify_startup(storage)
    except Exception:
        startup = {"state": "startup_receipt_unavailable", "verified": False}
    result["startup"] = {key: startup.get(key) for key in ("state", "verified")}
    try:
        acceptance = _read(storage / "acceptance_plan.status.json")
        age = _age(acceptance.get("checked_at"), now)
        result["acceptance"] = {key: acceptance.get(key) for key in
            ("state", "deadline", "first_stage_cases", "validation_stage_cases", "required_per_stage", "natural_cycle_verified", "paper_evidence_error")}
        result["acceptance"].update(age_seconds=age, stale=age is None or age > 180)
        result["costs"] = {key: (acceptance.get("execution_costs") or {}).get(key) for key in
                           ("state", "measured_fill_observations", "cost_calibration_ready")}
        result["archive"] = {key: (acceptance.get("publication_evidence") or {}).get(key) for key in ("state", "records", "replay_ready")}
    except (OSError, ValueError, TypeError, AttributeError):
        result["acceptance"] = {"state": "unavailable", "stale": True}
        result["errors"].append("acceptance_report_unavailable")
    try:
        activity = _read(storage / "activity_review/status.json")
        age = _age(activity.get("checked_at"), now)
        result["activity"] = {key: activity.get(key) for key in
            ("state", "deadline", "sampled_publications", "directional_publications", "analysis_eligible_publications",
             "coverage_gap_publications", "categories", "verified_natural_cycles_in_window")}
        result["activity"].update(age_seconds=age, stale=age is None or age > 180)
    except (OSError, ValueError, TypeError):
        result["activity"] = {"state": "unavailable", "stale": True}
        result["errors"].append("activity_report_unavailable")
    try:
        pointer = _read(storage / "learned_ranker_active.json")
        directory = Path(pointer["run_dir"]).resolve(); directory.relative_to(storage.resolve())
        manifest = _read(directory / "manifest.json", signed=True)
        model = _read(directory / "model.json", signed=True)
        history = _read(directory / "historical_report.json", signed=True)
        if (manifest.get("broker_eligible") is not False or manifest.get("auto_promotion") is not False
                or model.get("broker_eligible") is not False):
            raise ValueError("unexpected_research_authority")
        learner = {"state": "awaiting_observer", "model_state": model.get("state"),
                   "training_rows": model.get("rows"), "training_dates": model.get("dates"),
                   "frozen_at": manifest.get("frozen_at"), "deadline": manifest.get("deadline"),
                   "historical_review_passed": history.get("historical_review_passed") is True,
                   "validation_learner": _metrics((history.get("validation_previously_inspected") or {}).get("learner") or {}),
                   "validation_baseline": _metrics((history.get("validation_previously_inspected") or {}).get("baseline") or {}),
                   "metadata_checksums_verified": True, "broker_eligible": False, "stale": True}
        try:
            forward = _read(directory / "forward_status.json")
            age = _age(forward.get("checked_at"), now)
            learner.update({key: forward.get(key) for key in
                           ("state", "learner_paper_trades", "baseline_paper_trades", "first_stage_passed", "validation_stage_passed")})
            learner.update(age_seconds=age, stale=age is None or age > 900,
                           first_stage_cases=((forward.get("first_stage") or {}).get("learner") or {}).get("trades", 0),
                           validation_stage_cases=((forward.get("validation_stage") or {}).get("learner") or {}).get("trades", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            result["errors"].append("learning_observer_report_unavailable")
        result["learning"] = learner
    except FileNotFoundError:
        result["learning"] = {"state": "unavailable", "stale": True, "broker_eligible": False}
        result["errors"].append("learning_metadata_unavailable")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result["learning"] = {"state": "integrity_review_required", "stale": True, "broker_eligible": False}
        result["errors"].append("learning_metadata_invalid")
    try:
        pointer=_read(storage/"penalty_shadow_active.json")
        directory=Path(pointer["run_dir"]).resolve();directory.relative_to(storage.resolve())
        manifest=_read(directory/"manifest.json",signed=True)
        if manifest.get("broker_eligible") is not False or manifest.get("auto_promotion") is not False:
            raise ValueError("unexpected_penalty_authority")
        shadow=_read(directory/"status.json");age=_age(shadow.get("checked_at"),now)
        result["penalty_shadow"]={key:shadow.get(key) for key in
            ("state","frozen_at","deadline","resolved_pairs","pending_pairs","first_stage","validation_stage","contrast_sufficient_for_review")}
        result["penalty_shadow"].update(stale=age is None or age>180,age_seconds=age,broker_eligible=False)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        result["penalty_shadow"]={"state":"unavailable","stale":True,"broker_eligible":False}
    return result


def research_answer(progress, query, *, voice=False):
    q = query.lower(); learning = progress.get("learning") or {}; activity = progress.get("activity") or {}
    if "penalty" in q or "haircut" in q:
        shadow=progress.get("penalty_shadow") or {}
        if shadow.get("stale",True):
            return "The penalty comparison report is unavailable or stale; I cannot confirm its current progress. It has no trading authority."
        first=(shadow.get("first_stage") or {}).get("resolved_pairs",0)
        second=(shadow.get("validation_stage") or {}).get("resolved_pairs",0)
        return (f"The penalty comparison has {first}/30 first-stage pairs and {second}/30 validation pairs, with {shadow.get('pending_pairs',0)} pending. "
                "It has no trading authority." + ("" if voice else
                " It compares current behavior with aggregate-count penalties removed, while retaining fingerprint lessons. "
                "These are matched paper observations; remaining live execution gates are not verified by this test."))
    if "startup" in q or "reboot" in q:
        startup = progress.get("startup") or {}
        if startup.get("verified") is True:
            return "A successful Windows sign-in startup was recorded on the current boot after the verification baseline."
        if startup.get("state") == "pending_reboot":
            return "Startup shortcuts are installed, but the real reboot and Windows sign-in test is still pending. Manual startup does not count as that proof."
        return "Post-reboot startup evidence is unavailable or needs review; I cannot confirm that test passed."
    if any(term in q for term in ("activity", "inactivity", "seven-day", "seven day")):
        if activity.get("stale", True): return "The activity review report is unavailable or stale; I cannot confirm current progress."
        return (f"Activity review: {str(activity.get('state', 'unknown')).replace('_', ' ')}. "
                f"Verified natural cycles: {activity.get('verified_natural_cycles_in_window', 0)}. "
                f"Deadline: {activity.get('deadline', 'unavailable')}. "
                + ("" if voice else f"Sampled directional publications: {activity.get('directional_publications', 0)}; "
                   f"analysis-eligible publications: {activity.get('analysis_eligible_publications', 0)}. Counts are observations, not unique opportunities."))
    if learning.get("model_state") is None:
        return "The learning experiment's verified metadata is unavailable. I cannot confirm its model or results; it has no trading authority."
    if learning.get("model_state") != "fitted_research_only":
        return "The learning experiment has insufficient training evidence for a fitted model. It has no trading authority."
    if any(term in q for term in ("how does", "how do", "what does", "how it works")):
        return ("The learning model estimates cost-adjusted simulated returns from closed-candle context, ranks existing strategy signals, "
                "and can reject every candidate. It is frozen for a separate paper test; it cannot rewrite strategies or change risk and execution gates.")
    state = "The learning observer report is stale or unavailable." if learning.get("stale") else "The frozen learning model is being tested on new paper outcomes."
    if not learning.get("stale") and learning.get("state") in {"completed_paper_requires_review", "window_completed_requires_review"}:
        state = "The frozen learning paper test has ended and needs review."
    elif not learning.get("stale") and learning.get("state") == "blocked_evidence_review_required":
        state = "The frozen learning paper test is blocked and needs evidence review."
    historical = "passed its historical screening" if learning.get("historical_review_passed") else "did not pass historical screening"
    text = f"{state} It {historical} and has no trading authority."
    if "why" in q and not learning.get("historical_review_passed") and learning.get("validation_learner", {}).get("trades") == 0:
        text += " In the inspected diagnostic period it selected no candidate above its expected-return threshold; zero trades cannot qualify a trading strategy."
    if not voice:
        text += (f" It trained on {learning.get('training_rows', 'unknown')} examples across {learning.get('training_dates', 'unknown')} dates. "
                 f"Recorded paper stages: {learning.get('first_stage_cases', 0)}/30 and {learning.get('validation_stage_cases', 0)}/30. "
                 "The current trader keeps its existing strategies, risk limits and execution gates. Profitability remains unproven.")
    return text
