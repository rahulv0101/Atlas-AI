from datetime import datetime,timezone
from unittest.mock import Mock
from tools import supervise_settled_forecasts as module


def test_operator_sleep_prevents_resume_and_restart_budget_is_bounded(monkeypatch,tmp_path):
    now=datetime.now(timezone.utc);start=Mock(return_value={'state':'settled_collector_started'})
    evaluate=Mock(return_value={'state':'blocked_review_required'})
    monkeypatch.setattr(module,'resume_collector',start)
    monkeypatch.setattr(module,'resume_evaluator',evaluate)
    state={}
    module.ensure(tmp_path,state,can_start=False,now=now)
    start.assert_not_called();evaluate.assert_not_called()
    for _ in range(3):module.ensure(tmp_path,state,can_start=True,now=now)
    result=module.ensure(tmp_path,state,can_start=True,now=now)
    assert start.call_count==3
    assert result['collector']['state']=='restart_budget_exhausted_review_required'
    assert state['settled_starts']['evaluator']==[]


def test_existing_workers_do_not_consume_restart_budget(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'resume_collector',lambda _: {'state':'existing_settled_collector_running'})
    monkeypatch.setattr(module,'resume_evaluator',lambda _: {'state':'existing_evaluator_running'})
    state={}
    for _ in range(4):module.ensure(tmp_path,state,can_start=True,now=datetime.now(timezone.utc))
    assert state['settled_starts']=={'collector':[],'evaluator':[]}
