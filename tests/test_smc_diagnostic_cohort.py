from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
from tools import smc_diagnostic_cohort as tool
from tools.learn_candidate_ranker import save_signed


def registry(tmp_path):
    now=datetime.now(timezone.utc);d=tmp_path/'model';source=d/'frozen_source'
    sources={}
    for name in ['atlas_ai/strategies/smc_h1_research.py','tools/smc_validation.py']:
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# pinned')
        sources[name]=tool.digest(p)
    m={'model':'smc_h1_event_retest_v6','broker_eligible':False,'orders_sent':0,
       'deadline':(now+timedelta(days=1)).isoformat(),'account_scope':'scope','source_hashes':sources}
    save_signed(d,'manifest',m)
    r={'schema':'atlas_smc_diagnostic_cohort_v1','broker_eligible':False,'orders_sent':0,'auto_promotion':False,
       'source_root':str(source),'runner_sha256':tool.digest(tool.__file__),'deadline':m['deadline'],'account_scope':'scope',
       'models':{m['model']:{'run_dir':str(d),'manifest_sha256':tool.digest(d/'manifest.json')}}}
    save_signed(tmp_path,'smc_h1_diagnostic_active',r)
    return tmp_path/'smc_h1_diagnostic_active.json',r,now


def test_supervisor_uses_one_bounded_read_only_process(tmp_path):
    path,r,now=registry(tmp_path);start=Mock(return_value=SimpleNamespace(pid=10))
    assert tool.ensure(tmp_path,{},can_start=False,now=now,start=start)['state']=='waiting_for_backend_and_operator'
    start.assert_not_called()
    state={}
    assert tool.ensure(tmp_path,state,can_start=True,now=now,start=start)['state']=='smc_h1_diagnostic_started'
    command=start.call_args.args[0]
    assert command[-2:]==['--registry',str(path)]
    assert start.call_args.kwargs['env']['STORAGE_DIR']==str(tmp_path.resolve())
    state['smc_h1_diagnostic_starts']=[now.timestamp()]*3
    assert tool.ensure(tmp_path,state,can_start=True,now=now,start=start)['state']=='restart_budget_exhausted_review_required'
    assert tool.ensure(tmp_path,{},can_start=True,now=now+timedelta(days=2),start=start)['state']=='deadline_reached'


def test_source_or_authority_changes_fail_closed(tmp_path):
    path,r,now=registry(tmp_path)
    assert tool.validate_registry(path,tmp_path)==r
    p=__import__('pathlib').Path(r['source_root'])/'atlas_ai/strategies/smc_h1_research.py'
    p.write_text('# changed')
    with pytest.raises(ValueError,match='frozen_model_source_changed'):tool.validate_registry(path,tmp_path)
    p.write_text('# pinned');r['broker_eligible']=True;save_signed(tmp_path,'smc_h1_diagnostic_active',r)
    with pytest.raises(ValueError,match='diagnostic_boundary_changed'):tool.validate_registry(path,tmp_path)


def test_new_strategy_answers_separate_paper_from_broker_trades():
    from atlas_ai.research_status import research_answer
    p={'h1_smc_diagnostics':{'stale':False,'models':{'h1_event':{'paper_trades':2}},'historically_qualified':[]}}
    typed=research_answer(p,'new strategies');voice=research_answer(p,'new strategies',voice=True)
    assert '2 simulated cases' in typed and 'no broker authority' in typed
    assert 'no broker authority' in voice and len(voice)<len(typed)
    from atlas_ai.brain.intent import classify_intent_candidates
    for question in ['How are the new strategies doing?','How is H1 SMC research doing?']:
        assert classify_intent_candidates(question)[0].name=='research_progress'
