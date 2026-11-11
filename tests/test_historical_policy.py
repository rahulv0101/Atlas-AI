from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.inventory import base_inventory
from atlas_ai.backtest import Backtester
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant,simulate
from atlas_ai.testing.policy_replay import higher_timeframe_bias,replay
from atlas_ai.testing import historical_decision as decision_module
from atlas_ai.trader import AtlasTrader


def settings(**kw):return replace(Settings(1,"test","Demo",timeframe="M1"),**kw)


def spec(**kw):
    return replace(BrokerSpec(.01,.01,1.,1.,.01,10.,.01,2),**kw)


def bars(n=3):
    return pd.DataFrame({"time":pd.date_range("2026-11-09T08:00Z",periods=n,freq="min").tz_localize(None),
        "open":100.,"high":100.,"low":100.,"close":100.,"spread":20.,"tick_volume":100.})


def test_shared_inventory_preserves_runtime_order_and_covers_six_enabled_strategies():
    names=[s.name for s in base_inventory("M1")]
    assert names==["ema_crossover","rsi_mean_reversion","breakout","candlestick_patterns","macd_trend",
        "bollinger_mean_reversion","stochastic_reversal","vwap_proxy_reversion","momentum_continuation",
        "pullback_trend","rsi_trend_hybrid","gold_micro_impulse","gold_breakout_retest","gold_liquidity_sweep",
        "gold_micro_structure_reversion"]
    engine=Backtester(settings=settings())
    assert {s.name for s in engine.base}>={"ema_crossover","pullback_trend","momentum_continuation",
        "gold_micro_impulse","gold_breakout_retest","gold_liquidity_sweep"}
    assert len(base_inventory("M15",paper_variants=True))==13
    assert len(base_inventory("M15",paper_variants=False))==11


@pytest.mark.parametrize("side",["buy","sell"])
def test_bid_ask_spread_charged_once_with_volume_tick_and_fee_units(side):
    data=bars();signal=TradeSignal("ema_crossover",side,.8,100,150)
    model=spec(roundtrip_fee_per_lot=2)
    result=simulate(data,0,signal,.01,model,settings(backtest_max_hold_bars=1),ExitVariant("test",.05,3))
    assert result["net_cash"]==pytest.approx(-.28)
    assert result["fees_cash"]==pytest.approx(.02)
    assert result["initial_risk_cash"]==pytest.approx(1)
    assert not result["broker_fill"] and not result["protection_observed"]


def test_profit_and_loss_tick_value_conversion_are_distinct():
    model=spec(tick_size=.1,tick_value_profit=2,tick_value_loss=3)
    assert model.cash(1,.1)==pytest.approx(2)
    assert model.cash(-1,.1)==pytest.approx(-3)
    with pytest.raises(ValueError):spec(tick_value_loss=0)


def test_stop_first_and_gap_stops_are_conservative():
    data=bars();data["spread"]=0.;data.loc[0,["high","low","close"]]=[102,98,101]
    signal=TradeSignal("ema_crossover","buy",.8,100,150)
    result=simulate(data,0,signal,.01,spec(),settings(),ExitVariant("current",.05,0))
    assert result["net_cash"]==pytest.approx(-1) and result["ambiguous_stop_first"]
    data=bars();data["spread"]=0.;data.loc[1,["open","high","low","close"]]=[98,98.5,97,98]
    result=simulate(data,0,signal,.01,spec(),settings(),ExitVariant("current",.05,0))
    assert result["exit_price"]==98 and result["net_cash"]==pytest.approx(-2)


def test_current_bar_high_cannot_move_stop_before_that_bar_closes():
    data=bars();data["spread"]=0.;data.loc[0,["high","low","close"]]=[102,99.5,101]
    data.loc[1,["open","high","low","close"]]=[101,101.5,100.5,101]
    result=simulate(data,0,TradeSignal("ema_crossover","buy",.8,100,1000),.01,spec(),settings(),ExitVariant("current",.05,0))
    assert result["exit_bar"]==1 and result["net_cash"]>0


def test_higher_timeframe_uses_only_complete_closed_groups():
    data=bars(151);data["close"]=[100+i*.1 for i in range(len(data))]
    before=higher_timeframe_bias(data,5)
    assert before[148]=="unknown" and before[149]=="buy"
    data.loc[150,"close"]=1
    assert higher_timeframe_bias(data,5)==before


def fixture_replay(tmp_path,monkeypatch,**settings_kw):
    data=bars(300);data["spread"]=0.;data["high"]=100.2;data["low"]=98.9
    cfg=settings(backtest_initial_balance=10000,min_same_side_signals=1,**settings_kw)
    monkeypatch.setattr(AtlasTrader,"_timing_discipline_snapshot",lambda *args,**kw:{"passed":True})
    monkeypatch.setattr(decision_module,"build_structured_decision_analysis",lambda **kw:{"confidence_score":99})
    cache=[{"index":i,"available_at":(pd.Timestamp(data.time.iloc[i],tz="UTC")+pd.Timedelta(minutes=1)).isoformat(),
        "signals":[{"strategy":"ema_crossover","side":"buy","confidence":.99,"stop_loss_points":100,"take_profit_points":150}],
        "regime":{"name":"trend","trend_strength":.3,"volatility_pct":.05},"higher_tf_bias":"buy"} for i in (250,260)]
    limits={"day_trades":1,"loss_streak":2,"daily_loss_percent":.6,"lot_cap":.01,"setup_family":"continuation"}
    return data,cache,cfg,KnowledgeStore(str(tmp_path)),limits


def test_real_risk_session_and_size_adapters_enforce_daily_trade_cap(tmp_path,monkeypatch):
    data,cache,cfg,store,limits=fixture_replay(tmp_path,monkeypatch)
    result=replay(data,cache,cfg,spec(),ExitVariant("current",.05,0),store,limits)
    assert result["trades"]==1
    assert result["trade_list"][0]["volume"]==.01
    assert result["trade_list"][0]["entry_at"].endswith("+00:00")
    assert result["trade_list"][0]["exit_at"].endswith("+00:00")
    assert result["rejections"]["max_trades_per_day_reached"]==1
    assert not result["broker_eligible"] and result["orders_sent"]==0


def test_strict_replay_cannot_invent_historical_visual_evidence(tmp_path,monkeypatch):
    data,cache,cfg,store,limits=fixture_replay(tmp_path,monkeypatch)
    result=replay(data,cache,cfg,spec(),ExitVariant("current",.05,0),store,limits,strict=True)
    assert result["trades"]==0
    assert result["rejections"]["historical_visual_macro_and_execution_evidence_unavailable"]==2


def test_higher_timeframe_opposition_and_broker_minimum_fail_closed(tmp_path,monkeypatch):
    data,cache,cfg,store,limits=fixture_replay(tmp_path,monkeypatch)
    cache[0]["higher_tf_bias"]="sell"
    result=replay(data,cache[:1],cfg,spec(),ExitVariant("current",.05,0),store,limits)
    assert result["rejections"]["higher_timeframe_alignment"]==1
    result=replay(data,cache[1:],cfg,spec(volume_min=.02),ExitVariant("current",.05,0),store,limits)
    assert result["trades"]==0 and result["rejections"]["no_risk_bounded_volume"]==1


def test_replay_uses_atlas_conviction_not_raw_signal_confidence(tmp_path,monkeypatch):
    data,cache,cfg,store,limits=fixture_replay(tmp_path,monkeypatch)
    monkeypatch.setattr(decision_module,"build_structured_decision_analysis",lambda **kw:{"confidence_score":20})
    result=replay(data,cache,cfg,spec(),ExitVariant("current",.05,0),store,limits)
    assert result["trades"]==0 and result["rejections"]["atlas_conviction_threshold"]==2


def test_active_profile_caps_the_adaptive_threshold_as_runtime_does(tmp_path,monkeypatch):
    data,cache,cfg,store,limits=fixture_replay(tmp_path,monkeypatch,learning_mode=True,confidence_threshold_learning=.44)
    result=replay(data,cache,cfg,spec(),ExitVariant("current",.05,0),store,limits)
    assert result["trade_list"][0]["confidence"]==.99
    assert result["trade_list"][0]["confidence_threshold"]==.44
    assert result["trade_list"][0]["signal_confidence_seed"]==.99
