"""Round order quantities down without exceeding a supplied limit."""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def floor_volume(volume, step, maximum=None):
    try:
        value, increment = Decimal(str(volume)), Decimal(str(step))
        if not value.is_finite() or not increment.is_finite() or value <= 0 or increment <= 0:
            return 0.0
        if maximum is not None:
            cap = Decimal(str(maximum))
            if not cap.is_finite() or cap <= 0:
                return 0.0
            value = min(value, cap)
        return float((value / increment).to_integral_value(rounding=ROUND_FLOOR) * increment)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return 0.0
