"""Validated demo closed-position evidence for an explicitly selected filter policy."""
from datetime import datetime, timezone
import math
from types import SimpleNamespace


def confirmed_demo_statistics(evidence, *, now=None, max_age_seconds=180):
    if not isinstance(evidence, dict) or evidence.get("available") is not True:
        raise ValueError("confirmed_evidence_unavailable")
    if evidence.get("schema") != "atlas_closed_position_ledger_v1":
        raise ValueError("confirmed_evidence_schema_invalid")
    try:
        stamp = datetime.fromisoformat(str(evidence.get("updated_at", "")).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    except (ValueError, TypeError):
        raise ValueError("confirmed_evidence_timestamp_invalid") from None
    if not 0 <= age <= max_age_seconds:
        raise ValueError("confirmed_evidence_not_fresh")
    rows = evidence.get("strategy_statistics")
    if not isinstance(rows, dict):
        raise ValueError("confirmed_evidence_statistics_invalid")
    result = {}
    for strategy, row in rows.items():
        if not isinstance(strategy, str) or not strategy or not isinstance(row, dict):
            raise ValueError("confirmed_evidence_statistics_invalid")
        wins, losses = row.get("wins"), row.get("losses")
        if any(type(n) is not int or n < 0 for n in (wins, losses)):
            raise ValueError("confirmed_evidence_counts_invalid")
        try:
            pnl = float(row["pnl"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("confirmed_evidence_pnl_invalid") from None
        if not math.isfinite(pnl):
            raise ValueError("confirmed_evidence_pnl_invalid")
        result[strategy] = SimpleNamespace(wins=wins, losses=losses, pnl=pnl,
                                          win_rate=wins / max(1, wins + losses))
    return result
