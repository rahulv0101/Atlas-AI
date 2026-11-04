"""Translate verified strategy entry evidence for the existing timing gate."""
from atlas_ai.strategies.minute_pack import GoldBreakoutRetestStrategy


def resolve_retest_timing_context(signal, df, context, strategies):
    resolved = dict(context)
    location = str(context.get("entry_location_state") or context.get("location_state") or context.get("location") or "unknown").lower()
    resolution = {
        "strategy": str(signal.strategy), "side": str(signal.side),
        "original_location": location, "resolved_location": location,
        "applied": False, "reason": "no_verified_strategy_retest",
    }
    if signal.strategy != "gold_breakout_retest" or signal.side not in {"buy", "sell"} or location != "breakout":
        return resolved, resolution
    strategy = next((item for item in strategies if isinstance(item, GoldBreakoutRetestStrategy) and item.name == signal.strategy), None)
    if strategy is None:
        return resolved, resolution
    try:
        evidence = strategy.confirmed_entry_evidence(df, signal.side)
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        resolution["reason"] = "strategy_retest_evidence_unavailable"
        resolution["error_type"] = type(exc).__name__
        return resolved, resolution
    if evidence is None:
        return resolved, resolution
    resolved["entry_location_state"] = "retest"
    resolution.update({"resolved_location": "retest", "applied": True,
                       "reason": "ordered_retest_verified_from_current_strategy_frame", "evidence": evidence})
    return resolved, resolution
