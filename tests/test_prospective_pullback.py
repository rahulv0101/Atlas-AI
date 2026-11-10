from dataclasses import replace
from types import SimpleNamespace as NS
from datetime import datetime,timezone
import json

import pandas as pd
import pytest

from atlas_ai.data.timeframe_bias import bias_from_closes
from atlas_ai.trader import AtlasTrader
from tools.prospective_pullback import filter_h1,stage_report


def test_partial_slow_window_cannot_fabricate_bullish_higher_timeframe_alignment():
    assert bias_from_closes([100.]*25)=="unknown"
    assert bias_from_closes([100.]*29)=="unknown"
    assert bias_from_closes([100.]*30)=="flat"
    assert bias_from_closes([100.]*29+[float("nan")])=="unknown"
    trader=AtlasTrader.__new__(AtlasTrader)
    trader.feed=NS(get_rates_for_timeframe=lambda *args,**kwargs:pd.DataFrame({"close":[100.]*25}))
    assert trader._timeframe_bias("H1")=="unknown"


def test_valid_bias_windows_keep_the_existing_ten_thirty_mean_rule():
    for closes in ([100.]*30,list(range(100,130)),list(range(130,100,-1))):
        fast=sum(closes[-10:])/10;slow=sum(closes[-30:])/30
        expected="buy" if fast>slow*1.0002 else "sell" if fast<slow*.9998 else "flat"
        assert bias_from_closes(closes)==expected


def test_future_h1_candles_cannot_change_an_earlier_paper_decision():
    n=2400;closes=[2000+i*.01 for i in range(n)]
    frame=pd.DataFrame({"time":pd.date_range("2026-11-09T00:00",periods=n,freq="min"),
        "open":closes,"high":[v+.1 for v in closes],"low":[v-.1 for v in closes],"close":closes,
        "tick_volume":100.,"spread":20.})
    candidate={"available_at":"2026-11-10T10:15:00+00:00","signal":{"side":"buy"}}
    before=filter_h1(frame,[candidate]);assert before
    changed=frame.copy();changed.loc[changed.time>=pd.Timestamp("2026-11-10T10:00"),["open","high","low","close"]]+=1000
    assert filter_h1(changed,[candidate])==before
    assert pd.Timestamp(before[0]["h1_available_at"])<=pd.Timestamp(candidate["available_at"])


def test_missing_hour_group_cannot_count_toward_minimum_thirty_h1_closes():
    n=30*60
    frame=pd.DataFrame({"time":pd.date_range("2026-11-09T00:00",periods=n,freq="min"),
        "open":2000.,"high":2001.,"low":1999.,"close":2000.,"tick_volume":100.,"spread":20.})
    frame.loc[frame.index[-600:],"close"]=2000.8
    frame.loc[frame.index[-600:],"high"]=2001.8
    candidate={"available_at":"2026-11-10T06:00:00+00:00","signal":{"side":"buy"}}
    assert filter_h1(frame,[candidate])
    assert not filter_h1(frame.drop(index=100).reset_index(drop=True),[candidate])


def test_successive_evidence_stages_do_not_sum_cases_or_authorize_trading():
    rows=[{"entry_at":f"2026-11-{11+i//10:02}T10:00:00Z","session":"london",
        "net_r":.2,"spread_fee_r":.25,"gross_r":.3} for i in range(60)]
    assert not stage_report(rows[:30])["research_review_ready"]
    ready=stage_report(rows)
    assert ready["research_review_ready"] and not ready["broker_eligible"] and ready["orders_sent"]==0
    bad=rows[:30]+[{**r,"net_r":-.1} for r in rows[30:]]
    assert not stage_report(bad)["research_review_ready"]


def test_frozen_manifest_changes_are_rejected_before_any_broker_access(tmp_path):
    from tools import prospective_pullback as module
    source=tmp_path/"source";source.mkdir()
    (source/"manifest.json").write_text(json.dumps({"symbol":"XAUUSD","rules":{"slippage_bps":1.5},"simulator_settings":{}}))
    run=tmp_path/"paper";module.start(run,source)
    m=json.loads((run/"manifest.json").read_text());m["rules"]["slippage_bps"]=0
    (run/"manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError,match="manifest_changed"):module.once(run)


def test_paper_collection_excludes_pre_freeze_cases_resumes_and_detects_data_tampering(tmp_path,monkeypatch):
    from tools import prospective_pullback as module
    from atlas_ai.config.settings import Settings
    class Clock(datetime):
        current=datetime(2026,11,10,10,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz=None):return cls.current
    monkeypatch.setattr(module,"datetime",Clock)
    source=tmp_path/"source";source.mkdir()
    rules={"point":.01,"fee_points":0.,"slippage_bps":1.5,"max_spread_points":80,
        "max_trades_day":6,"max_losses":2,"daily_loss_r":1.2}
    (source/"manifest.json").write_text(json.dumps({"symbol":"XAUUSD","rules":rules,"simulator_settings":{}}))
    settings=Settings(1,"test","Demo",storage_dir=str(tmp_path))
    monkeypatch.setattr(module,"load_settings",lambda:settings)
    run=tmp_path/"paper";module.start(run,source)
    monkeypatch.setattr(module,"attach",lambda _:None)
    times=pd.date_range(end="2026-11-10T12:00",periods=5000,freq="min")
    f=pd.DataFrame({"time":times,"open":2000.,"high":2001.,"low":1999.,"close":2000.,"tick_volume":100.,"spread":20.})
    def feed(actual):
        assert actual.mt5_server_timezone==json.loads((run/"manifest.json").read_text())["broker_clock_timezone"]
        return NS(get_rates=lambda _:f.copy())
    monkeypatch.setattr(module,"MarketDataFeed",feed)
    def candidate(at):
        return {"available_at":at,"bar_utc":(pd.Timestamp(at)-pd.Timedelta(minutes=15)).isoformat(),
            "timeframe_minutes":15,"signal":{"strategy":"test","side":"buy","confidence":.8,
                "stop_loss_points":1000.,"take_profit_points":1500.}}
    monkeypatch.setattr(module,"signal_cache",lambda *args:[candidate("2026-11-10T09:45Z"),candidate("2026-11-10T10:15Z")])
    monkeypatch.setattr(module,"filter_h1",lambda frame,candidates:candidates)
    Clock.current=datetime(2026,11,10,12,1,tzinfo=timezone.utc)
    first=module.once(run)
    assert first["total_paper_outcomes"]==1 and first["orders_sent"]==0 and not first["research_review_ready"]
    assert module.once(run)["total_paper_outcomes"]==1
    monkeypatch.setattr(module,"load_settings",lambda:replace(settings,mt5_server_timezone="Europe/London"))
    assert module.once(run)["total_paper_outcomes"]==1  # frozen broker clock is retained
    assert len(json.loads((run/"signals.json").read_text()))==1
    with (run/"observed_candles.csv").open("a") as stream:stream.write("\n")
    with pytest.raises(ValueError,match="artifact_changed"):module.once(run)
