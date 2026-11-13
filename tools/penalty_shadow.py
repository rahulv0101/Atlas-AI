"""Frozen paired replay of future archived candidates; no broker calls or promotion."""
import argparse
import ast
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.learning.observation_checkpoint import account_scope, observation_lock
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.research_protocol import environment_versions
from atlas_ai.testing.decision_archive import encoded, index_rows, sha
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant, simulate
from atlas_ai.testing.penalty_shadow import paired_candidate, stage
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import read, digest, signed, save_signed, settings_for, deny

METHOD = {"comparison": "remove_aggregate_loss_count_multipliers_only_keep_fingerprint_lessons",
          "selection": "same_published_chosen_candidate_no_reranking",
          "daily_pair_limit": 6, "minimum_pairs_per_stage": 30, "minimum_changed_per_stage": 10,
          "minimum_admission_differences_per_stage": 5,
          "admission": "recomputed_final_conviction_vs_captured_effective_threshold_and_recorded_timing_only",
          "entry": "next_full_UTC_minute_after_archive_observation", "slippage_points_per_side": 3.,
          "sampling": "first_reproducible_candidate_per_4h_UTC_band_nonoverlapping_full_horizons",
          "maximum_per_4h_band": 1, "auto_promotion": False}


def analysis_environment():
    names = set()
    for name in ("decision_analysis", "chart_analysis", "setup_playbook", "market_regime"):
        tree = ast.parse((ROOT/"atlas_ai/analysis"/(name+".py")).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                literal = node.args[0].value
                if isinstance(literal, str) and (isinstance(node.func, ast.Attribute) and node.func.attr=="getenv"
                                               or isinstance(node.func, ast.Name) and node.func.id=="_env_threshold"):
                    names.add(literal)
    if any(any(part in key.upper() for part in ("API_KEY", "PASSWORD", "SECRET", "TOKEN", "LOGIN")) for key in names):
        raise ValueError("private_environment_must_not_be_frozen")
    return {key: os.environ.get(key) for key in sorted(names)}


def stamp(value):
    value = pd.Timestamp(value)
    if value.tzinfo is None: raise ValueError("verified_UTC_offset_required")
    return value.tz_convert("UTC")


def initialize(directory, storage, now):
    if directory.exists(): raise FileExistsError("new_penalty_experiment_directory_required")
    directory.resolve().relative_to(storage.resolve())
    settings = load_settings(); acceptance = read(storage/"acceptance_plan.json")
    if digest(storage/"acceptance_plan.json") != (storage/"acceptance_plan.sha256").read_text().strip():
        raise ValueError("acceptance_plan_changed")
    if acceptance["account_scope"] != account_scope(settings): raise ValueError("account_scope_changed")
    if stamp(acceptance["deadline"]) <= stamp(now): raise ValueError("observation_deadline_already_passed")
    Path(acceptance["paper_run"]).resolve().relative_to(storage.resolve())
    reference = Path(read(storage/"guarded_research_active.json")["run_dir"]).resolve()
    reference.relative_to(storage.resolve()); broker = signed(reference, "manifest")
    if broker["settings"]["symbol"] != settings.symbol or settings.timeframe != "M1":
        raise ValueError("matching_M1_market_required")
    directory.mkdir(parents=True)
    hashes = {}
    for name in ("atlas_ai", "tools"):
        for path in (ROOT/name).rglob("*.py"):
            relative = path.relative_to(ROOT); target = directory/"frozen_source"/relative
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
            hashes[relative.as_posix()] = digest(path)
    manifest = {"schema": "atlas_penalty_shadow_v1", "frozen_at": now.isoformat(),
        "deadline": acceptance["deadline"], "storage": str(storage.resolve()),
        "paper_source": str(Path(acceptance["paper_run"]).resolve()),
        "method": METHOD, "settings": safe_settings(settings), "source_hashes": hashes,
        "environment": environment_versions(), "account_scope": acceptance["account_scope"],
        "analysis_environment": analysis_environment(),
        "spec": broker["spec"], "broker_reference_manifest_sha256": digest(reference/"manifest.json"),
        "broker_reference_frozen_at": broker["frozen_at"],
        "variant": asdict(ExitVariant("current", settings.backtest_break_even_lock_r, 3.)),
        "broker_eligible": False, "orders_sent": 0, "auto_promotion": False,
        "limitations": ["Post-publication paired replay, not atomic pre-decision inputs or pre-entry prediction receipts.",
            "Chosen strategy held fixed; no alternate reranking or endogenous learning path.",
            "Only conviction and recorded timing admissions are compared; all other live execution gates remain unverified.",
            "Nominal minimum-volume labels, not live sizing, margin, risk-budget or portfolio simulation.",
            "Current-reference broker cash conversion and assumed slippage; natural fills remain uncalibrated.",
            "Fixed opportunity sampling may yield inadequate policy contrast. No statistical proof or promotion."]}
    save_signed(directory, "manifest", manifest)
    atomic_json(storage/"penalty_shadow_active.json", {"run_dir": str(directory.resolve())})
    return manifest


def validate(directory):
    manifest = signed(directory, "manifest")
    if (manifest["schema"] != "atlas_penalty_shadow_v1" or manifest["method"] != METHOD
            or manifest["environment"] != environment_versions() or manifest["broker_eligible"] is not False
            or manifest["auto_promotion"] is not False or manifest["orders_sent"] != 0):
        raise ValueError("penalty_experiment_boundary_changed")
    snapshot = directory/"frozen_source"
    for name, expected in manifest["source_hashes"].items():
        path = (snapshot/name).resolve(); path.relative_to(snapshot.resolve())
        if digest(path) != expected: raise ValueError("frozen_penalty_source_changed")
    return manifest


def stable_candles(source):
    before = (source/"artifacts.json").read_bytes(); expected = json.loads(before)
    data = (source/"observed_candles.csv").read_bytes()
    if sha(data) != expected.get("observed_candles.csv") or before != (source/"artifacts.json").read_bytes():
        return None
    return prepare_frame(pd.read_csv(StringIO(data.decode("utf-8"))))


def read_record(archive, row):
    raw = (archive/"records"/(row["record_id"]+".json.gz")).read_bytes()
    if sha(raw) != row["blob_sha256"]: raise ValueError("paired_archive_record_changed")
    record = json.loads(gzip.decompress(raw))
    if sha(encoded({k:v for k,v in record.items() if k != "observed_at"})) != row["record_id"]:
        raise ValueError("paired_record_identity_changed")
    return record


def load_saved(archive, record, name):
    ref = record["saved_state"][name]; key = ref["blob_id"]
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key): raise ValueError("invalid_learning_blob_id")
    data = (archive/"state_blobs"/(key+".json.gz")).read_bytes()
    raw = gzip.decompress(data)
    if sha(data) != ref["blob_sha256"] or sha(raw) != key: raise ValueError("paired_learning_blob_changed")
    return json.loads(raw)


class ArchiveBusy(RuntimeError):
    pass


@contextmanager
def archive_read_lock(path):
    lock = observation_lock(path)
    try:
        lock.__enter__()
    except RuntimeError as exc:
        raise ArchiveBusy("archive_writer_busy") from exc
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def once(directory, now):
    try:
        return _once(directory, now)
    except ArchiveBusy:
        report = read(directory/"status.json") if (directory/"status.json").exists() else {
            "state": "collecting_paired_shadow", "resolved_pairs": 0, "pending_pairs": 0,
            "broker_eligible": False, "orders_sent": 0}
        report = {**report, "checked_at": now.isoformat(), "waiting_for_archive_writer": True}
        atomic_json(directory/"status.json", report)
        return report


def _once(directory, now):
    manifest = validate(directory); storage = Path(manifest["storage"]); archive = storage/"replay_evidence"
    state_path = directory/"checkpoint.json"
    if state_path.exists():
        wrapper = read(state_path); state = wrapper["state"]
        if sha(encoded(state)) != wrapper["sha256"] or state["manifest_sha256"] != digest(directory/"manifest.json"):
            raise ValueError("paired_checkpoint_changed")
    else:
        state = {"manifest_sha256": digest(directory/"manifest.json"), "cursor": 0,
                 "prefix_sha256": sha(encoded([])), "pairs": [], "pending": [], "excluded": {}, "daily": {}, "bands": {}, "next_entry": None}
    def exclude(reason): state["excluded"][reason] = state["excluded"].get(reason, 0)+1
    cfg = settings_for(manifest, str(directory/"unused_storage_no_writes"))
    freeze = stamp(manifest["frozen_at"]); end = stamp(manifest["deadline"])
    with patch.dict(os.environ), patch.object(mt5, "initialize", deny), patch.object(mt5, "order_send", deny):
        for key,value in manifest["analysis_environment"].items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
        with archive_read_lock(archive/"archive.lock"):
            rows = index_rows(archive); cursor = state["cursor"]
            if cursor > len(rows) or sha(encoded(rows[:cursor])) != state["prefix_sha256"]:
                raise ValueError("paired_archive_prefix_changed")
            by_id={row["record_id"]:row for row in rows}
            for pair in state["pairs"]+state["pending"]:
                if pair["record_id"] not in by_id:raise ValueError("paired_source_record_missing")
                read_record(archive,by_id[pair["record_id"]])
            for row in rows[cursor:]:
                if len(state["pairs"])+len(state["pending"]) >= 60: break
                record = read_record(archive, row)
                try: observed = stamp(record["observed_at"]); published = stamp(record["publication"]["updated_at"])
                except (ValueError, KeyError): exclude("unverified_time"); continue
                if not freeze <= published <= observed < end: exclude("outside_frozen_window"); continue
                if observed > stamp(now) or (observed-published).total_seconds() > 180 or record.get("publication_fresh") is not True:
                    exclude("stale_or_future"); continue
                entry = observed.floor("min")+pd.Timedelta(minutes=1); horizon = entry+pd.Timedelta(minutes=cfg.backtest_max_hold_bars)
                if horizon > end: exclude("horizon_beyond_deadline"); continue
                if state["next_entry"] and entry < stamp(state["next_entry"]): exclude("overlapping_horizon"); continue
                day = entry.date().isoformat()
                if state["daily"].get(day,0) >= METHOD["daily_pair_limit"]: exclude("daily_pair_limit"); continue
                band=day+":"+str(entry.hour//4)
                if state["bands"].get(band,0)>=METHOD["maximum_per_4h_band"]:exclude("sampling_band_limit");continue
                try: payload = {"state":load_saved(archive, record,"learning_state.json")}
                except KeyError: exclude("learning_snapshot_missing"); continue
                runtime=load_saved(archive,record,"runtime_flags.json") if "runtime_flags.json" in record["saved_state"] else {}
                pair, reason = paired_candidate(cfg, payload, record["publication"],runtime)
                if pair is None: exclude(reason); continue
                state["pending"].append({**pair, "record_id": row["record_id"], "entry_at": entry.isoformat(), "horizon_end": horizon.isoformat()})
                state["next_entry"] = horizon.isoformat(); state["daily"][day] = state["daily"].get(day,0)+1
                state["bands"][band]=state["bands"].get(band,0)+1
            # A full cohort is fixed; unselected later observations cannot alter it.
            state["cursor"] = len(rows); state["prefix_sha256"] = sha(encoded(rows))
        frame = stable_candles(Path(manifest["paper_source"]))
        if frame is not None:
            times = pd.to_datetime(frame.time, utc=True); pending = []
            def horizon_rows(i,last):
                return json.loads(frame.iloc[i:last+1][["time","open","high","low","close","spread"]].to_json(
                    orient="records",date_format="iso",double_precision=12))
            for pair in state["pairs"]:
                i=int(times.searchsorted(stamp(pair["entry_at"])));last=i+cfg.backtest_max_hold_bars-1
                if last>=len(frame) or horizon_rows(i,last)!=pair["horizon_candles"]:
                    raise ValueError("paired_resolved_prices_revised")
            for pair in state["pending"]:
                at = stamp(pair["entry_at"]); horizon = stamp(pair["horizon_end"])
                if horizon > stamp(now) or frame.empty or times.iloc[-1]+pd.Timedelta(minutes=1) < horizon:
                    pending.append(pair); continue
                i = int(times.searchsorted(at)); last = i+cfg.backtest_max_hold_bars-1
                if i >= len(frame) or last >= len(frame) or times.iloc[i] != at or not times.iloc[i:last+1].diff().dropna().eq(pd.Timedelta(minutes=1)).all():
                    exclude("execution_horizon_gap"); continue
                outcome = simulate(frame, i, TradeSignal(pair["strategy"], pair["side"], pair["seed_baseline"],
                    pair["stop_loss_points"],pair["take_profit_points"]), manifest["spec"]["volume_min"],
                    BrokerSpec(**manifest["spec"]),cfg,ExitVariant(**manifest["variant"]))
                state["pairs"].append({**pair,"net_r":outcome["net_r"],"net_cash":outcome["net_cash"],"exit_reason":outcome["exit_reason"],
                                       "horizon_candles":horizon_rows(i,last)})
            state["pending"] = pending
    state["pairs"].sort(key=lambda pair:pair["entry_at"])
    first = stage(state["pairs"][:30]); second = stage(state["pairs"][30:60])
    report = {"state": "completed_requires_review" if len(state["pairs"])>=60 else "window_completed_requires_review" if stamp(now)>=end else "collecting_paired_shadow",
        "checked_at": now.isoformat(), "frozen_at": manifest["frozen_at"], "deadline": manifest["deadline"],
        "resolved_pairs": len(state["pairs"]), "pending_pairs": len(state["pending"]), "excluded": state["excluded"],
        "first_stage": first, "validation_stage": second,
        "contrast_sufficient_for_review": first["contrast_sufficient_for_review"] and second["contrast_sufficient_for_review"],
        "candle_snapshot_committed": frame is not None, "broker_eligible": False, "auto_promotion": False,
        "orders_sent": 0, "full_live_policy_parity": False}
    atomic_json(state_path,{"state":state,"sha256":sha(encoded(state))}); atomic_json(directory/"status.json",report)
    return report


def ensure(storage,state,*,can_start,now,start=subprocess.Popen):
    storage=Path(storage); pointer=storage/"penalty_shadow_active.json"
    if not pointer.exists(): return {"state":"not_configured"}
    directory=Path(read(pointer)["run_dir"]).resolve(); directory.relative_to(storage.resolve())
    manifest=signed(directory,"manifest"); report=read(directory/"status.json") if (directory/"status.json").exists() else {}
    if (manifest.get("schema")!="atlas_penalty_shadow_v1" or manifest.get("broker_eligible") is not False
            or manifest.get("auto_promotion") is not False or manifest.get("orders_sent")!=0):
        raise ValueError("penalty_experiment_boundary_changed")
    if report.get("state") in {"completed_requires_review","window_completed_requires_review","blocked_evidence_review_required"}:
        return {key:report.get(key) for key in ("state","resolved_pairs","pending_pairs")}
    if now>=stamp(manifest["deadline"]).to_pydatetime(): return {"state":"deadline_reached"}
    try:
        with observation_lock(directory/"watch.lock"): pass
    except RuntimeError:
        return {"state":"existing_paired_observer_running","resolved_pairs":report.get("resolved_pairs",0),"pending_pairs":report.get("pending_pairs",0),"broker_eligible":False}
    if not can_start: return {"state":"waiting_for_backend_and_operator_awake"}
    attempts=state.setdefault("penalty_shadow_starts",[]); attempts[:]=[t for t in attempts if now.timestamp()-t<3600]
    if len(attempts)>=3:return {"state":"restart_budget_exhausted_review_required"}
    validate(directory)
    with (directory/"stdout.log").open("a") as out,(directory/"stderr.log").open("a") as err:
        child=start([sys.executable,str(directory/"frozen_source/tools/penalty_shadow.py"),"watch","--run-dir",str(directory)],
            cwd=directory/"frozen_source",stdout=out,stderr=err,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    attempts.append(now.timestamp()); return {"state":"paired_observer_launched","pid":child.pid,"broker_eligible":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("mode",choices=("init","once","watch"))
    parser.add_argument("--run-dir",type=Path,required=True); parser.add_argument("--storage",type=Path,default=ROOT/"storage")
    args=parser.parse_args()
    if args.mode=="init":
        result=initialize(args.run_dir,args.storage,datetime.now(timezone.utc));print(json.dumps({"state":"frozen","frozen_at":result["frozen_at"],"deadline":result["deadline"]}));return
    with observation_lock(args.run_dir/"watch.lock"):
        while True:
            try: result=once(args.run_dir,datetime.now(timezone.utc))
            except Exception as exc:
                result={"state":"blocked_evidence_review_required","checked_at":datetime.now(timezone.utc).isoformat(),"error":type(exc).__name__,"reason":str(exc),"broker_eligible":False,"orders_sent":0}
                atomic_json(args.run_dir/"status.json",result)
            if args.mode=="once" or result["state"]!="collecting_paired_shadow":return
            time.sleep(60)


if __name__=="__main__":main()
