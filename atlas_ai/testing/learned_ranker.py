"""Bounded offline candidate learning. No broker calls or trading-state writes."""
from collections import Counter
from datetime import timedelta
import math

import numpy as np
import pandas as pd

from atlas_ai.models import TradeSignal
from atlas_ai.testing.historical_broker import simulate


METHOD = {
    "model": "ridge_expected_net_r", "regularization": 10.0, "target_clip_r": 5.0,
    "minimum_training_rows": 300, "minimum_training_dates": 10,
    "prediction_threshold_r": .10, "training_fraction": .70,
    "slippage_points_per_side": 3.0, "minimum_review_trades": 30,
    "minimum_review_dates": 2, "minimum_profit_factor": 1.1, "maximum_drawdown_r": 6.0,
    "candidate_scope": "Existing gated base-strategy signals; learned ranking/abstention only.",
    "training_sampling": "Nonoverlapping full-horizon groups; same-bar candidates share unit weight.",
    "forward_policy": "Frozen model and threshold; no automatic retraining or promotion.",
}


def stamp(value):
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        raise ValueError("ranker_timestamp_requires_utc_offset")
    return result.tz_convert("UTC")


def feature_names(strategies):
    return ["intercept", "confidence", "return_1_atr", "return_5_atr", "body_atr",
            "distance_20_atr", "spread_atr", "relative_volume", "htf_agreement",
            "trend_regime", "hour_sin", "hour_cos", *["strategy:" + name for name in strategies]]


def feature_frame(frame):
    result = frame.copy()
    previous = frame.close.shift(1)
    ranges = pd.concat([frame.high - frame.low, (frame.high - previous).abs(),
                        (frame.low - previous).abs()], axis=1).max(axis=1)
    result["_atr"] = ranges.rolling(14, min_periods=14).mean()
    result["_mean20"] = frame.close.rolling(20, min_periods=20).mean()
    result["_volume20"] = frame.tick_volume.rolling(20, min_periods=20).mean()
    return result


def features(frame, item, signal, strategies, point):
    i = int(item["index"])
    at = stamp(item["available_at"])
    candle = pd.Timestamp(frame.time.iloc[i])
    candle = candle.tz_localize("UTC") if candle.tzinfo is None else candle.tz_convert("UTC")
    if at != candle + pd.Timedelta(minutes=1) or i < 20:
        raise ValueError("candidate_available_time_or_warmup_invalid")
    row = frame.iloc[i]; atr = float(row["_atr"])
    if not math.isfinite(atr) or atr <= 0 or signal["strategy"] not in strategies:
        raise ValueError("invalid_feature_inputs")
    direction = 1 if signal["side"] == "buy" else -1
    def bounded(value):
        value = float(value)
        if not math.isfinite(value): raise ValueError("nonfinite_feature")
        return float(np.clip(value, -3, 3))
    hour = at.hour + at.minute / 60
    bias = item.get("higher_tf_bias")
    agreement = 1 if bias == signal["side"] else -1 if bias in {"buy", "sell"} else 0
    values = [1., bounded(signal["confidence"]),
              bounded(direction * (row.close - frame.close.iloc[i-1]) / atr),
              bounded(direction * (row.close - frame.close.iloc[i-5]) / atr),
              bounded(direction * (row.close - row.open) / atr),
              bounded(direction * (row.close - row["_mean20"]) / atr),
              bounded(row.spread * point / atr),
              bounded(row.tick_volume / max(1., row["_volume20"]) - 1),
              agreement, float((item.get("regime") or {}).get("name") == "trend"),
              math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)]
    values.extend(float(signal["strategy"] == name) for name in strategies)
    return values


def examples(frame, candidates, settings, spec, variant, strategies, *, start=None, end=None):
    """Label only complete continuous horizons; future prices never enter features."""
    prepared = feature_frame(frame); rows = []; excluded = Counter()
    hold = settings.backtest_max_hold_bars
    times = pd.to_datetime(frame.time, utc=True)
    for item in candidates:
        i = int(item["index"]); at = stamp(item["available_at"])
        if start is not None and at < stamp(start): continue
        if end is not None and at >= stamp(end): continue
        last = i + hold
        if last >= len(frame): excluded["incomplete_horizon"] += 1; continue
        resolved_by = times.iloc[last] + pd.Timedelta(minutes=1)
        if end is not None and resolved_by > stamp(end):
            excluded["purged_boundary_horizon"] += 1; continue
        sequence = times.iloc[i:last+1]
        if sequence.iloc[0] + pd.Timedelta(minutes=1) != at or not sequence.diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            excluded["gapped_horizon"] += 1; continue
        for raw in item["signals"]:
            if raw["side"] not in {"buy", "sell"} or raw["confidence"] <= 0: continue
            vector = features(prepared, item, raw, strategies, spec.point)
            signal = TradeSignal(**raw)
            outcome = simulate(frame, i+1, signal, spec.volume_min, spec, settings, variant)
            rows.append({"at": at.isoformat(), "horizon_end": resolved_by.isoformat(),
                         "strategy": raw["strategy"], "side": raw["side"],
                         "confidence": raw["confidence"], "features": vector,
                         "net_r": outcome["net_r"], "net_cash": outcome["net_cash"],
                         "entry_bar": i+1, "exit_bar": outcome["exit_bar"],
                         "initial_risk_cash": outcome["initial_risk_cash"]})
    return rows, dict(excluded)


def training_rows(rows):
    groups = {}
    for row in rows: groups.setdefault(row["at"], []).append(row)
    selected = []; until = None
    for at, group in sorted(groups.items()):
        if until is not None and stamp(at) < until: continue
        selected.extend(group); until = max(stamp(row["horizon_end"]) for row in group)
    return selected


def fit(rows, names):
    rows = training_rows(rows)
    dates = len({row["at"][:10] for row in rows})
    if len(rows) < METHOD["minimum_training_rows"] or dates < METHOD["minimum_training_dates"]:
        return {"state": "insufficient_training_evidence", "rows": len(rows), "dates": dates,
                "broker_eligible": False, "orders_sent": 0}
    x = np.asarray([row["features"] for row in rows], dtype=float)
    y = np.clip([row["net_r"] for row in rows], -METHOD["target_clip_r"], METHOD["target_clip_r"])
    counts = Counter(row["at"] for row in rows)
    weights = np.array([1 / counts[row["at"]] for row in rows])
    if x.shape[1] != len(names) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("invalid_training_matrix")
    penalty = np.eye(x.shape[1]) * METHOD["regularization"]; penalty[0, 0] = 0
    coefficients = np.linalg.solve(x.T @ (weights[:, None] * x) + penalty, x.T @ (weights * y))
    return {"state": "fitted_research_only", "rows": len(rows), "dates": dates,
            "feature_names": names, "coefficients": coefficients.tolist(),
            "training_groups": len(counts), "last_label_resolved_by": max(row["horizon_end"] for row in rows),
            "broker_eligible": False, "orders_sent": 0}


def predict(model, vector):
    if model["state"] != "fitted_research_only": raise ValueError("unfitted_model")
    values = np.asarray(vector, dtype=float); coefficients = np.asarray(model["coefficients"], dtype=float)
    if values.shape != coefficients.shape or not np.isfinite(values).all() or not np.isfinite(coefficients).all():
        raise ValueError("invalid_prediction_vector")
    return float(values @ coefficients)


def metrics(trades):
    total = peak = drawdown = 0.
    positive = negative = 0.
    for row in trades:
        value = row["net_r"]; total += value; peak = max(peak, total); drawdown = max(drawdown, peak-total)
        positive += max(0., value); negative += max(0., -value)
    return {"trades": len(trades), "dates": len({row["at"][:10] for row in trades}),
            "wins": sum(row["net_r"] > 0 for row in trades), "net_r": total,
            "net_cash": sum(row["net_cash"] for row in trades),
            "mean_net_r": total / len(trades) if trades else None,
            "profit_factor": positive / negative if negative else None,
            "max_drawdown_r": drawdown}


def compare(rows, model, *, daily_limit=6):
    """Matched candidate universe, separate one-position paper portfolios.

    This deliberately does not claim live gate parity or risk-policy simulation.
    The fixed minimum-volume labels are nominal research outcomes only.
    """
    groups = {}
    for row in rows: groups.setdefault(row["at"], []).append(row)
    result = {}
    for learned in (False, True):
        trades = []; busy = -1; counts = Counter(); abstentions = 0
        for at, group in sorted(groups.items()):
            if group[0]["entry_bar"] <= busy or counts[at[:10]] >= daily_limit: continue
            if learned:
                if model["state"] != "fitted_research_only": continue
                chosen = min(group, key=lambda row: (-predict(model, row["features"]), row["strategy"], row["side"]))
                score = predict(model, chosen["features"])
                if score < METHOD["prediction_threshold_r"]: abstentions += 1; continue
            else:
                chosen = min(group, key=lambda row: (-row["confidence"], row["strategy"], row["side"]))
                score = None
            trades.append({**chosen, "predicted_net_r": score}); busy = chosen["exit_bar"]; counts[at[:10]] += 1
        result["learner" if learned else "baseline"] = {**metrics(trades), "abstentions": abstentions, "trade_list": trades}
    return result


def review_passed(comparison):
    stats = comparison["learner"]; baseline = comparison["baseline"]
    return (stats["trades"] >= METHOD["minimum_review_trades"] and stats["dates"] >= METHOD["minimum_review_dates"]
            and (stats["mean_net_r"] or 0) > 0 and stats["net_r"] > baseline["net_r"]
            and stats["net_cash"] > baseline["net_cash"]
            and ((stats["profit_factor"] or 0) >= METHOD["minimum_profit_factor"] or stats["wins"] == stats["trades"])
            and stats["max_drawdown_r"] <= METHOD["maximum_drawdown_r"])
