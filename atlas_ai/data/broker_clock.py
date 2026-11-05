"""Explicit MT5 clock boundary. Strategy frames continue to contain naive UTC.

MT5 documents UTC epochs. Some servers instead expose server wall time encoded
as an epoch. That exception must be configured; never infer it from stale ticks.
"""
from datetime import datetime, timezone

import pandas as pd


def server_timezone(settings) -> str:
    return str(getattr(settings, "mt5_server_timezone", "") or "UTC")


def broker_time_to_utc(value: int | float, settings) -> datetime:
    wall = pd.Timestamp(float(value), unit="s")
    # Ambiguous/nonexistent DST wall times must fail rather than guess a trade's hour.
    return wall.tz_localize(server_timezone(settings), ambiguous="raise", nonexistent="raise").tz_convert("UTC").to_pydatetime()


def utc_query_time(value: datetime, settings) -> datetime:
    # Historical callers have always used naive UTC. Do not let Windows local
    # timezone reinterpret those inputs during timestamp conversion.
    utc = pd.Timestamp(value)
    utc = utc.tz_localize("UTC") if utc.tzinfo is None else utc.tz_convert("UTC")
    wall = utc.tz_convert(server_timezone(settings)).tz_localize(None)
    return wall.to_pydatetime().replace(tzinfo=timezone.utc)


def normalize_rates(rates, settings) -> pd.DataFrame:
    frame = pd.DataFrame(rates)
    if frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
    frame["time"] = (
        pd.to_datetime(frame["time"], unit="s")
        .dt.tz_localize(server_timezone(settings), ambiguous="raise", nonexistent="raise")
        .dt.tz_convert("UTC").dt.tz_localize(None)
    )
    frame.attrs["timestamp_basis"] = "UTC"
    frame.attrs["broker_timezone"] = server_timezone(settings)
    return frame
