"""Broker-unit, bid/ask historical fills. No terminal or execution dependency."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BrokerSpec:
    point: float
    tick_size: float
    tick_value_profit: float
    tick_value_loss: float
    volume_min: float
    volume_max: float
    volume_step: float
    digits: int
    trade_stops_level: int = 0
    trade_freeze_level: int = 0
    margin_per_lot: float = 0.
    roundtrip_fee_per_lot: float = 0.

    def __post_init__(self):
        positive=(self.point,self.tick_size,self.tick_value_profit,self.tick_value_loss,
            self.volume_min,self.volume_max,self.volume_step)
        if not all(math.isfinite(x) and x>0 for x in positive):raise ValueError("invalid_broker_units")
        if self.volume_max<self.volume_min:raise ValueError("invalid_volume_range")
        if not all(math.isfinite(x) and x>=0 for x in (self.margin_per_lot,self.roundtrip_fee_per_lot)):
            raise ValueError("invalid_broker_costs")

    def cash(self,move,volume):
        value=self.tick_value_profit if move>=0 else self.tick_value_loss
        return move/self.tick_size*value*volume


@dataclass(frozen=True)
class ExitVariant:
    name: str
    lock_r: float
    slippage_points_per_side: float
    cost_aware_lock: bool = False


def simulate(frame,entry_index,signal,volume,spec,settings,variant,*,last_index=None):
    """Ask entry/bid exit for buys; bid entry/ask exit for sells; stop first.

    Spread is embedded exactly once in quote-side prices. Slippage applies on
    both legs; commission/fees are separate cash charges. Conversion/margin
    specifications are frozen current estimates, not historical reconstructions.
    """
    if signal.side not in {"buy","sell"}:raise ValueError("direction_required")
    if not math.isfinite(volume) or volume<spec.volume_min or volume>spec.volume_max:
        raise ValueError("invalid_volume")
    sign=1 if signal.side=="buy" else -1
    slip=variant.slippage_points_per_side*spec.point
    if not math.isfinite(slip) or slip<0:raise ValueError("invalid_slippage")
    first=frame.iloc[entry_index];spread=float(first.spread)*spec.point
    entry=round(float(first.open)+(spread if sign==1 else 0)+sign*slip,spec.digits)
    minimum=max(spec.trade_stops_level,spec.trade_freeze_level)+max(2,round(float(first.spread)*.35))
    stop_points=max(float(signal.stop_loss_points),minimum)
    target_points=max(float(signal.take_profit_points),minimum)
    if not all(math.isfinite(x) and x>0 for x in (stop_points,target_points)):raise ValueError("invalid_protection")
    distance=stop_points*spec.point
    stop=round(entry-sign*distance,spec.digits);target=round(entry+sign*target_points*spec.point,spec.digits)
    initial_risk=abs(spec.cash(-distance,volume))
    fees=spec.roundtrip_fee_per_lot*volume
    lock=float(variant.lock_r)
    if variant.cost_aware_lock:
        # Research-only fee/slippage break-even, plus the declared positive lock.
        lock+=(fees+abs(spec.cash(-2*slip,volume)))/initial_risk
    last=min(len(frame)-1,entry_index+settings.backtest_max_hold_bars-1)
    if last_index is not None:last=min(last,int(last_index))
    if last<entry_index:raise ValueError("empty_execution_window")
    best=0.;exit_price=None;reason="max_hold";ambiguous=False
    for j in range(entry_index,last+1):
        row=frame.iloc[j]
        if j>entry_index:
            if best>=settings.backtest_break_even_r_trigger:
                locked=entry+sign*lock*distance
                stop=max(stop,locked) if sign==1 else min(stop,locked)
            if best>=settings.backtest_trailing_r_trigger:
                locked=entry+sign*max(lock,best-settings.backtest_trailing_buffer_r)*distance
                stop=max(stop,locked) if sign==1 else min(stop,locked)
        offset=0 if sign==1 else float(row.spread)*spec.point
        opening=float(row.open)+offset;high=float(row.high)+offset;low=float(row.low)+offset;close=float(row.close)+offset
        hit_stop=low<=stop if sign==1 else high>=stop
        hit_target=high>=target if sign==1 else low<=target
        if hit_stop:
            # A gap through a stop fills at the worse available quote.
            exit_price=min(stop,opening) if sign==1 else max(stop,opening)
            reason="stop_loss";ambiguous=bool(hit_target);break
        if hit_target:exit_price=target;reason="take_profit";break
        best=max(best,max(0.,(high-entry if sign==1 else entry-low)/distance))
        if j-entry_index+1>=settings.backtest_stale_exit_bars and best<settings.backtest_stale_min_progress_r:
            exit_price=close;reason="stale_exit";break
        if j==last:
            exit_price=close;reason="session_or_window_close" if last_index is not None and last_index<=last else "max_hold";break
    exit_price-=sign*slip
    gross=spec.cash(sign*(exit_price-entry),volume)
    return {"entry_bar":entry_index,"exit_bar":j,"entry_price":entry,"exit_price":exit_price,
        "volume":volume,"initial_risk_cash":initial_risk,"gross_cash_after_spread_slippage":gross,
        "fees_cash":fees,"net_cash":gross-fees,"net_r":(gross-fees)/initial_risk,
        "exit_reason":reason,"ambiguous_stop_first":ambiguous,"effective_lock_r":lock,
        "spread_charged_in_quotes":True,"protection_observed":False,"broker_fill":False}
