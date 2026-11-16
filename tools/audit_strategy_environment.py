"""Read-only environment checks and receipt-bound structural rejection traces.

Never prints environment values or contacts an advisor/broker. Replays the
unchanged research policy solely to expose its existing rejection reasons.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv.parser import parse_stream
from dotenv.variables import parse_variables


def inspect_env(path, environment=None):
    """Return key names/checks only, including for malformed secret lines."""
    environment = os.environ if environment is None else environment
    values = {}
    counts = Counter()
    malformed = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for binding in parse_stream(stream):
            if binding.error:
                malformed.append(binding.original.line)
            elif binding.key is not None:
                counts[binding.key] += 1
                if binding.value is None:
                    values[binding.key] = None
                else:
                    resolution = {**values, **environment}
                    values[binding.key] = ''.join(atom.resolve(resolution) for atom in parse_variables(binding.value))
    overridden = sorted(k for k, v in values.items() if k in environment and environment[k] != v)
    # Match dotenv's override=False semantics, including an explicitly empty
    # process variable. Never echo either side of a mismatch.
    effective = {k: environment.get(k, v) for k, v in values.items()}
    api_keys = ["GEMINI_API_KEY", "OPENAI_API_KEY"]
    numeric_issues = []
    numeric_keys = {"MAX_RISK_PER_TRADE": float, "MAX_DAILY_DRAWDOWN": float,
                    "MAX_WEEKLY_DRAWDOWN": float, "BASE_LOT": float,
                    "HFM_LOGIN": int, "MAX_OPEN_TRADES": int}
    import math
    for key, convert in numeric_keys.items():
        if key not in effective:
            continue
        try:
            value = convert(effective[key])
            if not math.isfinite(value) or value <= 0:
                numeric_issues.append(key)
        except (ValueError, TypeError, OverflowError):
            numeric_issues.append(key)
    old_paths = sorted(k for k, v in effective.items()
                       if isinstance(v, str) and "c:\\users\\user\\" in v.lower().replace("/", "\\"))
    terminal = effective.get("HFM_TERMINAL_PATH")
    return {"file_present": True, "key_count": len(values),
            "malformed_line_numbers": malformed,
            "duplicate_keys": sorted(k for k, n in counts.items() if n > 1),
            "process_override_keys": overridden,
            "invalid_positive_numeric_keys": numeric_issues,
            "old_account_path_keys": old_paths,
            "terminal_path_exists": bool(terminal and Path(terminal).is_file()),
            "dotenv_api_key_configured": {k: bool(values.get(k)) for k in api_keys},
            "api_key_configured": {k: bool(effective.get(k, environment.get(k))) for k in api_keys},
            "api_authentication": "not_tested",
            "note": "Presence is not API validity. No secret values are included; no API requests were made."}


def trace_structural(source, baseline):
    import MetaTrader5 as mt5
    import pandas as pd
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
    from atlas_ai.testing.policy_replay import replay
    from atlas_ai.trader import AtlasTrader
    from tools.learn_candidate_ranker import digest, signed, settings_for
    from tools.m5_calibration_study import deny, load_reused_frames

    p = signed(source, "protocol")
    report = signed(source, "report")
    receipt = signed(source, "prediction_receipt")
    sources = signed(source, "source_receipt")
    if report["state"] != "completed_research_only":
        raise ValueError("completed_structural_report_required")
    for manifest in [report, receipt, sources]:
        if manifest["protocol_sha256"] != digest(source / "protocol.json"):
            raise ValueError("structural_protocol_changed")
    if (report["prediction_receipt_sha256"] != digest(source / "prediction_receipt.json")
            or receipt["candidate_sha256"] != digest(source / "candidate_cache.json")
            or receipt["predictions_sha256"] != digest(source / "predictions.jsonl")):
        raise ValueError("structural_predictions_changed")
    for name, expected in sources["hashes"].items():
        if digest(source / "frozen_source" / name) != expected:
            raise ValueError("frozen_source_changed")
        if name.startswith("atlas_ai/") and digest(ROOT / name) != expected:
            raise ValueError("current_policy_changed_use_frozen_version")
    if (digest(baseline / "report.json") != p["source_report_sha256"]
            or digest(baseline / "protocol.json") != p["source_protocol_sha256"]):
        raise ValueError("baseline_changed")
    rows = signed(source, "candidate_cache")["rows"]
    original_timing = AtlasTrader._timing_discipline_snapshot
    timing = {}

    def observe_timing(self, signal, context, status=None):
        result = original_timing(self, signal, context, status)
        timing[(status["updated_at"], signal.strategy)] = {
            k: result[k] for k in ["passed", "missing", "reasons", "observed"]}
        return result

    with tempfile.TemporaryDirectory(prefix="atlas_rejection_trace_") as temporary:
        with patch.object(mt5, "initialize", deny), patch.object(mt5, "order_send", deny):
            frames = load_reused_frames(baseline, signed(baseline, "protocol"))
            frame = frames["M5"].copy()
            frame["spread"] = frame.spread.shift(1)
            cfg = settings_for(p, temporary)
            spec = BrokerSpec(**p["spec"])
            traces = []
            for period, begin, end in [("development", p["windows"]["development_start"], p["windows"]["split"]),
                                       ("validation", p["windows"]["split"], p["windows"]["validation_end"])]:
                rejections = []
                with patch.object(AtlasTrader, "_timing_discipline_snapshot", observe_timing):
                    actual = replay(frame, rows, cfg, spec,
                                    ExitVariant("configured", cfg.backtest_break_even_lock_r, 3.),
                                    KnowledgeStore(temporary), p["limits"],
                                    start=pd.Timestamp(begin).to_pydatetime(), end=pd.Timestamp(end).to_pydatetime(),
                                    audit=rejections.append)
                expected = report["periods"][period]["structural_proposal"]
                # review() is report metadata, not part of replay(). Compare
                # all replay fields rather than only aggregate trade counts.
                if actual != {k: v for k, v in expected.items() if k != "review"}:
                    raise ValueError("rejection_replay_does_not_match_recorded_result")
                for item in rejections:
                    signal = item["signal"]
                    trace = {"period": period, "available_at": item["available_at"], "reason": item["reason"]}
                    if signal:
                        trace["timing"] = timing.get((item["available_at"], signal["strategy"]))
                        stop_points = max(signal["stop_loss_points"],
                                          max(spec.trade_stops_level, spec.trade_freeze_level)
                                          + max(2, round(float(frame.spread.iloc[item["index"] + 1]) * .35)))
                        trace["minimum_lot_stop_risk_cash"] = abs(spec.cash(-stop_points * spec.point, spec.volume_min))
                        trace["nominal_starting_risk_budget_cash"] = cfg.backtest_initial_balance * cfg.max_risk_per_trade
                        trace["risk_note"] = "Stop risk alone excludes fees/slippage; nominal historical account, not a funding recommendation."
                    traces.append(trace)
    return {"state": "verified_replay_matches_original", "traces": traces,
            "missing_timing_counts": dict(Counter(m for t in traces if t.get("timing")
                                                    for m in t["timing"]["missing"])),
            "orders_sent": 0, "policy_changed": False, "broker_eligible": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--structural", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.resolve().relative_to(ROOT / "storage")
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "environment": inspect_env(args.env)}
    if args.structural:
        if not args.baseline:
            parser.error("--baseline is required with --structural")
        result["structural"] = trace_structural(args.structural, args.baseline)
    from atlas_ai.atomic_files import atomic_json
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2))
