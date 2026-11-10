from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from atlas_ai.learning.decision_index import GuardedDecisionIndex
from atlas_ai.learning.closed_position_ledger import _decisions


def setup(tmp_path):
    return NS(hfm_login=1,hfm_server="Demo",storage_dir=tmp_path)


def meta(**extra):
    return dict(decision_id="abcdef12",strategy="ema_crossover",request_origin="trader_guarded",
                execution_success=True,execution_mode="demo",order_id=101,**extra)


def test_index_survives_main_event_rotation_and_deduplicates(tmp_path):
    settings=setup(tmp_path);index=GuardedDecisionIndex(settings)
    assert index.record(meta()) is True
    assert index.record(meta()) is False
    restored=GuardedDecisionIndex(settings).events()
    refs,ids=_decisions(restored)
    assert refs["101"][0]["strategy"]=="ema_crossover" and len(restored)==1
    assert ids["abcdef"]


@pytest.mark.parametrize("change",[{"execution_success":False},{"execution_mode":"paper"},
    {"request_origin":"manual"},{"comment":"manual_broker_test"},{"order_id":"BRK_FAKE"},
    {"strategy":"unknown"},{"decision_id":""}])
def test_index_does_not_create_verified_evidence_from_unproven_records(tmp_path,change):
    row=meta();row.update(change)
    index=GuardedDecisionIndex(setup(tmp_path));assert index.record(row) is False
    assert index.events()==[]


def test_index_is_account_scoped_and_preserves_ambiguity(tmp_path):
    index=GuardedDecisionIndex(setup(tmp_path));index.record(meta())
    assert GuardedDecisionIndex(NS(hfm_login=2,hfm_server="Demo",storage_dir=tmp_path)).events()==[]
    other=meta();other["decision_id"]="other";other["strategy"]="pullback_trend"
    index.record(other)
    assert len(_decisions(index.events())[0]["101"])==2


def test_corrupt_index_is_not_silently_ignored(tmp_path):
    index=GuardedDecisionIndex(setup(tmp_path));index.path.write_text("bad")
    with pytest.raises(ValueError):index.events()


@pytest.mark.parametrize("flag",["forced_demo_entry","forced_learning_probe"])
def test_forced_probe_is_not_added_to_autonomous_index(tmp_path,flag):
    index=GuardedDecisionIndex(setup(tmp_path));row=meta();row[flag]=True
    assert not index.record(row) and index.events()==[]
