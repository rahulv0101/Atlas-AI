from __future__ import annotations

from dataclasses import dataclass
import math

from atlas_ai.config.settings import Settings, get_active_thresholds
from atlas_ai.risk.volume import floor_volume


@dataclass
class RiskSnapshot:
    equity: float
    balance: float
    daily_loss_pct: float
    open_positions: int
    spread_points: float = 0.0
    weekly_loss_pct: float = 0.0
    consecutive_losses: int = 0


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def can_trade(self, snapshot: RiskSnapshot) -> bool:
        allowed, _ = self.evaluate(snapshot)
        return allowed

    def evaluate(self, snapshot: RiskSnapshot) -> tuple[bool, str]:
        for field in ("equity", "balance", "daily_loss_pct", "weekly_loss_pct", "open_positions", "spread_points"):
            try:
                valid = math.isfinite(float(getattr(snapshot, field)))
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                return False, f"Invalid risk data: {field}"
        if snapshot.equity <= 0 or snapshot.balance <= 0:
            return False, "Account equity and balance must be positive"
        if snapshot.open_positions < 0 or snapshot.spread_points < 0:
            return False, "Invalid negative position count or spread"
        if snapshot.daily_loss_pct >= self.settings.max_daily_drawdown:
            return False, "Daily drawdown limit reached"
        if snapshot.weekly_loss_pct >= getattr(self.settings, "max_weekly_drawdown", 1.0):
            return False, "Weekly drawdown limit reached"
        if snapshot.open_positions >= self.settings.max_open_trades:
            return False, "Max open trades reached"
        if snapshot.spread_points > 0 and snapshot.spread_points > self.settings.max_spread_points:
            return False, f"Spread too high ({snapshot.spread_points:.1f} pts)"
        return True, ""

    def lot_size(self, equity: float, stop_loss_points: float, tick_value: float, *,
                 point_size: float = 1.0, tick_size: float = 1.0,
                 volume_step: float = 0.01, minimum_volume: float | None = None) -> float:
        try:
            values = (equity, stop_loss_points, tick_value, point_size, tick_size,
                      volume_step, self.settings.max_risk_per_trade, self.settings.base_lot)
            if not all(math.isfinite(float(v)) and float(v) > 0 for v in values):
                return 0.0
            if float(self.settings.max_risk_per_trade) > 1:
                return 0.0
            if minimum_volume is not None and (not math.isfinite(float(minimum_volume)) or float(minimum_volume) <= 0):
                return 0.0
            minimum = float(self.settings.base_lot) if minimum_volume is None else float(minimum_volume)
            if not math.isfinite(minimum):
                return 0.0
            loss_per_lot = stop_loss_points * (point_size / tick_size) * tick_value
            budget = equity * self.settings.max_risk_per_trade
            if not math.isfinite(loss_per_lot) or loss_per_lot <= 0:
                return 0.0
            raw = budget / loss_per_lot
            if bool(getattr(self.settings, "learning_mode", False)):
                fixed = float(get_active_thresholds(self.settings)["max_lot"])
                if not math.isfinite(fixed) or fixed <= 0 or fixed > raw:
                    return 0.0
                raw = fixed
            volume = floor_volume(raw, volume_step)
            return volume if volume >= minimum else 0.0
        except (TypeError, ValueError, OverflowError, ZeroDivisionError):
            return 0.0
