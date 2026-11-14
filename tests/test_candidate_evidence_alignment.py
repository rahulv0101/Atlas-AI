from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from atlas_ai.models import TradeSignal
from atlas_ai.trader import AtlasTrader
from atlas_ai.vision.chart_vision import rebase_visual_observation
from atlas_ai.vision.evidence_alignment import build_evidence_alignment,candle_evidence
from atlas_ai.strategies.distance_units import atr_distance_points,corrected_atr_signal,distance_unit_review


def status():
    now=datetime.now(timezone.utc);bar=now.replace(second=0,microsecond=0)
    return {"symbol":"XAUUSD","timeframe":"M1","market_data_clock":{"timestamp_basis":"UTC",
        "latest_bar_utc":bar.isoformat(),"ended_at":(bar+timedelta(seconds=10)).isoformat()},
        "chart_features":{"momentum_state":"weak","location_state":"mid_range","trend_state":"range","reliability":"low"}}


def observation():
    return {"symbol":"XAUUSD","timeframe":"M1","captured_at":(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat(),
        "source":"screenshot_plus_chart_features","live_chart_window_confirmed":True,"stale":False,
        "image":{"available":True,"contrast":.5},"visual_features":{"available":True,"status":"parsed",
            "visual_momentum":"strong","visual_direction":"up","visual_noise":"low","confidence":.8},
        "visual_confirmation":"supports_setup"}


def test_reused_image_is_rebased_without_freshening_its_capture_or_rewriting_pixels():
    old=observation();before=deepcopy(old);s=status()
    result=rebase_visual_observation(old,s)
    assert result["captured_at"]==old["captured_at"]
    assert result["visual_features"]==old["visual_features"] and old==before
    assert result["candle_evidence"]["bar_utc"]==s["market_data_clock"]["latest_bar_utc"]
    assert result["visual_confirmation"]=="does_not_confirm"
    assert result["evidence_alignment"]["screen_bar_matches_current"] is None


@pytest.mark.parametrize("field,value",[("symbol","EURUSD"),("timeframe","M15"),
    ("captured_at","2000-01-01T00:00:00+00:00"),("captured_at","2999-01-01T00:00:00+00:00")])
def test_stale_wrong_chart_or_future_screenshot_cannot_be_rebased(field,value):
    old=observation();old[field]=value
    with pytest.raises(ValueError):rebase_visual_observation(old,status())


def test_matching_labels_do_not_claim_same_screen_bar_and_candle_closed_state_is_historical():
    s=status();s["chart_features"]["momentum_state"]="strong"
    a=build_evidence_alignment(s,observation())
    assert a["momentum_relation"]=="agree" and a["screen_bar_matches_current"] is None
    assert candle_evidence(s)["bar_closed_at_evaluation"] is False
    assert "different measures" in a["summary"]


def test_missing_feature_packets_produce_unknown_evidence_without_breaking_status():
    a=build_evidence_alignment({"chart_features":None,"market_data_clock":None},{"visual_features":None,"candle_evidence":None})
    assert a["momentum_relation"]=="missing" and a["screen_bar_matches_current"] is None


def test_closed_bar_shadow_excludes_forming_bar_without_mutating_selection(monkeypatch):
    closes=[1000+i*.5 for i in range(120)]
    frame=pd.DataFrame({"time":pd.date_range("2026-11-10T10:00",periods=120,freq="min"),
        "close":closes,"open":[c-.4 for c in closes],"high":[c+.05 for c in closes],"low":[c-.45 for c in closes]})
    frame.loc[119,"open"]=frame.loc[119,"close"]
    chosen=TradeSignal("ema_crossover","buy",.8,100,150);before=deepcopy(chosen)
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=NS(symbol="XAUUSD",timeframe="M1")
    trader.base_strategies=[]
    monkeypatch.setattr("atlas_ai.trader.mt5.symbol_info",lambda _:NS(point=.01))
    s={"symbol":"XAUUSD","timeframe":"M1","chosen":{"side":"buy"},"market_data_clock":{
        "timestamp_basis":"UTC","latest_bar_utc":"2026-11-10T11:59:00+00:00","ended_at":"2026-11-10T11:59:10+00:00"}}
    trader._attach_candidate_evidence_review(s,frame,chosen,{})
    preview=s["closed_bar_entry_preview"]
    assert preview["available"] and preview["bar_utc"]=="2026-11-10T11:58:00+00:00"
    assert preview["momentum"]=="strong" and chosen==before and s["chosen"]["side"]=="buy"
    assert s["indicator_evidence"]["bar_closed_at_evaluation"] is False


def test_distance_adapter_preserves_signal_and_price_units_and_never_activates_itself():
    signal=TradeSignal("momentum_continuation","sell",.72,115,175)
    a=corrected_atr_signal(signal,10,.01);b=corrected_atr_signal(signal,10,.1)
    assert a.stop_loss_points*.01==pytest.approx(b.stop_loss_points*.1)
    assert a.side==signal.side and a.confidence==signal.confidence and signal.stop_loss_points==115
    assert distance_unit_review(signal,10,.01)["activation_state"]=="correction_in_research_only"
    with pytest.raises(ValueError):atr_distance_points(10,2,0,100)


def test_visual_strength_cannot_override_weak_candle_momentum():
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=NS(timeframe="M1",timing_allow_mid_range_strong_momentum=False)
    s=status();v=observation();v.update(visual_watch_used_for_decision=True,
        visual_confirmation="supports_setup",visual_features={"visual_momentum":"strong","visual_location":"pullback","visual_direction":"up"})
    s["visual_chart_read"]=v
    result=trader._timing_discipline_snapshot(TradeSignal("ema_crossover","buy",.8,100,150),
        {"entry_momentum_state":"weak","entry_location_state":"pullback","entry_trend_state":"uptrend","trend_strength":.3},s)
    assert result["hard_block"] and "strong_or_turning_m1_momentum" in result["missing"]
    assert result["evidence_alignment"]["momentum_relation"]=="different"
