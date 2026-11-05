from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.learning.trade_labeling import _simulate_trade_path
from atlas_ai.models import TradeSignal
from tools.timing_discipline_selectivity_report import _extract_candidate, _nearest_signal_index, _simulate


@pytest.mark.parametrize("unit", ["ns", "us", "ms"])
def test_event_matches_real_bar_using_consistent_timestamp_units(unit):
    times = pd.date_range("2026-11-05T08:00:00Z", periods=5, freq="min").as_unit(unit)
    frame = pd.DataFrame({"time": times})
    assert _nearest_signal_index(frame, datetime(2026,11,5,8,2,30,tzinfo=timezone.utc)) == 2
    assert _nearest_signal_index(frame, datetime(2026,11,5,7,tzinfo=timezone.utc)) is None
    assert _nearest_signal_index(frame, datetime(2026,11,5,9,tzinfo=timezone.utc)) is None


def event():
    return {"time": "2026-11-05T08:02:30Z", "message": "Executed buy", "meta": {"timeframe":"M1", "market_data_clock":{"timestamp_basis":"UTC"}, "chosen":{"strategy":"test", "side":"buy", "stop_loss_points":100, "take_profit_points":160}, "execution_request_created":True}}


def extract(row):
    return _extract_candidate(row, Path(__file__).resolve().parents[1]/"storage/events.jsonl")


def test_request_creation_and_pending_acceptance_are_not_completed_fills():
    row=event();assert extract(row) is None
    row["meta"]["execution"]={"success":True,"broker_order_id":"123","broker_status":"submitted"}
    assert extract(row) is None
    row["meta"]["execution"]["broker_status"]="filled"
    assert extract(row).group == "timing_passed_executed"


@pytest.mark.parametrize("missing", ["clock", "stop", "target"])
def test_legacy_missing_evidence_is_excluded_instead_of_invented(missing):
    row=event();row["message"]="Timing discipline blocked trade"
    if missing=="clock":row["meta"].pop("market_data_clock")
    else:row["meta"]["chosen"].pop("stop_loss_points" if missing=="stop" else "take_profit_points")
    assert extract(row) is None


@pytest.mark.parametrize("side,close", [("buy",101),("sell",99)])
def test_offline_stop_first_policy_does_not_assume_favorable_intrabar_order(side,close):
    frame=pd.DataFrame({"open":[100]*3,"high":[102]*3,"low":[98]*3,"close":[close]*3})
    settings=Settings(1,"test","Demo")
    signal=TradeSignal("test",side,.8,100,100)
    assert _simulate_trade_path(frame,signal,0,settings)["r_multiple"] == 1
    assert _simulate_trade_path(frame,signal,0,settings,ambiguous_bar_policy="stop_first")["r_multiple"] == -1


def test_incomplete_forward_horizon_cannot_be_reported_as_finished_trade():
    row=event();row["message"]="Timing discipline blocked trade"
    candidate=extract(row)
    frame=pd.DataFrame({"time":pd.date_range("2026-11-05T08:00:00Z",periods=5,freq="min")})
    results,skipped=_simulate([candidate],frame,Settings(1,"test","Demo"))
    assert results==[] and skipped==1
