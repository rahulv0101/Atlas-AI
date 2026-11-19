import pandas as pd
from tools.settled_m5_collector import forecast_window


def frame():
    return pd.DataFrame({'time':pd.date_range('2026-11-19T06:40Z',periods=5,freq='5min'),'close':100.})


def test_latest_closed_bar_is_not_committed_before_settling_delay():
    f=frame();settled,window=forecast_window(f,pd.Timestamp('2026-11-19T07:00:30Z'))
    assert settled.time.iloc[-1]==pd.Timestamp('2026-11-19T06:50Z')
    assert not window['timely']


def test_forecast_is_timely_after_settlement_and_scheduled_entry_is_in_future():
    now=pd.Timestamp('2026-11-19T07:01:10Z');settled,window=forecast_window(frame(),now)
    assert settled.time.iloc[-1]==pd.Timestamp('2026-11-19T06:55Z')
    assert window['timely'] and window['lag_seconds']==70
    assert now.ceil('5min')>now


def test_late_forecasts_are_not_backfilled_and_naive_utc_is_supported():
    f=frame();f['time']=f.time.dt.tz_localize(None)
    _,window=forecast_window(f,pd.Timestamp('2026-11-19T07:03Z'))
    assert not window['timely']
