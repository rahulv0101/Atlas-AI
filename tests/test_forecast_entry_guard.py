import pandas as pd
import pytest
from tools.forecast_entry_guard import entry_index_after_recording


def test_recording_after_confirmation_cannot_take_past_open():
    times=pd.date_range('2026-11-26T10:00Z',periods=3,freq='5min')
    forecast={'available_at':times[0].isoformat(),'observed_at':(times[0]+pd.Timedelta(seconds=30)).isoformat()}
    assert entry_index_after_recording(forecast,times,times[0])==1
    assert entry_index_after_recording(forecast,times[:1],times[0]) is None


def test_late_or_retrospective_forecast_is_not_executable_evidence():
    times=pd.date_range('2026-11-26T10:00Z',periods=3,freq='5min')
    forecast={'available_at':times[0].isoformat(),'observed_at':(times[0]+pd.Timedelta(seconds=121)).isoformat()}
    with pytest.raises(ValueError):entry_index_after_recording(forecast,times,times[0])
    forecast['observed_at']=(times[0]+pd.Timedelta(seconds=30)).isoformat()
    with pytest.raises(ValueError):entry_index_after_recording(forecast,times,times[1])
