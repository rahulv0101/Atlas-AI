from dataclasses import replace
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import MetaTrader5 as mt5
import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.data.broker_clock import broker_time_to_utc, normalize_rates, utc_query_time
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.system_health import build_freshness_runtime


BASE = Settings(hfm_login=1, hfm_password="test", hfm_server="Demo")
HFM = replace(BASE, mt5_server_timezone="Europe/Athens")


@pytest.mark.parametrize("wall,expected", [
    ("2026-11-05T07:24:00", "2026-11-05T05:24:00+00:00"),
    ("2026-07-05T07:24:00", "2026-07-05T04:24:00+00:00"),
    ("2026-03-29T02:59:00", "2026-03-29T00:59:00+00:00"),
    ("2026-03-29T04:00:00", "2026-03-29T01:00:00+00:00"),
    ("2026-10-25T02:59:00", "2026-10-24T23:59:00+00:00"),
    ("2026-10-25T04:00:00", "2026-10-25T02:00:00+00:00"),
])
def test_configured_broker_clock_handles_winter_summer_and_dst_edges(wall, expected):
    epoch = pd.Timestamp(wall, tz="UTC").timestamp()
    utc = broker_time_to_utc(epoch, HFM)
    assert utc.isoformat() == expected
    assert utc_query_time(utc, HFM).timestamp() == epoch


@pytest.mark.parametrize("wall", ["2026-10-25T03:30:00", "2026-03-29T03:30:00"])
def test_ambiguous_or_nonexistent_wall_time_is_never_guessed(wall):
    with pytest.raises(Exception, match="ambiguous|infer dst|exist"):
        broker_time_to_utc(pd.Timestamp(wall, tz="UTC").timestamp(), HFM)


def test_default_utc_contract_never_double_shifts_prices_or_timestamps():
    rows = [{"time": 1793863453, "close": 3000.25}]
    original = normalize_rates(rows, BASE)
    corrected = normalize_rates(rows, HFM)
    assert original["close"].equals(corrected["close"])
    assert (original.time.iloc[0] - corrected.time.iloc[0]).total_seconds() == 7200
    assert corrected.attrs["timestamp_basis"] == "UTC"
    assert broker_time_to_utc(rows[0]["time"], BASE).timestamp() == rows[0]["time"]


def test_range_query_and_returned_bars_use_same_clock_boundary(monkeypatch):
    feed = MarketDataFeed(HFM)
    monkeypatch.setattr(feed, "_ensure_initialized", lambda: None)
    start = datetime(2026, 11, 5, 5, 0, tzinfo=timezone.utc)
    rows = [{"time": int((start + timedelta(hours=2, minutes=i)).timestamp()), "close": 3000 + i} for i in range(3)]
    query = Mock(return_value=rows)
    monkeypatch.setattr(mt5, "copy_rates_range", query)
    result = feed.get_rates_range(start, start + timedelta(minutes=1))
    assert query.call_args.args[2] == start + timedelta(hours=2)
    assert len(result) == 2
    assert result.time.iloc[0] == pd.Timestamp(start).tz_localize(None)


def test_empty_historical_range_is_well_formed(monkeypatch):
    feed = MarketDataFeed(BASE)
    monkeypatch.setattr(feed, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(mt5, "copy_rates_range", lambda *args: [])
    assert feed.get_rates_range(datetime(2026, 1, 1), datetime(2026, 1, 2)).empty


def test_naive_market_times_are_utc_even_when_operator_is_in_south_africa():
    now = datetime(2026, 11, 5, 7, 24, tzinfo=timezone(timedelta(hours=2)))
    result = build_freshness_runtime({"updated_at": "2026-11-05T05:24:00+00:00", "market": {"recent_time": ["2026-11-05 05:23:00"]}}, SimpleNamespace(timeframe_minutes=1), now=now)
    assert result["market_data_age_ms"] == 60000
    assert result["state"] == "fresh"


def test_future_bars_and_stopped_backend_cannot_report_fresh():
    now = datetime(2026, 11, 5, 5, 24, tzinfo=timezone.utc)
    future = build_freshness_runtime({"updated_at": now.isoformat(), "market": {"recent_time": ["2026-11-05 07:23:00"]}}, BASE, now=now)
    assert future["clock_error"] and future["is_stale"]
    stopped = build_freshness_runtime({"updated_at": "2026-11-04T05:24:00Z", "market": {"recent_time": ["2026-11-04 05:23:00"]}}, BASE, now=now)
    assert stopped["is_status_stale"] and stopped["is_stale"]
