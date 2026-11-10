from dataclasses import replace
import json

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.models import TradeSignal
from tools import cost_aware_strategy_audit as audit


def frame(size=1500):
    return pd.DataFrame({"time":pd.date_range("2026-11-02",periods=size,freq="min"),
        "open":100.,"high":100.1,"low":99.9,"close":100.,"spread":10.,"tick_volume":100})


@pytest.mark.parametrize("name",list(audit.DISTANCES))
def test_atr_research_correction_preserves_price_units_and_existing_floor(name):
    signal=TradeSignal(name,"buy",.8,100,150)
    a=audit.corrected(signal,10.,.01)
    b=audit.corrected(signal,10.,.1)
    assert a.stop_loss_points*.01 == pytest.approx(b.stop_loss_points*.1)
    assert a.take_profit_points*.01 == pytest.approx(b.take_profit_points*.1)
    assert a.stop_loss_points >= audit.DISTANCES[name][2]
    assert signal.stop_loss_points == 100  # baseline is not mutated


def test_retest_cannot_confirm_from_a_later_bar_or_across_a_gap():
    f=frame(8);f["atr_price"]=1.
    f.loc[2,["open","low","high","close"]]=[99.9,99.8,100.3,100.2]
    assert audit.confirmation(f.iloc[:2],0,"buy") is None
    assert audit.confirmation(f,0,"buy") == 2
    f.loc[1:,"time"] += pd.Timedelta(hours=1)
    assert audit.confirmation(f,0,"buy") is None


def test_nonpositive_atr_is_rejected():
    with pytest.raises(ValueError):audit.corrected(TradeSignal("ema_crossover","buy",.8,100,150),0,.01)


def test_prospective_signal_cache_never_generates_pre_freeze_signals(monkeypatch):
    seen=[]
    class Fake:
        def generate_signal(self,f):
            seen.append(f.time.iloc[-1])
            return TradeSignal("ema_crossover","flat",0,100,150)
    monkeypatch.setattr(audit,"strategies",lambda:[Fake()])
    f=frame();cutoff=pd.Timestamp("2026-11-03T00:20:00Z")
    result=audit.cache_signals(f,cutoff)
    assert seen and min(seen)>=cutoff.tz_localize(None)
    assert all(audit.stamp(k)>=cutoff for k in result)


def test_isolated_replay_respects_loss_stop_and_does_not_read_future_scores():
    f=frame();f["low"]=98.;f=audit.prepare_frame(f)
    cache={audit.stamp(f.time.iloc[i]).isoformat():[{"strategy":"ema_crossover","side":"buy",
        "confidence":.8,"stop_loss_points":100.,"take_profit_points":150.}] for i in range(1200,len(f))}
    rules={"hold_bars":12,"max_trades_day":6,"max_losses":2,"daily_loss_r":1.2,
        "point":.01,"max_spread_points":80,"fee_points":0,"slippage_bps":0}
    rows=audit.evaluate(f,cache,"ema_crossover","current_immediate","2026-11-02T20:00Z",
        "2026-11-02T21:00Z",Settings(1,"test","Demo"),rules)
    assert len(rows)==2
    assert all(r["gross_r"]==pytest.approx(-1) and r["net_r"]==pytest.approx(-1.1) for r in rows)
    assert all(audit.stamp(r["exit_at"])<pd.Timestamp("2026-11-02T21:00Z") for r in rows)


def test_training_qualification_is_not_a_broker_promotion():
    stats={"trades":12,"days":2,"mean_r":.2,"profit_factor":1.5,"max_drawdown_r":2,"wins":8,"losses":4}
    assert audit.qualifies(stats,minimum_trades=12)
    assert not audit.qualifies(stats)  # prospective sample requirement stays 30
    assert not audit.qualifies({**stats,"mean_r":-.1},minimum_trades=12)


def test_forward_fails_before_data_access_when_research_source_changes(tmp_path):
    (tmp_path/"manifest.json").write_text(json.dumps({"sources":{}}))
    with pytest.raises(ValueError,match="frozen_research_source_changed"):
        audit.forward_once(tmp_path)


def test_bad_prices_or_missing_spread_cannot_silently_enter_results():
    f=frame(20);f.loc[5,"high"]=98
    with pytest.raises(ValueError,match="invalid_ohlc"):audit.prepare_frame(f)
    f=frame(20);f.loc[5,"spread"]=float("nan")
    with pytest.raises(ValueError,match="invalid_price_or_spread"):audit.prepare_frame(f)
