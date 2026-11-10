from dataclasses import replace
import json
from types import SimpleNamespace as NS

import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.learning.observation_checkpoint import save_checkpoint,load_checkpoint,observation_lock
from tools.observe_day_trading import lifecycle_summary,acceptance_summary


def settings(tmp_path):
    return Settings(hfm_login=1,hfm_password="test",hfm_server="Demo",storage_dir=str(tmp_path))


def test_restart_retains_protection_and_entry_evidence_for_a_later_exit(tmp_path):
    s=settings(tmp_path);p=tmp_path/"checkpoint.json"
    entry={"ticket":"1","position_id":"10","order_id":"101","entry":0,"deal_type":0,"broker_time_msc":1,"volume":.01,"net":-1}
    save_checkpoint(p,s,{"old"},{"1":entry},{"10"},{"orders_sent":0})
    baseline,seen,managed,summary=load_checkpoint(p,s)
    assert baseline=={"old"} and managed=={"10"} and summary["orders_sent"]==0
    seen["2"]={"ticket":"2","position_id":"10","order_id":"102","entry":1,"deal_type":1,"broker_time_msc":2,"volume":.01,"net":9}
    event={"meta":{"decision_id":"decision","strategy":"ema_crossover","order_id":"101",
        "request_origin":"trader_guarded","execution_success":True,"execution_mode":"demo"}}
    cycles=lifecycle_summary(seen,[event],set())
    assert acceptance_summary(cycles,managed)["state"]=="verified"
    assert acceptance_summary(cycles,set())["state"]=="management_evidence_missing"


@pytest.mark.parametrize("change",[{"hfm_login":2},{"hfm_server":"Other"},{"symbol":"EURUSD"},{"magic_number":999}])
def test_checkpoint_cannot_cross_account_symbol_or_magic_scope(tmp_path,change):
    s=settings(tmp_path);p=tmp_path/"checkpoint.json"
    save_checkpoint(p,s,set(),{},set(),{"orders_sent":0})
    with pytest.raises(ValueError,match="wrong_account"):
        load_checkpoint(p,replace(s,**change))


def test_corrupt_checkpoint_never_resets_into_an_empty_successful_run(tmp_path):
    s=settings(tmp_path);p=tmp_path/"checkpoint.json";p.write_text("broken")
    with pytest.raises(ValueError):load_checkpoint(p,s)
    save_checkpoint(p,s,set(),{},set(),{"orders_sent":0})
    row=json.loads(p.read_text());row["seen"]={"1":{"ticket":"different"}}
    p.write_text(json.dumps(row))
    with pytest.raises(ValueError,match="fill_identity"):load_checkpoint(p,s)


def test_duplicate_observer_is_rejected_and_lock_is_released(tmp_path):
    path=tmp_path/"observer.lock"
    with observation_lock(path):
        with pytest.raises(RuntimeError,match="already_running"):
            with observation_lock(path):pass
    with observation_lock(path):pass


def test_checkpoint_for_a_different_journal_cannot_be_loaded(tmp_path):
    s=settings(tmp_path);p=tmp_path/"checkpoint.json"
    save_checkpoint(p,s,set(),{},set(),{"orders_sent":0},journal=tmp_path/"first.jsonl")
    with pytest.raises(ValueError,match="journal_mismatch"):
        load_checkpoint(p,s,journal=tmp_path/"second.jsonl")


def test_resume_cli_observes_exit_without_losing_pre_restart_protection(tmp_path,monkeypatch):
    from tools import observe_day_trading as module
    s=settings(tmp_path);journal=tmp_path/"journal.jsonl";journal.write_text('{"prior":"retained"}\n')
    entry={"ticket":"1","position_id":"10","order_id":"101","entry":0,"deal_type":0,"broker_time_msc":1,"volume":.01,"net":-1}
    exit_fill={**entry,"ticket":"2","order_id":"102","entry":1,"deal_type":1,"broker_time_msc":2,"net":9}
    summary={"started_at":"2026-11-10T10:00:00Z","samples":1,"broker_unavailable_samples":0,
        "stale_status_samples":0,"verified_natural_cycles":[],"orders_sent":0,"status":"running"}
    save_checkpoint(journal.with_suffix(".checkpoint.json"),s,{"old"},{"1":entry},{"10"},summary,journal=journal)
    event={"meta":{"decision_id":"decision","strategy":"ema_crossover","order_id":"101",
        "request_origin":"trader_guarded","execution_success":True,"execution_mode":"demo"}}
    monkeypatch.setattr(module,"load_settings",lambda:s)
    monkeypatch.setattr(module.mt5,"terminal_info",lambda:object())
    monkeypatch.setattr(module.mt5,"shutdown",lambda:None)
    monkeypatch.setattr(module,"broker_snapshot",lambda *a,**kw:{"broker_ok":True,"history_ok":True,
        "positions":[],"pending_orders":[],"deals":[entry,exit_fill]})
    monkeypatch.setattr(module,"GuardedDecisionIndex",lambda _:NS(events=lambda:[event]))
    monkeypatch.setattr("sys.argv",["observe","--once","--resume","--output",str(journal)])
    module.main()
    result=json.loads((tmp_path/"lifecycle_acceptance.json").read_text())
    assert result["state"]=="verified" and result["verified_end_to_end_cycles"][0]["net"]==8
    assert result["orders_sent"]==0 and len(journal.read_text().splitlines())==2
    assert result["observer_state"]=="completed" and result["window_ends_at"]
    assert json.loads(journal.read_text().splitlines()[0])=={"prior":"retained"}
