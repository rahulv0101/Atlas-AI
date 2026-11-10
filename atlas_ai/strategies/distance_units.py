"""Explicit ATR-price to broker-point conversion for reviewed research variants.

This adapter does not register or activate strategies in the live trader.
"""
from dataclasses import replace
import math


ATR_DISTANCE_RULES = {
    "ema_crossover": (2., 3., 100., 150.),
    "pullback_trend": (1.8, 2.6, 110., 170.),
    "momentum_continuation": (1.9, 2.8, 115., 175.),
    "gold_micro_impulse": (1.25, 1.9, 85., 120.),
    "gold_breakout_retest": (1.45, 2.15, 100., 145.),
    "gold_liquidity_sweep": (1.3, 2., 90., 125.),
    "evolved_rule": (1.9, 2.8, 100., 160.),
}


def atr_distance_points(atr_price, multiplier, point_size, floor_points):
    values = tuple(float(v) for v in (atr_price, multiplier, point_size, floor_points))
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("positive_finite_atr_multiplier_point_and_floor_required")
    a, m, p, floor = values
    return max(a * m / p, floor)


def corrected_atr_signal(signal, atr_price, point_size):
    key = signal.strategy.split("(", 1)[0]
    sl, tp, sl_floor, tp_floor = ATR_DISTANCE_RULES[key]
    return replace(signal,
        stop_loss_points=atr_distance_points(atr_price, sl, point_size, sl_floor),
        take_profit_points=atr_distance_points(atr_price, tp, point_size, tp_floor))


def distance_unit_review(signal, atr_price, point_size):
    """Observe the active distances without changing them or approving an entry."""
    try:
        expected = corrected_atr_signal(signal, atr_price, point_size)
        actual_sl, actual_tp = float(signal.stop_loss_points), float(signal.take_profit_points)
        if not all(math.isfinite(v) and v > 0 for v in (actual_sl, actual_tp)):
            raise ValueError("invalid_actual_distances")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return {"available": False, "reason": type(exc).__name__, "advisory_only": True}
    match = math.isclose(actual_sl, expected.stop_loss_points, rel_tol=1e-9) and math.isclose(actual_tp, expected.take_profit_points, rel_tol=1e-9)
    return {"available": True, "advisory_only": True, "strategy": signal.strategy,
        "atr_price": float(atr_price), "point_size": float(point_size),
        "candidate_stop_points": actual_sl, "candidate_target_points": actual_tp,
        "reviewed_atr_stop_points": expected.stop_loss_points,
        "reviewed_atr_target_points": expected.take_profit_points,
        "matches_reviewed_atr_units": match,
        "activation_state": "current_distances_match" if match else "correction_in_research_only",
        "policy_note": "Candidate distances before broker stop adjustment. This comparison cannot resize orders, alter limits or activate a strategy."}
