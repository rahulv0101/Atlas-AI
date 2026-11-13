"""Bounded continuation of read-only acceptance collectors; no trade authority.

The frozen paper rule, criteria and original observation journal are retained.
Existing collectors are reused. This supervisor never launches the backend,
changes trading settings, approves a strategy or dispatches a broker order.
"""
from datetime import datetime,timedelta,timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.learning.observation_checkpoint import account_scope,load_checkpoint,observation_lock
from atlas_ai.runtime_processes import atlas_mode_processes
from atlas_ai.strategies.research_protocol import environment_versions
from tools.observe_cost_research import observer_lock
from tools.execution_quality_report import build_report
from tools.guarded_research_supervision import ensure_research
from atlas_ai.testing.decision_archive import capture as capture_publication
from atlas_ai.testing.activity_review import review as review_activity
from tools.learned_ranker_supervision import ensure_learning
from tools.recover_paper_prefix import recover as recover_paper_prefix
from tools.penalty_shadow import ensure as ensure_penalty_shadow


def read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:return default


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def minimum_trading_days(manifest):
    return math.ceil(2*int(manifest["minimum_cases_per_stage"])/int(manifest["rules"]["max_trades_day"]))


def create_plan(path,paper,journal,days=30):
    if path.exists():raise FileExistsError("existing_acceptance_plan_must_be_resumed")
    if not 14<=days<=45:raise ValueError("bounded_plan_requires_14_to_45_calendar_days")
    s=load_settings();m=read(paper/"manifest.json");snapshot=paper/"frozen_source"
    if not snapshot.is_dir():raise ValueError("frozen_source_snapshot_required")
    load_checkpoint(journal.with_suffix(".checkpoint.json"),s,journal=journal)
    plan={"schema":"atlas_acceptance_supervision_v1","created_at":datetime.now(timezone.utc).isoformat(),
        "frozen_at":m["frozen_at"],"deadline":(datetime.fromisoformat(m["frozen_at"])+timedelta(days=days)).isoformat(),
        "calendar_days":days,"minimum_possible_trading_days":minimum_trading_days(m),
        "account_scope":account_scope(s),"project_root":str(ROOT),"storage_dir":str(Path(s.storage_dir).resolve()),
        "paper_run":str(paper.resolve()),"journal":str(journal.resolve()),"source_root":str(snapshot.resolve()),
        "source_hashes":{str(p.relative_to(snapshot)).replace('\\','/'):digest(p) for p in snapshot.rglob('*.py')},
        "python":str(Path(sys.executable).resolve()),"paper_manifest_sha256":digest(paper/"manifest.json"),
        "broker_eligible":False,"auto_promotion":False,"orders_sent":0}
    validate(plan,s)
    atomic_json(path,plan);path.with_suffix(".sha256").write_text(digest(path),encoding="ascii")
    return plan


def validate(plan,settings):
    if (plan.get("schema")!="atlas_acceptance_supervision_v1" or plan.get("account_scope")!=account_scope(settings)
            or plan.get("orders_sent")!=0 or plan.get("broker_eligible") is not False or plan.get("auto_promotion") is not False):
        raise ValueError("invalid_acceptance_plan_boundary_or_account")
    frozen=datetime.fromisoformat(plan["frozen_at"]);deadline=datetime.fromisoformat(plan["deadline"])
    if frozen.tzinfo is None or deadline.tzinfo is None or not timedelta(days=14)<=deadline-frozen<=timedelta(days=45):
        raise ValueError("invalid_acceptance_deadline")
    paper=Path(plan["paper_run"]);snapshot=Path(plan["source_root"])
    if digest(paper/"manifest.json")!=plan["paper_manifest_sha256"]:
        raise ValueError("paper_manifest_changed")
    if (paper/"manifest.sha256").read_text().strip()!=plan["paper_manifest_sha256"]:
        raise ValueError("paper_manifest_integrity_changed")
    m=read(paper/"manifest.json")
    if (m.get("schema")!="atlas_prospective_pullback_v1" or m.get("broker_eligible") is not False
            or m.get("auto_promotion") is not False or m.get("orders_sent")!=0
            or m.get("minimum_cases_per_stage")!=30):
        raise ValueError("unsupported_or_changed_paper_acceptance_boundary")
    if m["account_scope"]!=plan["account_scope"] or m["frozen_at"]!=plan["frozen_at"]:
        raise ValueError("paper_scope_or_freeze_changed")
    if settings.mt5_server_timezone!=m["broker_clock_timezone"]:
        raise ValueError("natural_observer_broker_clock_changed_review_required")
    if m["environment"]!=environment_versions():raise ValueError("frozen_paper_environment_changed")
    for name,expected in plan["source_hashes"].items():
        source=(snapshot/name).resolve();source.relative_to(snapshot.resolve())
        if digest(source)!=expected:raise ValueError("frozen_collector_source_changed")
    if any(plan["source_hashes"].get(k)!=v for k,v in m["source_hashes"].items()):
        raise ValueError("snapshot_does_not_match_paper_protocol")
    load_checkpoint(Path(plan["journal"]).with_suffix(".checkpoint.json"),settings,journal=plan["journal"])
    return m


def busy(role,path):
    lock=observer_lock if role=="paper" else observation_lock
    try:
        with lock(path):return False
    except RuntimeError as exc:
        if "already_running" in str(exc):return True
        raise


def worker_command(plan,role,remaining_hours):
    if not 0<remaining_hours<=24*45:raise ValueError("remaining_duration_outside_plan")
    snapshot=Path(plan["source_root"])
    if role=="paper":return [plan["python"],str(snapshot/"tools/prospective_pullback.py"),"watch","--run-dir",plan["paper_run"],"--hours",str(min(168,remaining_hours))]
    if role=="natural":return [plan["python"],str(snapshot/"tools/observe_day_trading.py"),"--resume","--minutes",str(min(10080,remaining_hours*60)),"--interval-seconds","10","--output",plan["journal"]]
    raise ValueError("unknown_collector_role")


def spawn(plan,role,hours):
    folder=Path(plan["storage_dir"])/"acceptance_supervision";folder.mkdir(parents=True,exist_ok=True)
    with (folder/f"{role}.stdout.log").open("a") as out,(folder/f"{role}.stderr.log").open("a") as err:
        child=subprocess.Popen(worker_command(plan,role,hours),cwd=plan["project_root"],stdout=out,stderr=err,
            env={**os.environ,"STORAGE_DIR":str(Path(plan["storage_dir"]).resolve())},
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return child.pid


def tick(plan,state,now,*,is_busy=busy,start_worker=spawn,backend_ready=None):
    s=load_settings();m=validate(plan,s)
    # Report failures must be visible without stopping the independent collectors.
    try:
        costs=build_report(plan["storage_dir"])
        atomic_json(Path(plan["storage_dir"])/"acceptance_execution_costs.json",costs)
        cost_status={k:costs[k] for k in ("checked_at","state","measured_fill_observations",
            "diagnostic_measured_fill_observations","invalid_journal_rows","cost_calibration_ready")}
    except Exception as exc:
        cost_status={"state":"report_failed","error":type(exc).__name__,"cost_calibration_ready":False}
    remaining=(datetime.fromisoformat(plan["deadline"])-now).total_seconds()/3600
    paper=read(Path(plan["paper_run"])/"status.json",{})
    outcomes=read(Path(plan["paper_run"])/"outcomes.json",[])
    _,_,_,summary=load_checkpoint(Path(plan["journal"]).with_suffix(".checkpoint.json"),s,journal=plan["journal"])
    natural=summary.get("lifecycle_acceptance",{})
    natural_ready=(natural.get("state")=="verified" and bool(natural.get("verified_end_to_end_cycles"))
        and natural.get("manual_and_forced_tests_count_as_acceptance") is False)
    needed=int(m["minimum_cases_per_stage"])
    completed=len(outcomes);paper_done=completed>=2*needed
    if backend_ready is None:
        rows=atlas_mode_processes("live",project_root=plan["project_root"])
        backend_ready=bool(rows)
    controls=read(Path(plan["storage_dir"])/"automation_state.json",{})
    controls=controls.get("payload",controls)
    if not isinstance(controls,dict):raise ValueError("invalid_operator_controls")
    can_start=bool(backend_ready and not controls.get("sleep_mode_active",False))
    publication={"state":"paused_backend_or_operator_sleep","replay_ready":False}
    if can_start and remaining>0:
        try:publication=capture_publication(plan["storage_dir"],now,
            secrets=(s.hfm_password,s.gemini_api_key,s.openai_api_key))
        except Exception as exc:publication={"state":"blocked_archive_review_required","error":type(exc).__name__,"replay_ready":False}
    result={"checked_at":now.isoformat(),"deadline":plan["deadline"],"minimum_possible_trading_days":minimum_trading_days(m),
        "first_stage_cases":min(needed,completed),"validation_stage_cases":min(needed,max(0,completed-needed)),
        "required_per_stage":needed,"paper_review_ready":paper.get("research_review_ready") is True,
        "natural_cycle_verified":natural_ready,"natural_cycles":natural.get("verified_end_to_end_cycles",[]),
        "state":"window_completed" if remaining<=0 else "evidence_available_for_operator_review" if paper_done and natural_ready else "collecting",
        "backend_available":bool(backend_ready),"collector_actions":{},"publication_evidence":publication,"execution_costs":cost_status,"broker_eligible":False,"orders_sent":0,
        "note":"Paper qualification and broker cycles are separate evidence streams; same-version strategy linkage requires operator review. No activation is performed."}
    for role,done,lockfile in (("paper",paper_done,Path(plan["paper_run"])/"observer.lock"),
                               ("natural",natural_ready,Path(plan["storage_dir"])/"lifecycle_observer.lock")):
        action="no_renewal_required" if done else "deadline_reached" if remaining<=0 else None
        if action is None and is_busy(role,lockfile):action="existing_collector_running"
        if action is None and not can_start:
            action="operator_sleep_mode_no_restart" if controls.get("sleep_mode_active") else "waiting_for_explicit_backend_start"
        attempts=state.setdefault("starts",{}).setdefault(role,[])
        attempts[:]=[at for at in attempts if now.timestamp()-at<3600]
        if action is None and len(attempts)>=3:action="restart_budget_exhausted_review_required"
        if action is None:
            if role=="paper":
                if paper.get("error")=="ValueError" and paper.get("reason") not in {"frozen_paper_protocol_changed","paper_source_changed_during_evaluation"}:
                    raise ValueError("paper_worker_requires_evidence_review:"+str(paper.get("reason")))
                # A byte-exact signed prefix may recover an interrupted append.
                # Other corruption remains blocked without starving independent observers.
                digests=read(Path(plan["paper_run"])/"artifacts.json",{})
                try:
                    if set(digests)!={"observed_candles.csv","signals.json"}:raise ValueError("unverified_paper_artifacts")
                    if any(digest(Path(plan["paper_run"])/name)!=expected for name,expected in digests.items()):
                        repair=recover_paper_prefix(Path(plan["paper_run"]),apply=True)
                        result["paper_recovery"]={key:repair.get(key) for key in ("state","uncommitted_suffix_bytes","restored_sha256")}
                        if any(digest(Path(plan["paper_run"])/name)!=expected for name,expected in digests.items()):
                            raise ValueError("paper_artifact_changed")
                except (OSError,ValueError,RuntimeError):
                    result["paper_evidence_error"]="paper_artifact_changed"
                    result["collector_actions"][role]="blocked_artifact_review_required"
                    continue
            pid=start_worker(plan,role,remaining);attempts.append(now.timestamp())
            action=f"resumed_saved_evidence_pid_{pid}"
        result["collector_actions"][role]=action
    try:result["additional_research"]=ensure_research(plan["storage_dir"],state,can_start=can_start and remaining>0,now=now)
    except Exception as exc:
        result["additional_research"]={"state":"blocked_evidence_review_required","error":type(exc).__name__}
    try:result["activity_review"]=review_activity(plan["storage_dir"],s,now)
    except Exception as exc:
        result["activity_review"]={"state":"blocked_review_required","error":type(exc).__name__,"broker_eligible":False,"orders_sent":0}
    try:result["learning_experiment"]=ensure_learning(plan["storage_dir"],state,can_start=can_start and remaining>0,now=now)
    except Exception as exc:
        result["learning_experiment"]={"state":"blocked_evidence_review_required","error":type(exc).__name__,"broker_eligible":False,"orders_sent":0}
    try:result["penalty_shadow"]=ensure_penalty_shadow(plan["storage_dir"],state,can_start=can_start and remaining>0,now=now)
    except Exception as exc:
        result["penalty_shadow"]={"state":"blocked_evidence_review_required","error":type(exc).__name__,"broker_eligible":False,"orders_sent":0}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("mode",choices=("init","once","watch"))
    p.add_argument("--plan",type=Path,required=True);p.add_argument("--paper-run",type=Path);p.add_argument("--journal",type=Path)
    p.add_argument("--days",type=int,default=30);a=p.parse_args()
    if a.mode=="init":
        if a.paper_run is None or a.journal is None:p.error("--paper-run and --journal required")
        plan=create_plan(a.plan,a.paper_run,a.journal,a.days)
        print(json.dumps({"deadline":plan["deadline"],"minimum_trading_days":plan["minimum_possible_trading_days"],"orders_sent":0}));return
    state_path=a.plan.with_suffix(".state.json");report=a.plan.with_suffix(".status.json")
    with observation_lock(a.plan.with_suffix(".lock")):
        while True:
            if digest(a.plan)!=a.plan.with_suffix(".sha256").read_text().strip():raise ValueError("acceptance_plan_changed")
            plan=read(a.plan);state=read(state_path,{})
            try:result=tick(plan,state,datetime.now(timezone.utc))
            except Exception as exc:
                result={"state":"blocked_evidence_review_required","checked_at":datetime.now(timezone.utc).isoformat(),
                    "error":type(exc).__name__,"reason":str(exc),"broker_eligible":False,"orders_sent":0}
            atomic_json(state_path,state);atomic_json(report,result)
            if a.mode=="once" or result["state"] in {"window_completed","evidence_available_for_operator_review","blocked_evidence_review_required"}:return
            time.sleep(60)


if __name__=="__main__":main()
