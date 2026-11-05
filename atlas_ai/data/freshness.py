"""Validate cycle and independently timestamped market evidence at submission."""
from datetime import datetime, timezone
import math


def execution_freshness(*, status_age_ms, max_age_ms=120000, market_fetch=None, now=None):
    try:
        age = float(status_age_ms)
        cycle_stale = not math.isfinite(age) or age < 0 or age > max_age_ms
    except (TypeError, ValueError, OverflowError):
        age, cycle_stale = None, True
    result = {"status_age_ms": age, "is_stale": cycle_stale}
    if market_fetch is None:
        return result
    checked = now or datetime.now(timezone.utc)
    reasons = []
    ages = {}
    if not market_fetch.get("ok") or market_fetch.get("timestamp_basis") != "UTC":
        reasons.append("market_clock_unavailable")
    for key, limit in (("latest_tick_utc", max_age_ms), ("latest_bar_utc", market_fetch.get("bar_stale_after_ms"))):
        try:
            value = datetime.fromisoformat(str(market_fetch.get(key, "")).replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise ValueError("Unspecified timestamp basis")
            elapsed = (checked - value).total_seconds() * 1000
            threshold = float(limit)
            if not math.isfinite(threshold) or threshold < 0:
                raise ValueError("Invalid freshness threshold")
            ages[key] = round(elapsed, 2)
            if elapsed < -5000 or elapsed > threshold:
                reasons.append(key + "_stale_or_future")
        except (TypeError, ValueError, OverflowError):
            reasons.append(key + "_unavailable")
    result.update({"market_data_ages_ms": ages, "market_data_reasons": reasons, "is_stale": bool(cycle_stale or reasons)})
    return result
