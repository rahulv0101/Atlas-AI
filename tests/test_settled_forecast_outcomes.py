import pandas as pd
import pytest
from tools.evaluate_settled_forecasts import paper_outcome,initialize,once
from tools.learn_candidate_ranker import save_signed,digest,signed
import json

P={'horizon_bars':2,'slippage_points_per_side':0,'additional_cost_r':0}
R={'observed_at':'2026-11-19T10:01Z','scheduled_entry_at':'2026-11-19T10:05Z','quote':{'point':1}}
S={'side':'buy','stop_loss_points':2,'take_profit_points':4,'strategy':'test'}

def bar(o=100,h=101,l=99,c=100,spread=0):return dict(open=o,high=h,low=l,close=c,spread=spread)

def test_buy_target_and_ambiguous_stop_first():
    assert paper_outcome(R,S,{'2026-11-19T10:05Z':bar(h=105)},P)['net_r']==2
    outcome=paper_outcome(R,S,{'2026-11-19T10:05Z':bar(h=105,l=97)},P)
    assert outcome['net_r']==-1 and outcome['exit_reason']=='stop_first_ambiguous'


def test_sell_pays_ask_spread_and_adverse_slippage():
    signal={**S,'side':'sell'}
    result=paper_outcome(R,signal,{'2026-11-19T10:05Z':bar(h=101,l=97,spread=2)},P)
    assert result['net_r']==-1 and result['exit_reason']=='stop'
    result=paper_outcome(R,S,{'2026-11-19T10:05Z':bar(h=106,l=100,spread=1)}, {**P,'slippage_points_per_side':.5})
    assert result['net_r']==pytest.approx(1.75)


def test_pending_missing_gap_and_gap_stop():
    assert paper_outcome(R,S,{},P)['state']=='pending_or_missing_entry'
    assert paper_outcome(R,S,{'2026-11-19T10:05Z':bar()},P)['state']=='pending'
    gap={'2026-11-19T10:05Z':bar(),'2026-11-19T10:15Z':bar()}
    assert paper_outcome(R,S,gap,P)['state']=='incomplete_candle_sequence'
    gap={'2026-11-19T10:05Z':bar(),'2026-11-19T10:10Z':bar(o=95,h=96,l=94,c=95)}
    assert paper_outcome(R,S,gap,P)['net_r']==-2.5


def test_time_exit_and_no_lookahead_or_invalid_geometry():
    bars={'2026-11-19T10:05Z':bar(),'2026-11-19T10:10Z':bar(c=101)}
    assert paper_outcome(R,S,bars,P)['net_r']==.5
    with pytest.raises(ValueError):paper_outcome({**R,'scheduled_entry_at':R['observed_at']},S,bars,P)
    with pytest.raises(ValueError):paper_outcome(R,{**S,'stop_loss_points':float('nan')},bars,P)


def test_integrity_and_pre_registration_cases_not_promoted(tmp_path):
    source=tmp_path/'source';source.mkdir();out=tmp_path/'out'
    save_signed(source,'protocol',{'broker_eligible':False})
    record={**R,'signals':[S]};journal=source/'forecasts.jsonl';journal.write_text(json.dumps(record)+'\n')
    save_signed(source,'checkpoint',{'bars':{'2026-11-19T10:05Z':bar(h=110,l=90)},'journal_sha256':digest(journal)})
    initialize(out,source);status=once(out)
    assert status['resolved_candidates']==1 and status['prospective_resolved_candidates']==0
    assert not status['strategy_qualified'] and not status['broker_eligible']
    journal.write_text('changed')
    assert once(out)['state']=='waiting_for_atomic_source_snapshot'


def test_resume_deduplicates_and_does_not_reset_blocked_evaluator(tmp_path):
    from atlas_ai.atomic_files import atomic_json
    from atlas_ai.learning.observation_checkpoint import observation_lock
    from tools.evaluate_settled_forecasts import resume
    source=tmp_path/'source';source.mkdir();out=tmp_path/'out'
    save_signed(source,'protocol',{'broker_eligible':False,'deadline':'2099-01-01T00:00:00+00:00'})
    initialize(out,source)
    atomic_json(tmp_path/'settled_m5_forward_active.json',{'run_dir':str(source)})
    atomic_json(tmp_path/'settled_m5_outcomes_active.json',{'run_dir':str(out)})
    with observation_lock(out/'evaluator.lock'):
        assert resume(tmp_path)['state']=='existing_evaluator_running'
    atomic_json(out/'status.json',{'state':'blocked_review_required'})
    assert resume(tmp_path)['state']=='blocked_review_required'


def test_shared_answer_never_turns_candidate_outcomes_into_trade_proof():
    from atlas_ai.research_status import research_answer
    progress={'settled_m5_outcomes':{'stale':False,'prospective_resolved_candidates':3,'diagnostic_resolved_candidates':2,'pending_candidates':4}}
    text=research_answer(progress,'settled outcomes')
    assert '3 prospective resolved' in text and '2 pre-registration' in text
    assert 'not independent trades' in text
