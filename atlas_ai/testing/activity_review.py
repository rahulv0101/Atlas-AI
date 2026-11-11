"""A fixed-window operational review. Never modifies entry rules or sends orders."""
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.broker_clock import broker_time_to_utc
from atlas_ai.learning.observation_checkpoint import account_scope, load_checkpoint, observation_lock
from atlas_ai.testing.decision_archive import encoded, index_rows, sha


def timestamp(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("activity_timestamp_requires_timezone")
    return result.astimezone(timezone.utc)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def initialize(storage, settings, journal, now):
    folder = Path(storage) / "activity_review"
    folder.mkdir(parents=True, exist_ok=True)
    with observation_lock(folder / "review.lock"):
        path = folder / "protocol.json"
        if path.exists():
            raise FileExistsError("activity_protocol_exists_resume_without_reset")
        load_checkpoint(Path(journal).with_suffix(".checkpoint.json"), settings, journal=journal)
        start = timestamp(now.isoformat())
        protocol = {
            "schema": "atlas_activity_review_v1", "started_at": start.isoformat(),
            "deadline": (start + timedelta(days=7)).isoformat(), "calendar_days": 7,
            "minimum_natural_cycles": 1, "account_scope": account_scope(settings),
            "broker_clock_timezone": settings.mt5_server_timezone,
            "evaluator_sha256": sha(Path(__file__).read_bytes()),
            "journal": str(Path(journal).resolve()), "broker_eligible": False, "orders_sent": 0,
            "rule": "At least one strategy-linked protected natural demo cycle wholly inside the window.",
            "sampling": "Published observations are samples, not unique setups or complete decision coverage.",
        }
        atomic_json(path, protocol)
        path.with_suffix(".sha256").write_text(sha(path.read_bytes()), encoding="ascii")
        return protocol


def classify(status):
    """Return independent observations; entry eligibility never means broker approval."""
    analysis = status.get("decision_analysis") or {}
    signals = status.get("signals")
    directional = [row for row in signals or [] if isinstance(row, dict)
                   and row.get("side") in {"buy", "sell"} and float(row.get("confidence", 0)) > 0]
    chosen = status.get("chosen") or {}
    has_direction = bool(directional or chosen.get("side") in {"buy", "sell"})
    fresh = status.get("freshness_runtime") or {}
    blocking = status.get("blocker_classification") or {}
    safety = status.get("safety_layer") or {}
    execution = status.get("execution_state") or {}
    timing = status.get("timing_discipline") or {}
    eligible = ((analysis.get("decision_protocol") or {}).get("act") or {}).get("execution_request_eligible")
    reasons = set()
    reasons.update(str(x) for x in analysis.get("hard_blockers", []) if isinstance(x, str))
    reasons.update(str(x) for x in (status.get("decision_explanation") or {}).get("reason_codes", []) if isinstance(x, str))
    if timing.get("passed") is False and timing.get("enabled") is True:
        reasons.add(str(timing.get("reason_code") or "timing_not_passed"))
    if fresh.get("is_stale") is True or fresh.get("market_data_reasons") or blocking.get("class") == "runtime_or_data":
        category = "technical_or_data_block"
    elif execution.get("kill_switch_active") is True or execution.get("execution_gate_enabled") is False:
        category = "operator_or_execution_control"
    elif safety.get("safety_lock_active") is True or safety.get("cooldown_active") is True or blocking.get("class") == "safety_gate":
        category = "risk_or_safety_block"
    elif eligible is True:
        category = "analysis_eligible_requires_execution_gates"
    elif not has_direction and isinstance(signals, list):
        category = "no_directional_signal"
    elif has_direction and (eligible is False or reasons or blocking.get("class") in {"signal_quality", "quality_gate"}):
        category = "directional_signal_filtered"
    else:
        category = "insufficient_evidence"
    if blocking.get("class"):
        reasons.add("classification:" + str(blocking["class"]))
    return {
        "category": category, "directional": has_direction, "analysis_eligible": eligible is True,
        "strategy_samples": sorted({str(row.get("strategy", "unknown")) for row in directional}),
        "reason_codes": sorted(reasons),
        "coverage_gap": (analysis.get("strategy_coverage") or {}).get("coverage_gap") is True,
        "session": str(status.get("session") or "unknown"),
    }


def increment(counts, key):
    counts[key] = counts.get(key, 0) + 1


def review(storage, settings, now):
    now = timestamp(now.isoformat())
    storage = Path(storage); folder = storage / "activity_review"
    if not (folder / "protocol.json").exists():
        return {"state": "not_initialized", "broker_eligible": False, "orders_sent": 0}
    with observation_lock(folder / "review.lock"):
        path = folder / "protocol.json"
        protocol_hash = sha(path.read_bytes())
        if protocol_hash != path.with_suffix(".sha256").read_text().strip():
            raise ValueError("activity_protocol_changed")
        protocol = read(path)
        if (protocol.get("schema") != "atlas_activity_review_v1" or protocol.get("account_scope") != account_scope(settings)
                or protocol.get("broker_clock_timezone") != settings.mt5_server_timezone
                or protocol.get("evaluator_sha256") != sha(Path(__file__).read_bytes())
                or protocol.get("broker_eligible") is not False or protocol.get("orders_sent") != 0
                or protocol.get("minimum_natural_cycles") != 1 or protocol.get("calendar_days") != 7):
            raise ValueError("activity_scope_or_boundary_changed")
        start = timestamp(protocol["started_at"]); end = timestamp(protocol["deadline"])
        if end - start != timedelta(days=7) or now < start:
            raise ValueError("invalid_activity_window")
        state_path = folder / "checkpoint.json"
        if state_path.exists():
            wrapper = read(state_path); state = wrapper["state"]
            if sha(encoded(state)) != wrapper["sha256"] or state["protocol_sha256"] != protocol_hash:
                raise ValueError("activity_checkpoint_changed")
        else:
            state = {"protocol_sha256": protocol_hash, "cursor": 0, "prefix_sha256": sha(encoded([])),
                     "samples": 0, "excluded": {}, "categories": {}, "reason_codes": {}, "strategies": {},
                     "sessions": {}, "days": {}, "directional_samples": 0, "analysis_eligible_samples": 0,
                     "coverage_gap_samples": 0, "verified_cycle_ids": [], "cycle_days": {}, "first_sample": None, "last_sample": None}
        archive = storage / "replay_evidence"
        # Hold the writer lock while reading the append-only index and new capsules.
        with observation_lock(archive / "archive.lock"):
            rows = index_rows(archive); cursor = state["cursor"]
            if cursor > len(rows) or sha(encoded(rows[:cursor])) != state["prefix_sha256"]:
                raise ValueError("activity_archive_prefix_changed")
            for row in rows[cursor:]:
                blob = (archive / "records" / (row["record_id"] + ".json.gz")).read_bytes()
                if sha(blob) != row["blob_sha256"]:
                    raise ValueError("activity_archive_record_changed")
                record = json.loads(gzip.decompress(blob))
                if sha(encoded({k: v for k, v in record.items() if k != "observed_at"})) != row["record_id"]:
                    raise ValueError("activity_record_identity_changed")
                try:
                    stamp = timestamp(record["publication"]["updated_at"])
                    observed = timestamp(record["observed_at"])
                except (ValueError, KeyError, TypeError):
                    increment(state["excluded"], "unverified_timestamp"); continue
                if not start <= stamp < end or not start <= observed < end:
                    increment(state["excluded"], "outside_window"); continue
                if record.get("publication_fresh") is not True or not 0 <= (observed - stamp).total_seconds() <= 180:
                    increment(state["excluded"], "stale_or_future"); continue
                facts = classify(record["publication"])
                state["samples"] += 1
                state["directional_samples"] += int(facts["directional"])
                state["analysis_eligible_samples"] += int(facts["analysis_eligible"])
                state["coverage_gap_samples"] += int(facts["coverage_gap"])
                increment(state["categories"], facts["category"])
                increment(state["sessions"], facts["session"])
                for code in facts["reason_codes"]: increment(state["reason_codes"], code)
                for strategy in facts["strategy_samples"]: increment(state["strategies"], strategy)
                day = stamp.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
                daily = state["days"].setdefault(day, {"sampled_publications": 0, "directional_samples": 0})
                daily["sampled_publications"] += 1; daily["directional_samples"] += int(facts["directional"])
                state["first_sample"] = min(state["first_sample"] or stamp.isoformat(), stamp.isoformat())
                state["last_sample"] = max(state["last_sample"] or stamp.isoformat(), stamp.isoformat())
            state["cursor"] = len(rows); state["prefix_sha256"] = sha(encoded(rows))
        journal = Path(protocol["journal"])
        _, seen, managed, summary = load_checkpoint(journal.with_suffix(".checkpoint.json"), settings, journal=journal)
        natural = summary.get("lifecycle_acceptance") or {}
        if natural.get("state") == "verified" and natural.get("manual_and_forced_tests_count_as_acceptance") is False:
            for cycle in natural.get("verified_end_to_end_cycles", []):
                pos = str(cycle["position_id"])
                if (pos not in managed or not cycle.get("decision_id") or not cycle.get("strategy")
                        or cycle.get("management_evidence") != "broker_open_position_with_protective_sl_tp"):
                    continue
                deals = [deal for deal in seen.values() if str(deal.get("position_id")) == pos]
                times = [broker_time_to_utc(deal["broker_time_msc"] / 1000, settings) for deal in deals]
                if times and start <= min(times) <= max(times) < end and max(times) <= now and pos not in state["verified_cycle_ids"]:
                    state["verified_cycle_ids"].append(pos)
                    increment(state["cycle_days"], max(times).astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat())
        expired = now >= end
        cycles = len(state["verified_cycle_ids"])
        local_zone = ZoneInfo("Africa/Johannesburg")
        day = start.astimezone(local_zone).date()
        last_day = min(now, end - timedelta(microseconds=1)).astimezone(local_zone).date()
        daily_report = {}
        while day <= last_day:
            key = day.isoformat()
            sampled = state["days"].get(key, {"sampled_publications": 0, "directional_samples": 0})
            daily_report[key] = {**sampled, "verified_natural_cycles": state["cycle_days"].get(key, 0),
                                 "observation_state": "sampled" if sampled["sampled_publications"] else "no_samples"}
            day += timedelta(days=1)
        result = {
            "schema": "atlas_activity_report_v1", "checked_at": now.isoformat(),
            "started_at": start.isoformat(), "deadline": end.isoformat(),
            "state": "activity_requirement_met" if cycles else "activity_requirement_failed" if expired else "observing",
            "minimum_natural_cycles": 1, "verified_natural_cycles_in_window": cycles,
            "sampled_publications": state["samples"], "directional_publications": state["directional_samples"],
            "analysis_eligible_publications": state["analysis_eligible_samples"],
            "coverage_gap_publications": state["coverage_gap_samples"],
            "categories": state["categories"], "reason_codes": state["reason_codes"],
            "directional_strategy_samples": state["strategies"], "session_samples": state["sessions"],
            "daily_samples_sast": daily_report, "excluded": state["excluded"],
            "first_sample": state["first_sample"], "last_sample": state["last_sample"],
            "coverage": "Sampled publications only. Counts are not unique setups, trades, uptime, or missed profits.",
            "profitability_proven": False, "broker_eligible": False, "orders_sent": 0,
            "next_step": "Review technical blocks, strategy coverage and filter rejections; test any proposed changes separately.",
        }
        atomic_json(state_path, {"state": state, "sha256": sha(encoded(state))})
        atomic_json(folder / "status.json", result)
        return result
