"""Future paper review must never price a fill before its forecast was recorded."""
import pandas as pd


def entry_index_after_recording(forecast,bar_times,registered_start):
    available,observed,start=[pd.Timestamp(v) for v in
                              (forecast['available_at'],forecast['observed_at'],registered_start)]
    if any(v.tzinfo is None for v in (available,observed,start)):
        raise ValueError('aware_forecast_timestamps_required')
    if available<start or not 0<=(observed-available).total_seconds()<=120:
        raise ValueError('forecast_not_timely_or_predates_registration')
    times=pd.DatetimeIndex(pd.to_datetime(list(bar_times),utc=True))
    if times.has_duplicates or not times.is_monotonic_increasing or any(t.floor('5min')!=t for t in times):
        raise ValueError('ordered_unique_M5_open_times_required')
    index=int(times.searchsorted(observed,side='right'))
    return index if index<len(times) else None
