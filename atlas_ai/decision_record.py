"""Read-only provenance for a scan; never grants execution permission."""
from copy import deepcopy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def candle_manifest(frame, timeframe, *, broker_timezone="UTC"):
    import pandas as pd
    times = pd.to_datetime(frame.time, utc=True)
    start = times.iloc[-1]
    if timeframe == "D1":
        end = (start.tz_convert(broker_timezone) + pd.DateOffset(days=1)).tz_convert("UTC")
    else:
        end = start + pd.Timedelta(minutes={"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240}[timeframe])
    fields = [k for k in ("open", "high", "low", "close", "tick_volume", "spread", "real_volume") if k in frame]
    rows = [{"open_utc": at.isoformat(), **{k: float(frame.iloc[i][k]) for k in fields}}
            for i, at in enumerate(times)]
    return {"timeframe": timeframe, "last_open_utc": start.isoformat(), "last_close_utc": end.isoformat(),
            "bars": len(rows), "fields": fields, "candles_sha256": digest(rows), "timestamp_basis": "UTC"}


def scan_outcome(status):
    execution = dict(status.get("execution") or {})
    action = status.get("action", "unknown")
    submitted = bool(execution.get("request_id"))
    if action == "execute" and execution.get("success") is True:
        confirmed = any(execution.get(k) for k in ("order_id", "deal_id", "broker_order_id"))
        state = ("filled" if execution.get("deal_id") or execution.get("broker_status") == "filled"
                 else "submitted") if confirmed else "unknown"
    elif action == "blocked":
        state = "blocked" if submitted else "not_submitted"
    elif action == "failed":
        state = "failed" if execution else "unknown"
    elif action in {"paper", "hold"}:
        state = "not_submitted"
    else:
        state = "unknown"
    return {"decision_id": status.get("decision_id"), "state": state, "action": action,
            "reason": str(status.get("message", "")), "submitted_to_gate": submitted,
            "request_id": execution.get("request_id"), "success": execution.get("success"),
            **{k: execution.get(k) for k in ("retcode", "order_id", "deal_id", "broker_order_id")},
            "scope": "scan_entry_result_only; position management and closure are separate linked events"}


def bind_record(status, cycle):
    """Idempotently attach the same reference to derived panels and final scan result."""
    if not cycle or not cycle.get("decision_id"):
        return status
    status["decision_id"] = cycle["decision_id"]
    status["decision_snapshot"] = deepcopy(cycle)
    execution = status.get("execution")
    if isinstance(execution, dict):
        execution["decision_id"] = cycle["decision_id"]
    outcome = scan_outcome(status)
    ref = {"decision_id": cycle["decision_id"], "as_of_utc": cycle.get("as_of_utc"),
           "snapshot_sha256": digest(cycle), "outcome_sha256": digest(outcome)}
    status["decision_ref"] = ref
    status["current_execution"] = outcome
    for name in ("decision_trace", "decision_analysis", "context_snapshot", "decision_explanation",
                 "pre_trade_memo", "chart_features", "signal_generation", "higher_timeframe",
                 "timing_discipline", "setup_hunter", "setup_quality_observation", "smc_composite",
                 "market", "trader_cognition", "shadow_advice", "contextual_ranking", "conviction_adjustment",
                 "setup_quality_filter", "meta_model", "execution_gate"):
        if isinstance(status.get(name), dict):
            status[name]["decision_id"] = cycle["decision_id"]
            status[name]["decision_ref"] = deepcopy(ref)
    trace = status.get("decision_trace")
    if isinstance(trace, dict):
        trace["current_execution"] = deepcopy(outcome)
        trace.setdefault("execution_gate", {}).update(decision_id=cycle["decision_id"],
                                                      request_id=outcome["request_id"] or "")
    context = status.get("context_snapshot")
    entry = cycle.get("candles", {}).get(status.get("timeframe"), {})
    if isinstance(context, dict) and entry:
        context["timestamp"] = entry["last_open_utc"]
        context["candle_open_utc"] = entry["last_open_utc"]
        context["candle_close_utc"] = entry["last_close_utc"]
        context["evaluated_at_utc"] = cycle.get("as_of_utc")
    return status


def historical_execution(automation):
    truth = dict(automation.get("execution_truth") or automation.get("last_execution_truth") or {})
    return {"scope": "historical_last_execution; not the current scan outcome", "truth": truth}


def cycle_failure(cycle, *, symbol, timeframe, error):
    """Do not combine a new exception with the prior scan's analysis or fill."""
    return bind_record({"symbol": symbol, "timeframe": timeframe, "action": "degraded",
                        "message": "Live cycle error: " + str(error),
                        "cycle_error": {"error": str(error)}, "decision_analysis": {},
                        "decision_trace": {}, "context_snapshot": {}}, cycle)


def validate_record(status):
    """Validate rather than repair an API payload. Legacy evidence stays unverified."""
    import pandas as pd
    errors = []
    ref = status.get("decision_ref") or {}
    snapshot = status.get("decision_snapshot") or {}
    outcome = status.get("current_execution") or {}
    decision_id = status.get("decision_id")
    if not decision_id:
        errors.append("missing_decision_id")
    if not ref or ref.get("decision_id") != decision_id or snapshot.get("decision_id") != decision_id:
        errors.append("snapshot_identity_mismatch")
    if ref.get("snapshot_sha256") != digest(snapshot):
        errors.append("snapshot_hash_mismatch")
    if outcome.get("decision_id") != decision_id or ref.get("outcome_sha256") != digest(outcome):
        errors.append("outcome_mismatch")
    for name in ("decision_analysis", "decision_trace", "context_snapshot", "timing_discipline", "higher_timeframe"):
        if status.get(name) and status[name].get("decision_ref") != ref:
            errors.append(name + "_reference_mismatch")
    try:
        as_of = pd.Timestamp(snapshot["as_of_utc"])
        if as_of.tzinfo is None:
            raise ValueError("naive_as_of")
        for tf, candle in snapshot.get("candles", {}).items():
            start, end = pd.Timestamp(candle["last_open_utc"]), pd.Timestamp(candle["last_close_utc"])
            if start.tzinfo is None or end.tzinfo is None or not start < end <= as_of:
                errors.append(tf + "_not_closed_at_cutoff")
    except (KeyError, ValueError, TypeError):
        errors.append("evaluation_time_unavailable")
    return {"verified": not errors, "decision_id": decision_id, "errors": errors,
            "scope": "scan provenance only; separate runtime controls and historical evidence are not atomic"}
