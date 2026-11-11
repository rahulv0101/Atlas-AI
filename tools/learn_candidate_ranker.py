"""Freeze, train and observe a separate candidate-ranking paper experiment."""
import argparse
import ast
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import Settings
from atlas_ai.learning.observation_checkpoint import observation_lock
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.strategies.research_protocol import environment_versions
from atlas_ai.testing.decision_archive import sha
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.learned_ranker import METHOD, compare, examples, feature_names, fit, metrics, review_passed, stamp
from atlas_ai.testing.policy_replay import cache_candidates
from tools.cost_aware_strategy_audit import prepare_frame


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def digest(path): return sha(Path(path).read_bytes())


def deny(*args, **kwargs): raise AssertionError("learning_experiment_broker_access_forbidden")


def save_signed(directory, name, value):
    path = directory / (name + ".json")
    atomic_json(path, value); path.with_suffix(".sha256").write_text(digest(path), encoding="ascii")


def signed(directory, name):
    path = directory / (name + ".json")
    if digest(path) != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("learning_artifact_changed:" + name)
    return read(path)


def settings_for(manifest, temporary):
    return Settings(0, "", "", **{**manifest["settings"], "execute_trades": False,
                                    "storage_dir": temporary, "gemini_api_key": "", "openai_api_key": ""})


def signal_cache_ast(path):
    names = {"higher_timeframe_bias", "policy_trader", "cache_candidates"}
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(Path(path).read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name in names}


def initialize(source, output, storage, now):
    if output.exists(): raise FileExistsError("new_learning_directory_required_no_reset")
    old = signed(source, "manifest")
    if old["schema"] != "atlas_guarded_research_v2" or old["broker_eligible"] is not False:
        raise ValueError("verified_guarded_input_required")
    if digest(source / "candles.csv") != old["input_sha256"]:
        raise ValueError("historical_input_changed")
    # The publication archive is an unrelated observer, changed after this cache.
    # Signal-producing Atlas dependencies must still match the old frozen run.
    for name, expected in old["source_hashes"].items():
        if name.startswith("atlas_ai/") and name != "atlas_ai/testing/decision_archive.py":
            if digest(ROOT / name) != expected:
                frozen = source / "frozen_source" / name
                if (name != "atlas_ai/testing/policy_replay.py" or digest(frozen) != expected
                        or signal_cache_ast(ROOT / name) != signal_cache_ast(frozen)):
                    raise ValueError("signal_dependency_changed:" + name)
    acceptance = read(storage / "acceptance_plan.json")
    output.mkdir(parents=True)
    source_hashes = {}
    for name in ("atlas_ai", "tools"):
        for path in (ROOT / name).rglob("*.py"):
            relative = path.relative_to(ROOT); target = output / "frozen_source" / relative
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
            source_hashes[relative.as_posix()] = digest(path)
    frame = prepare_frame(pd.read_csv(source / "candles.csv"))
    times = pd.to_datetime(frame.time, utc=True)
    split = times.iloc[int(len(frame) * METHOD["training_fraction"])].isoformat()
    candidates = read(source / "candidates.json")
    strategies = sorted({s["strategy"] for row in candidates for s in row["signals"]})
    manifest = {
        "schema": "atlas_learned_candidate_ranker_v1", "frozen_at": now.isoformat(),
        "future_holdout_start": now.isoformat(), "deadline": acceptance["deadline"],
        "warmup_start": (now.replace(second=0, microsecond=0) - timedelta(minutes=1200)).isoformat(),
        "method": METHOD, "strategies": strategies, "settings": old["settings"], "spec": old["spec"],
        "variant": asdict(ExitVariant("current", old["settings"]["backtest_break_even_lock_r"], METHOD["slippage_points_per_side"])),
        "daily_paper_limit": 6, "historical_split": split,
        "historical_status": "Previously inspected data; chronological diagnostic only, not blind evidence.",
        "input_sha256": digest(source / "candles.csv"), "cached_signals_sha256": digest(source / "candidates.json"),
        "cached_signals_provenance": "Snapshot of previously generated signals; hash frozen here, not an original cache signature.",
        "cache_compatibility": "Signal-generation dependencies match source run; cache AST verified separately from UTC exit-report serialization.",
        "source_manifest_sha256": digest(source / "manifest.json"), "source_hashes": source_hashes,
        "environment": environment_versions(), "forward_source_run": acceptance["paper_run"],
        "broker_eligible": False, "auto_promotion": False, "orders_sent": 0,
        "missing_parity": ["Raw candidate ranking study; live conviction, timing, visual, macro and execution gates are not replayed.",
                           "Nominal minimum-lot paper outcomes; no live sizing, portfolio risk or margin policy simulation.",
                           "Frozen current currency conversion, recorded spread and assumed 3-point adverse slippage per leg.",
                           "Fixed model replay of post-freeze closed candles; not broker fills or pre-entry prediction receipts.",
                           "No independent statistical significance claim; historical data and labels can be correlated."],
    }
    save_signed(output, "manifest", manifest)
    shutil.copyfile(source / "candles.csv", output / "candles.csv")
    shutil.copyfile(source / "candidates.json", output / "candidates.json")
    with tempfile.TemporaryDirectory(prefix="atlas_ranker_") as temporary, patch.object(mt5, "initialize", deny), patch.object(mt5, "order_send", deny):
        settings = settings_for(manifest, temporary); spec = BrokerSpec(**manifest["spec"])
        variant = ExitVariant(**manifest["variant"])
        training, excluded = examples(frame, candidates, settings, spec, variant, strategies, end=split)
        model = fit(training, feature_names(strategies))
        # Model bytes are frozen before later-period diagnostics are evaluated.
        save_signed(output, "model", model)
        validation, validation_excluded = examples(frame, candidates, settings, spec, variant, strategies, start=split)
        train_report = compare(training, model); validation_report = compare(validation, model)
    result = {"state": "completed_historical_diagnostic", "training": train_report,
              "validation_previously_inspected": validation_report, "training_excluded": excluded,
              "validation_excluded": validation_excluded, "model_state": model["state"],
              "historical_review_passed": review_passed(validation_report),
              "selected_for_live": None, "broker_eligible": False, "orders_sent": 0}
    save_signed(output, "historical_report", result)
    save_signed(output, "inputs", {"candles.csv": digest(output / "candles.csv"),
                                  "candidates.json": digest(output / "candidates.json")})
    atomic_json(storage / "learned_ranker_active.json", {"run_dir": str(output.resolve())})
    return result


def validate(directory):
    manifest = signed(directory, "manifest"); model = signed(directory, "model")
    if (manifest["schema"] != "atlas_learned_candidate_ranker_v1" or manifest["method"] != METHOD
            or manifest["broker_eligible"] is not False or manifest["auto_promotion"] is not False
            or manifest["orders_sent"] != 0 or model["broker_eligible"] is not False
            or model["orders_sent"] != 0 or manifest["environment"] != environment_versions()):
        raise ValueError("learning_boundary_or_environment_changed")
    for name, expected in manifest["source_hashes"].items():
        path = (directory / "frozen_source" / name).resolve()
        path.relative_to((directory / "frozen_source").resolve())
        if digest(path) != expected: raise ValueError("frozen_learning_source_changed")
    for name, expected in signed(directory, "inputs").items():
        if name not in {"candles.csv", "candidates.json"} or digest(directory / name) != expected:
            raise ValueError("learning_input_changed")
    return manifest, model


def stage_comparison(comparison, offset):
    learner = comparison["learner"]["trade_list"][offset:offset+30]
    if learner:
        beginning = stamp(learner[0]["at"]); ending = max(stamp(row["horizon_end"]) for row in learner)
        baseline = [row for row in comparison["baseline"]["trade_list"]
                    if beginning <= stamp(row["at"]) and stamp(row["horizon_end"]) <= ending]
    else: baseline = []
    return {"learner": metrics(learner), "baseline": metrics(baseline)}


def once(directory, now):
    manifest, model = validate(directory)
    if model["state"] != "fitted_research_only":
        return {"state": "insufficient_training_evidence", "broker_eligible": False, "orders_sent": 0}
    source = Path(manifest["forward_source_run"]) / "observed_candles.csv"
    first_hash = digest(source); data = source.read_bytes()
    if sha(data) != first_hash or digest(source) != first_hash:
        return {"state": "waiting_for_consistent_source_snapshot", "broker_eligible": False, "orders_sent": 0}
    frame = prepare_frame(pd.read_csv(StringIO(data.decode("utf-8"))))
    times = pd.to_datetime(frame.time, utc=True)
    frame = frame[(times >= stamp(manifest["warmup_start"])) & (times + pd.Timedelta(minutes=1) <= stamp(now))].reset_index(drop=True)
    records = json.loads(frame.to_json(orient="records", date_format="iso", double_precision=15))
    integrity = directory / "forward_integrity.json"
    if integrity.exists():
        hashes = read(integrity)
        if set(hashes) != {"forward_candles.json", "forward_candidates.json", "forward_state.json"}:
            raise ValueError("incomplete_learning_forward_integrity")
        if any(digest(directory / name) != expected for name, expected in hashes.items()):
            raise ValueError("learning_forward_evidence_changed")
        old = read(directory / "forward_candles.json")
        if records[:len(old)] != old: raise ValueError("learning_observed_candles_revised")
        candidates = read(directory / "forward_candidates.json"); state = read(directory / "forward_state.json")
    else:
        if any((directory / name).exists() for name in ("forward_candles.json", "forward_candidates.json", "forward_state.json")):
            raise ValueError("unverified_learning_forward_evidence")
        candidates = []; state = {"last_index": max(249, int(pd.to_datetime(frame.time, utc=True).searchsorted(stamp(manifest["frozen_at"]))) - 2)}
    with tempfile.TemporaryDirectory(prefix="atlas_ranker_forward_") as temporary, patch.object(mt5, "initialize", deny), patch.object(mt5, "order_send", deny):
        settings = settings_for(manifest, temporary); store = KnowledgeStore(temporary)
        new, _, _ = cache_candidates(frame, settings, store, start_index=state["last_index"]+1)
        candidates.extend(new); state["last_index"] = max(state["last_index"], len(frame)-2)
        rows, excluded = examples(frame, candidates, settings, BrokerSpec(**manifest["spec"]), ExitVariant(**manifest["variant"]),
                                  manifest["strategies"], start=manifest["future_holdout_start"], end=manifest["deadline"])
        comparison = compare(rows, model, daily_limit=manifest["daily_paper_limit"])
    first = stage_comparison(comparison, 0); second = stage_comparison(comparison, 30)
    completed = comparison["learner"]["trades"] >= 60
    result = {"state": "completed_paper_requires_review" if completed else "window_completed_requires_review" if now >= stamp(manifest["deadline"]).to_pydatetime() else "collecting_frozen_model_paper",
              "checked_at": now.isoformat(), "frozen_at": manifest["frozen_at"], "deadline": manifest["deadline"],
              "first_stage": first, "validation_stage": second,
              "first_stage_passed": review_passed(first), "validation_stage_passed": review_passed(second),
              "learner_paper_trades": comparison["learner"]["trades"], "baseline_paper_trades": comparison["baseline"]["trades"],
              "comparison": comparison, "excluded": excluded, "historical_review_passed": signed(directory, "historical_report")["historical_review_passed"],
              "broker_eligible": False, "auto_promotion": False, "orders_sent": 0, "full_live_policy_parity": False}
    atomic_json(directory / "forward_candles.json", records)
    atomic_json(directory / "forward_candidates.json", candidates)
    atomic_json(directory / "forward_state.json", state)
    atomic_json(integrity, {name: digest(directory / name) for name in ("forward_candles.json", "forward_candidates.json", "forward_state.json")})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "once", "watch")); parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path); parser.add_argument("--storage", type=Path, default=ROOT / "storage")
    args = parser.parse_args()
    if args.mode == "init":
        if args.source is None: parser.error("--source required")
        result = initialize(args.source, args.run_dir, args.storage, datetime.now(timezone.utc))
        print(json.dumps({k: result[k] for k in ("state", "model_state", "historical_review_passed", "orders_sent")})); return
    with observation_lock(args.run_dir / "forward.lock"):
        while True:
            try: result = once(args.run_dir, datetime.now(timezone.utc))
            except Exception as exc:
                result = {"state": "blocked_evidence_review_required", "error": type(exc).__name__, "reason": str(exc), "broker_eligible": False, "orders_sent": 0}
            atomic_json(args.run_dir / "forward_status.json", result)
            if args.mode == "once" or result["state"] not in {"collecting_frozen_model_paper", "waiting_for_consistent_source_snapshot"}: return
            time.sleep(600)


if __name__ == "__main__": main()
