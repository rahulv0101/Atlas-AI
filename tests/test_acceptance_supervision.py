from datetime import datetime,timedelta,timezone
import hashlib
import json
from unittest.mock import Mock

import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.learning.observation_checkpoint import account_scope,save_checkpoint
from tools import supervise_acceptance as module


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    settings=Settings(1,"test","Demo",storage_dir=str(tmp_path))
    monkeypatch.setattr(module,"load_settings",lambda:settings)
    paper=tmp_path/"paper";snapshot=paper/"frozen_source";snapshot.mkdir(parents=True)
    hashes={}
    for name in ("tools/prospective_pullback.py","tools/observe_day_trading.py"):
        path=snapshot/name;path.parent.mkdir(exist_ok=True);path.write_text("# fixed test source\n")
        hashes[name]=module.digest(path)
    manifest={"schema":"atlas_prospective_pullback_v1","broker_eligible":False,"auto_promotion":False,"orders_sent":0,
        "broker_clock_timezone":settings.mt5_server_timezone,
        "symbol":"XAUUSD","account_scope":account_scope(settings),"frozen_at":"2026-11-10T19:51:19+00:00",
        "minimum_cases_per_stage":30,"rules":{"max_trades_day":6},"source_hashes":hashes,
        "environment":module.environment_versions()}
    (paper/"manifest.json").write_text(json.dumps(manifest))
    (paper/"manifest.sha256").write_text(module.digest(paper/"manifest.json"))
    (paper/"observed_candles.csv").write_text("fixed observed evidence\n")
    (paper/"signals.json").write_text("{}")
    (paper/"artifacts.json").write_text(json.dumps({name:module.digest(paper/name) for name in ("observed_candles.csv","signals.json")}))
    (paper/"status.json").write_text(json.dumps({"research_review_ready":False}))
    (paper/"outcomes.json").write_text("[]")
    journal=tmp_path/"journal.jsonl";journal.write_text("{}\n")
    save_checkpoint(journal.with_suffix(".checkpoint.json"),settings,set(),{},set(),
        {"orders_sent":0,"lifecycle_acceptance":{"state":"awaiting_autonomous_broker_cycle","verified_end_to_end_cycles":[]}},journal=journal)
    plan=module.create_plan(tmp_path/"plan.json",paper,journal)
    return plan,settings,paper,journal


def now():return datetime(2026,11,11,10,tzinfo=timezone.utc)


def test_six_trades_per_day_requires_at_least_ten_trading_days_for_both_stages(fixture):
    plan,_,paper,_=fixture
    assert plan["minimum_possible_trading_days"]==10
    assert datetime.fromisoformat(plan["deadline"])-datetime.fromisoformat(plan["frozen_at"])==timedelta(days=30)
    assert json.loads((paper/"manifest.json").read_text())["minimum_cases_per_stage"]==30


def test_healthy_collectors_are_reused_without_duplicates_or_policy_changes(fixture):
    plan,_,paper,_=fixture;before=(paper/"manifest.json").read_bytes()
    launch=Mock(side_effect=AssertionError("Healthy collector must not be replaced"))
    result=module.tick(plan,{},now(),is_busy=lambda *args:True,start_worker=launch,backend_ready=True)
    assert set(result["collector_actions"].values())=={"existing_collector_running"}
    assert not result["broker_eligible"] and result["orders_sent"]==0 and (paper/"manifest.json").read_bytes()==before


def test_expired_worker_windows_resume_original_evidence_with_bounded_chunks(fixture):
    plan,_,_,journal=fixture;launch=Mock(return_value=123)
    result=module.tick(plan,{},now(),is_busy=lambda *args:False,start_worker=launch,backend_ready=True)
    assert launch.call_count==2 and all("resumed_saved_evidence" in action for action in result["collector_actions"].values())
    paper=module.worker_command(plan,"paper",500)
    natural=module.worker_command(plan,"natural",500)
    assert float(paper[paper.index("--hours")+1])==168
    assert float(natural[natural.index("--minutes")+1])==10080
    assert "--resume" in natural and str(journal)==natural[natural.index("--output")+1]
    assert "--execute" not in paper+natural and "atlas_ai.main" not in paper+natural


@pytest.mark.parametrize("sleep,backend",[(False,False),(True,True)])
def test_supervisor_cannot_wake_a_stopped_backend_or_override_sleep(fixture,sleep,backend):
    plan,settings,_,_=fixture
    (module.Path(settings.storage_dir)/"automation_state.json").write_text(json.dumps({"sleep_mode_active":sleep}))
    launch=Mock(side_effect=AssertionError("No observer restart authorized in standby"))
    result=module.tick(plan,{},now(),is_busy=lambda *args:False,start_worker=launch,backend_ready=backend)
    assert all("no_restart" in action or "waiting_for_explicit_backend_start"==action for action in result["collector_actions"].values())


def test_plan_deadline_and_restart_budget_are_enforced(fixture):
    plan,_,_,_=fixture;launch=Mock(side_effect=AssertionError("No restart permitted"))
    expired=datetime.fromisoformat(plan["deadline"])+timedelta(seconds=1)
    result=module.tick(plan,{},expired,is_busy=lambda *args:False,start_worker=launch,backend_ready=True)
    assert result["state"]=="window_completed"
    state={"starts":{role:[now().timestamp()-i for i in (10,20,30)] for role in ("paper","natural")}}
    result=module.tick(plan,state,now(),is_busy=lambda *args:False,start_worker=launch,backend_ready=True)
    assert all("budget_exhausted" in action for action in result["collector_actions"].values())


def test_source_or_data_tampering_blocks_restart_without_resetting_experiment(fixture):
    plan,_,paper,_=fixture;launch=Mock(side_effect=AssertionError("Corrupt evidence cannot be resumed"))
    (paper/"observed_candles.csv").write_text("changed")
    with pytest.raises(ValueError,match="artifact_changed"):
        module.tick(plan,{},now(),is_busy=lambda *args:False,start_worker=launch,backend_ready=True)
    (module.Path(plan["source_root"])/"tools/observe_day_trading.py").write_text("changed")
    with pytest.raises(ValueError,match="source_changed"):
        module.tick(plan,{},now(),is_busy=lambda *args:False,start_worker=launch,backend_ready=True)


def test_diagnostic_or_manual_cycles_never_satisfy_natural_proof(fixture):
    plan,settings,_,journal=fixture
    save_checkpoint(journal.with_suffix(".checkpoint.json"),settings,set(),{},set(),{"orders_sent":0,
        "lifecycle_acceptance":{"state":"verified","verified_end_to_end_cycles":[{"strategy":"manual_broker_test"}],
            "manual_and_forced_tests_count_as_acceptance":True}},journal=journal)
    result=module.tick(plan,{},now(),is_busy=lambda *args:True,backend_ready=True)
    assert not result["natural_cycle_verified"] and not result["broker_eligible"]


def test_review_evidence_does_not_automatically_promote_or_link_different_strategies(fixture):
    plan,settings,paper,journal=fixture
    (paper/"outcomes.json").write_text(json.dumps([{}]*60))
    (paper/"status.json").write_text(json.dumps({"research_review_ready":True}))
    save_checkpoint(journal.with_suffix(".checkpoint.json"),settings,set(),{},set(),{"orders_sent":0,
        "lifecycle_acceptance":{"state":"verified","verified_end_to_end_cycles":[{"strategy":"some_other_strategy"}],
            "manual_and_forced_tests_count_as_acceptance":False}},journal=journal)
    result=module.tick(plan,{},now(),is_busy=lambda *args:True,backend_ready=True)
    assert result["state"]=="evidence_available_for_operator_review" and not result["broker_eligible"]
    assert "same-version" in result["note"]
