import json
from pathlib import Path
from types import SimpleNamespace as NS
import threading

import pytest
from atlas_ai.atomic_files import atomic_json
import atlas_ai.atomic_files as module


def test_transient_windows_reader_lock_retries_without_truncating(tmp_path,monkeypatch):
    path=tmp_path/"state.json";path.write_text('{"old":true}')
    original=module.os.replace;calls=[]
    def replace(source,target):
        calls.append(source)
        assert json.loads(path.read_text())=={"old":True}
        if len(calls)<3:raise PermissionError("temporary reader")
        original(source,target)
    monkeypatch.setattr(module.os,"replace",replace);monkeypatch.setattr(module.time,"sleep",lambda _:None)
    atomic_json(path,{"new":True})
    assert json.loads(path.read_text())=={"new":True} and len(calls)==3
    assert not list(tmp_path.glob("*.tmp"))


def test_persistent_lock_preserves_valid_previous_state(tmp_path,monkeypatch):
    path=tmp_path/"state.json";path.write_text('{"old":true}')
    def denied(*args):raise PermissionError("reader remains locked")
    monkeypatch.setattr(module.os,"replace",denied);monkeypatch.setattr(module.time,"sleep",lambda _:None)
    with pytest.raises(PermissionError):atomic_json(path,{"new":True})
    assert json.loads(path.read_text())=={"old":True} and not list(tmp_path.glob("*.tmp"))


def test_invalid_json_numbers_do_not_replace_good_state(tmp_path):
    path=tmp_path/"state.json";atomic_json(path,{"old":True})
    with pytest.raises(ValueError):atomic_json(path,{"value":float("nan")})
    assert json.loads(path.read_text())=={"old":True}


def test_observer_publication_failure_is_reported_without_stopping(monkeypatch,tmp_path):
    from tools import observe_day_trading as observer
    def denied(*args):raise PermissionError("locked")
    monkeypatch.setattr(observer,"atomic_json",denied)
    diagnostics={}
    assert not observer.publish_json(tmp_path/"status.json",{},diagnostics)
    assert diagnostics["persistence_error_count"]==1
    assert "broker_unavailable_samples" not in diagnostics


def test_research_worker_survives_failure_of_error_report(monkeypatch,tmp_path):
    import atlas_ai.strategies.research_worker as research
    from atlas_ai.config.settings import Settings
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    stop=threading.Event();worker=research.StrategyResearchWorker(Settings(hfm_login=1,hfm_password="test",hfm_server="Demo"),KnowledgeStore(str(tmp_path)),stop)
    calls=[]
    def tick():
        calls.append(True)
        if len(calls)==1:raise PermissionError("locked")
        stop.set()
    def denied(*args):raise PermissionError("error report locked")
    monkeypatch.setattr(worker,"run_once",tick);monkeypatch.setattr(research,"atomic_json",denied)
    monkeypatch.setattr(stop,"wait",lambda timeout:False)
    worker._loop()
    assert len(calls)==2
