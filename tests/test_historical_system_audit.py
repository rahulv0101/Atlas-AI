from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from tools import historical_system_audit as module


def frame(start,n=1005):
    return pd.DataFrame({"time":pd.date_range(start,periods=n,freq="min"),"open":2000.,"high":2001.,
        "low":1999.,"close":2000.,"spread":30.,"tick_volume":100.})


def test_history_must_have_sufficient_closed_bars_within_requested_window():
    start=datetime(2026,11,1,tzinfo=timezone.utc);end=start+timedelta(days=1)
    assert module.data_summary(frame(start),start,end)["bars"]==1005
    with pytest.raises(ValueError,match="insufficient_history"):module.data_summary(frame(start,10),start,end)
    with pytest.raises(ValueError,match="outside_closed"):module.data_summary(frame(start),start,start+timedelta(hours=1))


def setup(monkeypatch,start):
    settings=Settings(123,"must-not-appear-in-report","Demo")
    monkeypatch.setattr(module,"load_settings",lambda:settings)
    monkeypatch.setattr(module,"attach",Mock())
    monkeypatch.setattr(module.mt5,"shutdown",Mock())
    feed=Mock();feed.get_rates_range.return_value=frame(start)
    monkeypatch.setattr(module,"MarketDataFeed",lambda *args:feed)
    monkeypatch.setattr(module,"prepare_frame",lambda raw:raw)
    return settings


def test_offline_audit_isolates_storage_settings_and_never_dispatches(monkeypatch,tmp_path):
    start=datetime(2026,11,1,tzinfo=timezone.utc);settings=setup(monkeypatch,start)
    class Engine:
        base=[SimpleNamespace(name="ema_crossover")]
        def __init__(self,settings):
            assert settings.execute_trades is False and settings.backtest_persist_learning_state is False
            assert settings.storage_dir!=module.load_settings().storage_dir
            assert settings.gemini_api_key==settings.openai_api_key==""
        def _strategy_enabled(self,name):return True
        def _simulate_trade(self,*args):return 0,0,0
        def run(self,data):
            with pytest.raises(AssertionError,match="cannot_dispatch"):module.mt5.order_send({})
            from atlas_ai.backtest import BacktestResult
            return BacktestResult(0,0,0,0)
    monkeypatch.setattr(module,"Backtester",Engine)
    def timing(*args,**kwargs):
        path=module.matched.BASELINE_DIR/"timing.json";path.write_text('{"test":true}')
        assert module.matched.load_settings().execute_trades is False
        from atlas_ai.market_context import _fresh_external_context_fields
        assert _fresh_external_context_fields()=={}
        return path
    monkeypatch.setattr(module.matched,"run_matched_backtest",timing)
    destination=tmp_path/"run"
    result=module.run(destination,start,start+timedelta(days=1))
    assert result["state"]=="completed_research_only" and result["orders_sent"]==0
    assert not result["live_system_parity"] and not result["broker_eligible"]
    assert "must-not-appear-in-report" not in (destination/"report.json").read_text()
    assert len(result["data"]["sha256"])==64 and settings is module.load_settings()
    assert (destination/"executed_runner.py").exists()
    with pytest.raises(FileExistsError):module.run(destination,start,start+timedelta(days=1))


def test_failed_audit_publishes_failure_without_success_claim(monkeypatch,tmp_path):
    start=datetime(2026,11,1,tzinfo=timezone.utc);setup(monkeypatch,start)
    monkeypatch.setattr(module,"attach",Mock(side_effect=ValueError("wrong_demo_account")))
    with pytest.raises(ValueError,match="wrong_demo_account"):module.run(tmp_path/"failed",start,start+timedelta(days=1))
    result=json.loads((tmp_path/"failed/report.json").read_text())
    assert result["state"]=="failed" and result["orders_sent"]==0


def test_cost_and_stop_first_sensitivity_does_not_hide_ambiguous_losses_or_overlap():
    settings=Settings(123,"test","Demo",backtest_point_size=.01,max_risk_per_trade=.005,
        backtest_spread_cost_bps=3,backtest_slippage_cost_bps=1.5)
    start=datetime(2026,11,1,tzinfo=timezone.utc);data=frame(start,3)
    data["high"]=2002.;data["low"]=1998.;data["close"]=2001.
    row={"strategy":"ema_crossover","side":"buy","confidence":.8,"stop_loss_points":100.,
        "take_profit_points":150.,"signal_bar":0,"entry_bar":1,"r_multiple":1.5}
    result=module.timing_sensitivity(data,[row,row],settings)
    assert result["candle_direction_reproduction_mismatches"]==[]
    assert result["fixed_model_cost_r"]==pytest.approx(.09)
    assert result["variants"]["recorded_fixed_costs"]["mean_r"]==pytest.approx(1.41)
    assert result["variants"]["stop_first_fixed_costs"]["mean_r"]==pytest.approx(-1.09)
    assert result["variants"]["nonoverlap_stop_first_fixed_costs"]["trades"]==1
    assert result["overlapping_rows_excluded_in_conservative_greedy_subsample"]==1
