"""Explicit closed-candle D1/H4/H1/M15 confluence for M5 entries."""
import math
import pandas as pd
from atlas_ai.data.timeframe_bias import bias_from_closes

TIMEFRAMES = ("D1", "H4", "H1", "M15")
MINUTES = {"D1":1440, "H4":240, "H1":60, "M15":15, "M5":5}
POLICY = "top_down_d1_h4_h1_m15_m5_v1"


def closed_bars(frame, timeframe, now, *, broker_timezone="UTC"):
    now=pd.Timestamp(now)
    if now.tzinfo is None:raise ValueError("aware_evaluation_time_required")
    if frame.empty or "time" not in frame:raise ValueError("missing_candles")
    times=pd.to_datetime(frame.time,utc=True)
    if times.duplicated().any() or not times.is_monotonic_increasing:
        raise ValueError("unordered_or_duplicate_candles")
    if timeframe=="D1":
        # Broker daily boundaries follow local calendar days across DST.
        ends=times.map(lambda at: (at.tz_convert(broker_timezone)+pd.DateOffset(days=1)).tz_convert("UTC"))
    else:ends=times+pd.Timedelta(minutes=MINUTES[timeframe])
    mask=ends<=now
    result=frame.loc[mask].copy()
    if len(result)<30:raise ValueError("insufficient_closed_candles")
    age=(now-ends.loc[mask].iloc[-1]).total_seconds()
    if age>MINUTES[timeframe]*120:raise ValueError("stale_closed_candles")
    closes=[float(v) for v in result.close.tail(30)]
    if any(not math.isfinite(v) or v<=0 for v in closes):raise ValueError("invalid_closed_prices")
    return result


def collect(feed, now, *, broker_timezone="UTC"):
    details={};evidence={}
    for tf in TIMEFRAMES:
        try:
            frame=closed_bars(feed.get_rates_for_timeframe(tf,bars=90),tf,now,broker_timezone=broker_timezone)
            bias=bias_from_closes(frame.close)
            recent=frame.tail(20)
            high=float(recent.high.max());low=float(recent.low.min())
            if not all(math.isfinite(v) and v>0 for v in [high,low]) or low>high:
                raise ValueError("invalid_liquidity_reference")
            details[tf]=bias
            evidence[tf]={"bias":bias,"last_closed_bar_utc":pd.to_datetime(frame.time.iloc[-1],utc=True).isoformat(),
                "closed_bars":len(frame),"recent_high":high,"recent_low":low,
                "basis":"10_vs_30_closed_close_average","status":"available"}
        except Exception as exc:
            details[tf]="unknown"
            evidence[tf]={"bias":"unknown","status":"unavailable","reason":str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
    sides=set(details.values())
    bias=next(iter(sides)) if len(sides)==1 and sides <= {"buy","sell"} else "mixed"
    return {"policy":POLICY,"enabled":True,"entry_timeframe":"M5","confirm_tf":"M15",
        "context_tfs":list(TIMEFRAMES),"details":details,"evidence":evidence,"bias":bias,
        "aligned":bias in {"buy","sell"},"closed_candles_only":True,"evaluated_at":pd.Timestamp(now).isoformat()}


def entry_gate(context, side):
    if side not in {"buy","sell"}:return {"passed":False,"reason":"no_directional_entry"}
    failed=[tf for tf in TIMEFRAMES if context.get("details",{}).get(tf)!=side]
    passed=(context.get("policy")==POLICY and context.get("entry_timeframe")=="M5"
            and context.get("closed_candles_only") is True and not failed)
    return {"passed":passed,"policy":POLICY,"side":side,"nonconfirming_timeframes":failed,
        "reason":"all_higher_timeframes_confirm" if passed else "higher_timeframe_confluence_required"}
