from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.learning.observation_checkpoint import observation_lock
from atlas_ai.testing.historical_broker import BrokerSpec
from tools import guarded_research_audit as audit
from tools import observe_guarded_research as observer
from tools.guarded_research_supervision import ensure_research


def save(path,value):
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result(mean=.2):
    rows=[{"entry_at":f"2026-11-{9+i%2:02d}T12:00Z","net_cash":1.,"net_r":mean} for i in range(30)]
    return {"trades":30,"wins":30,"profit_factor":None,"mean_net_r":mean,"max_drawdown_r":0.,"trade_list":rows}


def test_selection_uses_training_only_and_cannot_promote():
    comparisons={"a":{"training_reused":result(.2),"validation_reused":result(100)},
        "b":{"training_reused":result(.3),"validation_reused":result(-100)}}
    selected=audit.select_training(comparisons)
    assert selected["selected_for_forward"]=="b" and selected["selected_for_live"] is None
    assert not selected["broker_eligible"]
    comparisons["b"]["training_reused"]["trades"]=29
    assert audit.select_training(comparisons)["selected_for_forward"]=="a"


def test_settings_snapshot_excludes_credentials_and_personal_paths():
    cfg=Settings(123,"secret","Demo",gemini_api_key="private",openai_api_key="private2",hfm_terminal_path="private")
    saved=audit.safe_settings(cfg)
    assert not {"hfm_login","hfm_password","hfm_server","gemini_api_key","openai_api_key","hfm_terminal_path","storage_dir"}&saved.keys()


@pytest.fixture
def forward(tmp_path,monkeypatch):
    directory=tmp_path/"research";directory.mkdir()
    source=tmp_path/"paper";source.mkdir()
    snapshot=directory/"frozen_source";snapshot.mkdir()
    code=snapshot/"dummy.py";code.write_text("# frozen\n")
    data=pd.DataFrame({"time":pd.date_range("2026-11-09T08:00Z",periods=300,freq="min").tz_localize(None),
        "open":100.,"high":101.,"low":99.,"close":100.,"spread":20.,"tick_volume":100.})
    def publish(data):
        data.to_csv(source/"observed_candles.csv",index=False)
        save(source/"artifacts.json",{"observed_candles.csv":audit.digest(source/"observed_candles.csv")})
    publish(data)
    manifest={"schema":"atlas_guarded_research_v2","broker_eligible":False,"auto_promotion":False,
        "environment":observer.environment_versions(),"source_hashes":{"dummy.py":audit.digest(code)},
        "forward_source_run":str(source),"future_holdout_start":"2026-11-09T12:00:00+00:00",
        "deadline":"2026-12-10T19:51:00+00:00","settings":audit.safe_settings(Settings(1,"","Demo",timeframe="M1")),
        "spec":asdict(BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2)),
        "variants":[{"name":"current","lock_r":.05,"slippage_points_per_side":0.,"cost_aware_lock":False}],
        "limits":{"day_trades":6,"loss_streak":2,"daily_loss_percent":.6,"lot_cap":.01,"setup_family":"continuation"}}
    for name,value in (("manifest",manifest),("selection",{"selected_for_forward":"ema_crossover/current/slip_0.0"})):
        digest=save(directory/f"{name}.json",value);(directory/f"{name}.sha256").write_text(digest)
    clock=type("Clock",(datetime,),{"now":staticmethod(lambda tz:datetime(2026,11,9,13,tzinfo=timezone.utc))})
    monkeypatch.setattr(observer,"datetime",clock)
    cache=Mock(return_value=([],{},[]));monkeypatch.setattr(observer,"cache_candidates",cache)
    monkeypatch.setattr(observer,"replay",Mock(return_value={"trades":0,"trade_list":[],"rejections":{}}))
    return directory,data,publish,cache


def test_forward_resumes_cached_closed_bars_and_rejects_revised_history(forward):
    directory,data,publish,cache=forward
    first=observer.once(directory)
    assert first["new_paper_outcomes"]==0 and not first["broker_eligible"]
    extended=pd.concat([data,data.tail(1).assign(time=data.time.iloc[-1]+pd.Timedelta(minutes=1))],ignore_index=True)
    publish(extended);observer.once(directory)
    assert cache.call_args.kwargs["start_index"]==299
    extended.loc[0,"close"]=100.5;publish(extended)
    with pytest.raises(ValueError,match="candles_revised"):observer.once(directory)


def test_forward_refuses_evidence_without_integrity_or_tampered_protocol(forward):
    directory,_,_,_=forward
    (directory/"forward_candles.json").write_text("[]")
    with pytest.raises(ValueError,match="unverified_forward"):observer.once(directory)
    (directory/"manifest.json").write_text("{}")
    with pytest.raises(ValueError,match="protocol_changed"):observer.once(directory)


def test_forward_thirty_case_stages_require_two_days_and_preserve_losses():
    rows=result()["trade_list"]
    assert audit.qualified(observer.stage_stats(rows))
    assert not audit.qualified(observer.stage_stats(rows[:29]))
    losses=[{**row,"net_cash":-1,"net_r":-1} for row in rows]
    assert not audit.qualified(observer.stage_stats(losses))


def test_research_supervision_reuses_lock_and_cannot_start_in_sleep(forward,tmp_path):
    directory,_,_,_=forward
    save(tmp_path/"guarded_research_active.json",{"run_dir":str(directory)})
    start=Mock(return_value=SimpleNamespace(pid=7))
    now=datetime(2026,11,10,tzinfo=timezone.utc)
    assert ensure_research(tmp_path,{},can_start=False,now=now,start=start)["state"]=="waiting_for_backend_and_operator_awake"
    start.assert_not_called()
    with observation_lock(directory/"forward.lock"):
        assert ensure_research(tmp_path,{},can_start=True,now=now,start=start)["state"]=="existing_collector_running"
    assert ensure_research(tmp_path,{},can_start=True,now=now,start=start)["pid"]==7
    command=start.call_args.args[0]
    assert "--watch" in command and "--execute" not in command and "atlas_ai.main" not in command
