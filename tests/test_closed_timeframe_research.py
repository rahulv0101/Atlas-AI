from dataclasses import replace
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.models import TradeSignal
from tools.closed_timeframe_research import closed_bars,signal_cache,evaluate,LOOKBACK,clock_settings


def frame(size=900):
    return pd.DataFrame({"time":pd.date_range("2026-11-09T08:00",periods=size,freq="min"),
        "open":2000.,"high":2001.,"low":1999.,"close":2000.,"tick_volume":100.,"spread":20.})


def rules():
    return {"point":.01,"slippage_bps":1.5,"fee_points":0.,"max_spread_points":80,
        "max_trades_day":6,"max_losses":2,"daily_loss_r":1.2}


def cached(at="2026-11-09T10:00:00Z"):
    return {"bar_utc":(pd.Timestamp(at)-pd.Timedelta(minutes=5)).isoformat(),"available_at":at,
        "timeframe_minutes":5,"signal":{"strategy":"test","side":"buy","confidence":.8,
            "stop_loss_points":1000.,"take_profit_points":1500.}}


def test_partial_and_missing_minute_groups_cannot_become_closed_chart_bars():
    coarse=closed_bars(frame(9),5)
    assert len(coarse)==1 and coarse.time.iloc[0]==pd.Timestamp("2026-11-09T08:00")
    broken=frame(10).drop(index=3)
    coarse=closed_bars(broken,5)
    assert len(coarse)==1 and coarse.time.iloc[0]==pd.Timestamp("2026-11-09T08:05")


@pytest.mark.parametrize("minutes",[5,15])
def test_signal_generation_is_past_only_with_a_fixed_closed_bar_lookback(minutes):
    seen=[]
    def generate(window):
        seen.append((len(window),window.time.iloc[-1]))
        return TradeSignal("fake","buy",.5,100,150)
    strategy=NS(generate_signal=generate,sl_atr_multiple=2.,tp_atr_multiple=3.,sl_floor_points=100.,tp_floor_points=150.)
    f=frame(2200);first=signal_cache(f,minutes,strategy,.01)
    assert first and all(n==LOOKBACK for n,_ in seen)
    assert all(pd.Timestamp(row["available_at"])==pd.Timestamp(row["bar_utc"])+pd.Timedelta(minutes=minutes) for row in first)
    changed=f.copy();changed.loc[len(changed)-minutes:,["open","high","low","close"]]+=50
    other=signal_cache(changed,minutes,strategy,.01)
    cutoff=pd.Timestamp(f.time.iloc[-minutes]).tz_localize("UTC")
    assert [r for r in first if pd.Timestamp(r["available_at"])<=cutoff]==[r for r in other if pd.Timestamp(r["available_at"])<=cutoff]


def test_entries_use_m1_after_chart_close_and_charge_costs_without_forcing_daily_trades():
    f=frame(300)
    s=Settings(1,"test","Demo",backtest_stale_exit_bars=4)
    cache=[cached(f"2026-11-09T10:{minute:02}:00Z") for minute in (0,5,10)]
    rows=evaluate(f,cache,"2026-11-09T09:00Z","2026-11-09T12:00Z",s,rules())
    assert len(rows)==2  # existing research consecutive-loss stop
    assert all(r["entry_at"]==r["signal_available_at"] for r in rows)
    assert rows[0]["entry_at"]=="2026-11-09T10:00:00+00:00"
    assert all(r["net_r"]==pytest.approx(-.05) for r in rows)


def test_malformed_availability_clock_cannot_admit_future_chart_information():
    c=cached();c["bar_utc"]=c["available_at"]
    with pytest.raises(ValueError,match="availability_clock"):
        evaluate(frame(),[c],"2026-11-09T09:00Z","2026-11-09T12:00Z",Settings(1,"test","Demo"),rules())


def test_missing_fill_path_or_incomplete_phase_horizon_cannot_count_as_a_trade():
    s=Settings(1,"test","Demo");f=frame(300).drop(index=130).reset_index(drop=True)
    assert not evaluate(f,[cached()],"2026-11-09T09:00Z","2026-11-09T12:00Z",s,rules())
    assert not evaluate(frame(),[cached()],"2026-11-09T09:00Z","2026-11-09T10:30Z",s,rules())


def test_recorded_spread_limit_is_not_relaxed_for_slower_timeframes():
    f=frame();f.loc[120,"spread"]=81
    assert not evaluate(f,[cached()],"2026-11-09T09:00Z","2026-11-09T12:00Z",Settings(1,"test","Demo"),rules())


@pytest.mark.parametrize("minutes,exit_minute",[(5,19),(15,59)])
def test_four_strategy_bars_preserve_elapsed_time_on_m1_fill_paths(minutes,exit_minute):
    s=Settings(1,"test","Demo",backtest_stale_exit_bars=4)
    baseline=evaluate(frame(),[cached()],"2026-11-09T09:00Z","2026-11-09T12:00Z",clock_settings(s,minutes,"m1"),rules())
    native=evaluate(frame(),[cached()],"2026-11-09T09:00Z","2026-11-09T12:00Z",clock_settings(s,minutes,"strategy"),rules())
    assert baseline[0]["exit_at"]=="2026-11-09T10:03:00+00:00"
    assert native[0]["exit_at"]==f"2026-11-09T10:{exit_minute:02}:00+00:00"
    assert s.backtest_stale_exit_bars==4
