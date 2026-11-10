"""Read-only counterfactual review of recorded timing and HTF rejections."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import MetaTrader5 as mt5

from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from tools.timing_discipline_selectivity_report import (
    _extract_candidate, _parse_dt, _simulate, _summarize,
)


def nonoverlapping(rows):
    """Conservatively keep one hypothetical position at a time per cohort."""
    selected = []
    last_exit = None
    for row in sorted(rows, key=lambda r: r["entry_bar_time"]):
        entry = pd.Timestamp(row["entry_bar_time"])
        if last_exit is not None and entry <= last_exit:
            continue
        selected.append(row)
        last_exit = pd.Timestamp(row["exit_bar_time"])
    return selected


def summarize(rows):
    result = {}
    for name, field in (("gross", "gross_r_multiple"),
                        ("recorded_spread_only", "spread_only_r"),
                        ("recorded_spread_plus_assumed_slippage", "recorded_spread_net_r_multiple")):
        known = [{**r, "r_multiple": r[field]} for r in rows if r.get(field) is not None]
        stats = _summarize(known)
        stats.pop("hold_bars_distribution", None)
        result[name] = stats
    return result


def run(start, end, output):
    settings = replace(load_settings(), timeframe="M1", execute_trades=False)
    if end > datetime.now(timezone.utc):
        raise ValueError("End must not be in the future")
    candidates = []
    rejected = Counter()
    seen = set()
    journal = ROOT / "storage/events.jsonl"
    with journal.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            stamp = _parse_dt(str(event.get("time", "")))
            if stamp is None or not start <= stamp <= end:
                continue
            message = str(event.get("message", "")).lower()
            if not ("timing discipline blocked trade" in message
                    or message.startswith("higher-timeframe alignment required")):
                continue
            c = _extract_candidate(event, journal, include_other_blockers=True)
            if c is None:
                rejected["missing_clock_risk_or_provenance"] += 1
                continue
            key = (c.timestamp, c.strategy, c.side, c.message)
            if key not in seen:
                seen.add(key)
                candidates.append(c)
    feed = MarketDataFeed(settings)
    # Request forward bars too; do not include the current unfinished candle.
    cutoff = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    fetch_end = min(cutoff - pd.Timedelta(minutes=1), end + pd.Timedelta(minutes=settings.backtest_max_hold_bars + 2))
    frame = feed.get_rates_range(start, fetch_end)
    if frame.empty:
        raise RuntimeError("No broker candles available for replay")
    symbol_info = mt5.symbol_info(settings.symbol)
    broker_point = float(getattr(symbol_info, "point", 0) or 0)
    if broker_point <= 0 or abs(broker_point - settings.backtest_point_size) > 1e-9:
        raise ValueError("Configured replay point size does not match the broker symbol")
    frame.to_csv(output.with_suffix(".candles.csv"), index=False)
    cohorts = {}
    all_rows = []
    for group in ("timing_blocked", "higher_timeframe_blocked"):
        members = [c for c in candidates if c.group == group]
        rows, skipped = _simulate(members, frame, settings)
        for row in rows:
            row["spread_only_r"] = (None if row["recorded_spread_points"] is None else
                row["gross_r_multiple"] - row["recorded_spread_points"] / row["stop_loss_points"])
        thinned = nonoverlapping(rows)
        plausible = [r for r in rows if r["recorded_spread_points"] is not None
                     and r["stop_loss_points"] >= r["recorded_spread_points"]]
        cohorts[group] = {"eligible": len(members), "replayed": len(rows),
            "skipped_unmatched_incomplete_or_gap": skipped,
            "all_signals": summarize(rows),
            "nonoverlapping_count": len(thinned), "nonoverlapping": summarize(thinned),
            "subspread_stop_count": sum(r["recorded_spread_points"] is not None
                and r["stop_loss_points"] < r["recorded_spread_points"] for r in rows),
            "without_subspread_stops_nonoverlapping": summarize(nonoverlapping(plausible)),
            "score_at_least_65_without_subspread_stops_nonoverlapping": summarize(
                nonoverlapping([r for r in plausible if r["confidence"] >= .65])),
            "nonoverlapping_by_session": {s: summarize([r for r in thinned if r["session"] == s])
                for s in sorted({r["session"] for r in thinned})}}
        all_rows.extend(rows)
    payload = {"schema": "atlas_blocked_setup_replay_v1", "captured_at": datetime.now(timezone.utc).isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "fetch_end": fetch_end.isoformat(),
            "bars": len(frame), "symbol": settings.symbol, "timeframe": "M1"},
        "assumptions": {"entry": "next M1 open after recorded event minute",
            "point_size": settings.backtest_point_size, "maximum_hold_bars": settings.backtest_max_hold_bars,
            "broker_point_size_verified": broker_point,
            "slippage_bps": settings.backtest_slippage_cost_bps, "ambiguous_bar": "stop_first",
            "management": "existing backtest simulator; not a reconstruction of live tick management",
            "commission": "not supplied; omitted in all scenarios",
            "overlap": "all signals correlated; separate greedy nonoverlapping cohort also reported"},
        "excluded": dict(rejected), "cohorts": cohorts,
        "limitations": ["No matched allowed-trade control; cannot establish causal filter benefit.",
            "M1 OHLC cannot reconstruct bid/ask ticks, intrabar ordering, fills or actual live management.",
            "Portfolio daily limits, cooldowns and session-forced exits are not reconstructed; cohort R cannot be summed into an account-return forecast.",
            "Counterfactual winners are possible missed entries, not proven executable profits.",
            "Other gates may still have rejected these candidates; replay is not permission to bypass them.",
            "Sub-spread recorded stops may reflect earlier unit defects; both full and excluded-case sensitivities are reported without rewriting historical parameters.",
            "Score stages differ across early and late rejections; score-65 sensitivity is descriptive, not probability calibration.",
            "Short observational sample and shared market moves do not establish sustainable profitability."],
        "policy_changed": False, "orders_submitted": False}
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output.with_suffix(".samples.json").write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    start, end = _parse_dt(args.start), _parse_dt(args.end)
    if start is None or end is None or start >= end:
        parser.error("A valid increasing UTC date range is required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run(start, end, args.output)
    print(json.dumps({"output": str(args.output), "window": result["window"],
        "counts": {k: {f: v[f] for f in ("eligible", "replayed", "nonoverlapping_count")} for k, v in result["cohorts"].items()}}))
