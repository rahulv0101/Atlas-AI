from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import json

import pandas as pd
import pytest

from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import Settings
from atlas_ai.strategies.research_protocol import environment_versions
from atlas_ai.testing.decision_archive import capture,index_rows
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.penalty_shadow import paired_candidate,stage
from tools import penalty_shadow as tool
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import save_signed

NOW=datetime(2026,11,13,14,tzinfo=timezone.utc)


def inputs():
    context={"allowed_session":True,"session":"london","regime":"trend","trend_strength":.2,
        "volatility_state":"normal","entry_wickiness":.6,"entry_location_state":"consolidation",
        "entry_momentum_state":"weak","entry_expansion":0.,"entry_position":.5}
    learning={"state":{"historical_loss_analysis":{"patterns":{"classification":[{"value":"stop_hunt","count":55}]}},
                       "loss_memory":{"pattern_lessons":{}}}}
    status={"updated_at":(NOW+timedelta(minutes=1)).isoformat(),"symbol":"XAUUSD","timeframe":"M1",
        "chosen":{"strategy":"ema_crossover","side":"buy","confidence":.2,"signal_confidence_seed":.43,
                  "stop_loss_points":100.,"take_profit_points":150.},
        "signal_generation":{"context":context,"candidates":[{"strategy":"ema_crossover",
            "before_filters":{"side":"buy","confidence":.5},"after_filters":{"side":"buy","confidence":.43}}]},
        "decision_analysis":{"confidence_score":20},"min_confidence_threshold":.3,
        "timing_discipline":{"passed":True}}
    return learning,status


@pytest.fixture
def conviction(monkeypatch):
    # Distinct final-score scale deliberately differs from seed confidence.
    monkeypatch.setattr("atlas_ai.testing.penalty_shadow.build_structured_decision_analysis",
        lambda status,**kw:{"confidence_score":20 if status["chosen"]["signal_confidence_seed"]<.5 else 40})


def test_alternative_removes_only_aggregate_penalty_and_uses_final_conviction(conviction):
    learning,status=inputs();settings=Settings(0,"","",timeframe="M1")
    pair,reason=paired_candidate(settings,learning,status)
    assert reason is None and pair["seed_baseline"]==pytest.approx(.43) and pair["seed_alternative"]==.5
    assert pair["conviction_baseline"]==.2 and pair["conviction_alternative"]==.4
    assert not pair["admit_baseline"] and pair["admit_alternative"]
    assert not pair["other_execution_gates_verified"]


def test_recorded_timing_and_reconstruction_are_not_silently_bypassed(conviction):
    learning,status=inputs();settings=Settings(0,"","",timeframe="M1")
    status["timing_discipline"]["passed"]=False
    pair,_=paired_candidate(settings,learning,status)
    assert not pair["admit_baseline"] and not pair["admit_alternative"]
    status["decision_analysis"]["confidence_score"]=99
    assert paired_candidate(settings,learning,status)[1]=="baseline_analysis_not_reproduced"


def test_fingerprint_lesson_remains_active_in_both_arms(conviction):
    from atlas_ai.testing.confidence_penalty_audit import make_trader
    learning,status=inputs();settings=Settings(0,"","",timeframe="M1")
    trader=make_trader(settings,learning);ctx=status["signal_generation"]["context"]
    fingerprint=trader._build_trade_pattern_fingerprint(strategy="ema_crossover",side="buy",
        setup_family=trader._strategy_to_setup_family("ema_crossover"),session="london",regime="trend",context=ctx)
    learning["state"]["loss_memory"]["pattern_lessons"]={fingerprint:{"fingerprint":fingerprint,"samples":2,
        "losses":2,"loss_rate":1.,"execution_lesson":{"classification":"stop_hunt"}}}
    from atlas_ai.testing.confidence_penalty_audit import trace_candidate
    actual=trace_candidate(settings,learning,ctx,status["signal_generation"]["candidates"][0])["replayed_confidence"]
    status["signal_generation"]["candidates"][0]["after_filters"]["confidence"]=actual
    status["chosen"]["signal_confidence_seed"]=actual
    pair,_=paired_candidate(settings,learning,status)
    assert pair["seed_alternative"]<.5
    assert pair["seed_baseline"]==pytest.approx(.86*pair["seed_alternative"])


@pytest.fixture
def experiment(tmp_path,conviction):
    directory=tmp_path/"run";snapshot=directory/"frozen_source";snapshot.mkdir(parents=True)
    (snapshot/"helper.py").write_text("# frozen method\n")
    source=tmp_path/"paper";source.mkdir()
    times=pd.date_range(NOW,periods=40,freq="min").tz_localize(None)
    frame=pd.DataFrame({"time":times,"open":[100+i*.1 for i in range(40)],
        "close":[100.05+i*.1 for i in range(40)],"high":[100.2+i*.1 for i in range(40)],
        "low":[99.8+i*.1 for i in range(40)],"tick_volume":100.,"spread":2.})
    frame.to_csv(source/"observed_candles.csv",index=False)
    atomic_json(source/"artifacts.json",{"observed_candles.csv":tool.digest(source/"observed_candles.csv")})
    cfg=Settings(0,"","",timeframe="M1",backtest_max_hold_bars=12)
    manifest={"schema":"atlas_penalty_shadow_v1","method":tool.METHOD,"storage":str(tmp_path),
        "paper_source":str(source),"frozen_at":NOW.isoformat(),"deadline":(NOW+timedelta(days=10)).isoformat(),
        "settings":safe_settings(cfg),"spec":asdict(BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2)),
        "variant":asdict(ExitVariant("current",.05,3.)),"source_hashes":{"helper.py":tool.digest(snapshot/"helper.py")},
        "analysis_environment":{},"environment":environment_versions(),"broker_eligible":False,"auto_promotion":False,"orders_sent":0}
    save_signed(directory,"manifest",manifest)
    learning,status=inputs();atomic_json(tmp_path/"learning_state.json",learning);atomic_json(tmp_path/"status.json",status)
    capture(tmp_path,NOW+timedelta(minutes=1))
    return directory,tmp_path,source,frame


def test_pending_outcomes_wait_for_full_horizon_and_resume_without_duplicates(experiment):
    directory,_,_,_=experiment
    early=tool.once(directory,NOW+timedelta(minutes=5))
    assert early["resolved_pairs"]==0 and early["pending_pairs"]==1
    later=tool.once(directory,NOW+timedelta(minutes=20))
    assert later["resolved_pairs"]==1 and later["pending_pairs"]==0
    assert later["first_stage"]["baseline"]["paper_admissions"]==0
    assert later["first_stage"]["alternative"]["paper_admissions"]==1
    assert tool.once(directory,NOW+timedelta(minutes=21))["resolved_pairs"]==1
    assert not later["broker_eligible"] and not later["full_live_policy_parity"]


def test_uncommitted_source_waits_and_revised_resolved_prices_block(experiment):
    directory,_,source,frame=experiment
    original=(source/"observed_candles.csv").read_bytes()
    (source/"observed_candles.csv").write_bytes(original+b"uncommitted\n")
    result=tool.once(directory,NOW+timedelta(minutes=20))
    assert not result["candle_snapshot_committed"] and result["pending_pairs"]==1
    (source/"observed_candles.csv").write_bytes(original)
    tool.once(directory,NOW+timedelta(minutes=20))
    before=(directory/"checkpoint.json").read_bytes()
    frame.loc[3,"close"]+=.1;frame.to_csv(source/"observed_candles.csv",index=False)
    atomic_json(source/"artifacts.json",{"observed_candles.csv":tool.digest(source/"observed_candles.csv")})
    with pytest.raises(ValueError,match="resolved_prices_revised"):tool.once(directory,NOW+timedelta(minutes=21))
    assert (directory/"checkpoint.json").read_bytes()==before


def test_archive_input_tampering_is_detected_after_resume(experiment):
    directory,storage,_,_=experiment;tool.once(directory,NOW+timedelta(minutes=20))
    row=index_rows(storage/"replay_evidence")[0]
    (storage/"replay_evidence/records"/(row["record_id"]+".json.gz")).write_bytes(b"changed")
    with pytest.raises(ValueError,match="archive_record_changed"):tool.once(directory,NOW+timedelta(minutes=21))


def test_cases_are_not_all_sampled_from_one_early_session(experiment):
    directory,storage,_,_=experiment;tool.once(directory,NOW+timedelta(minutes=20))
    _,status=inputs();status["updated_at"]=(NOW+timedelta(minutes=25)).isoformat()
    atomic_json(storage/"status.json",status);capture(storage,NOW+timedelta(minutes=25))
    result=tool.once(directory,NOW+timedelta(minutes=39))
    assert result["resolved_pairs"]==1 and result["excluded"]["sampling_band_limit"]==1


def test_sufficient_cases_with_no_contrast_cannot_pass_screening():
    rows=[{"seed_baseline":.4,"seed_alternative":.4,"admit_baseline":False,"admit_alternative":False,"net_r":1.,"net_cash":10.}]*30
    assert not stage(rows)["contrast_sufficient_for_review"]


def test_supervision_respects_sleep_lock_and_restart_budget(experiment):
    from unittest.mock import Mock
    from atlas_ai.learning.observation_checkpoint import observation_lock
    directory,storage,_,_=experiment
    atomic_json(storage/"penalty_shadow_active.json",{"run_dir":str(directory)})
    launch=Mock(side_effect=AssertionError("must not launch"))
    assert tool.ensure(storage,{},can_start=False,now=NOW,start=launch)["state"]=="waiting_for_backend_and_operator_awake"
    with observation_lock(directory/"watch.lock"):
        assert tool.ensure(storage,{},can_start=True,now=NOW,start=launch)["state"]=="existing_paired_observer_running"
    state={"penalty_shadow_starts":[NOW.timestamp()]*3}
    assert tool.ensure(storage,state,can_start=True,now=NOW,start=launch)["state"]=="restart_budget_exhausted_review_required"


def test_environment_freeze_refuses_private_values(tmp_path,monkeypatch):
    folder=tmp_path/"atlas_ai/analysis";folder.mkdir(parents=True)
    for name in ["decision_analysis","chart_analysis","setup_playbook","market_regime"]:
        (folder/(name+".py")).write_text("")
    (folder/"decision_analysis.py").write_text("import os\nvalue=os.getenv('OPENAI_API_KEY')\n")
    monkeypatch.setattr(tool,"ROOT",tmp_path)
    with pytest.raises(ValueError,match="private_environment"):tool.analysis_environment()


def test_archive_writer_contention_waits_without_resetting_checkpoint(experiment):
    directory,storage,_,_=experiment
    tool.once(directory,NOW+timedelta(minutes=5))
    before=(directory/"checkpoint.json").read_bytes()
    with tool.observation_lock(storage/"replay_evidence/archive.lock"):
        result=tool.once(directory,NOW+timedelta(minutes=20))
    assert result["state"]=="collecting_paired_shadow"
    assert result["waiting_for_archive_writer"] and result["pending_pairs"]==1
    assert (directory/"checkpoint.json").read_bytes()==before
    assert tool.once(directory,NOW+timedelta(minutes=21))["resolved_pairs"]==1
