from datetime import datetime,timezone
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import save_signed
from atlas_ai.research_status import load_research_progress,research_answer


def test_fresh_forecasts_are_never_reported_as_trade_outcomes(tmp_path):
    directory=tmp_path/'collector';directory.mkdir()
    save_signed(directory,'protocol',{'broker_eligible':False,'auto_promotion':False,'orders_sent':0})
    atomic_json(directory/'status.json',{'state':'collecting_settled_candidate_forecasts','forecasts':1,'checked_at':datetime.now(timezone.utc).isoformat()})
    atomic_json(tmp_path/'settled_m5_forward_active.json',{'run_dir':str(directory)})
    result=load_research_progress(tmp_path)['settled_m5_forecasts']
    assert result['forecasts']==1 and not result['stale']
    assert not result['broker_eligible'] and not result['trade_outcomes_verified']
    assert 'not trades' in research_answer({'settled_m5_forecasts':result},'settled collector')


def test_unexpected_authority_is_not_accepted_as_observation(tmp_path):
    directory=tmp_path/'collector';directory.mkdir()
    save_signed(directory,'protocol',{'broker_eligible':True,'auto_promotion':False,'orders_sent':0})
    atomic_json(tmp_path/'settled_m5_forward_active.json',{'run_dir':str(directory)})
    assert load_research_progress(tmp_path)['settled_m5_forecasts']['stale']
