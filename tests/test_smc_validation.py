from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
import pandas as pd
import pytest
from atlas_ai.config.settings import Settings
from atlas_ai.testing.smc_validation import HistoricalFeed,advance_ticks,stage
from atlas_ai.testing.historical_broker import BrokerSpec

NOW=pd.Timestamp('2026-11-13T12:00:00Z')
SPEC=BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2,roundtrip_fee_per_lot=5.)
CFG=Settings(0,'','',timeframe='M5')


def position(side='buy'):
    sign=1 if side=='buy' else -1
    return {'side':side,'entry_at':NOW.isoformat(),'entry_price':100.,'risk_price':1.,
        'initial_risk_cash':1.,'stop':100.-sign,'target':100.+sign*2,'best_r':0.,
        'entry_tick_msc':1000,'last_tick_msc':1000,'last_tick_keys':[],'evidence_complete':True}


def tick(seq,bid,ask,seconds=1):
    return {'time_msc':seq,'bid':bid,'ask':ask,'utc':(NOW+pd.Timedelta(seconds=seconds)).isoformat()}


@pytest.mark.parametrize('side,bid,ask',[('buy',102.,102.1),('sell',97.9,98.)])
def test_tick_exit_uses_correct_quote_side_and_subtracts_fee_slippage(side,bid,ask):
    p=position(side);original=deepcopy(p)
    pending,result=advance_ticks(p,[tick(2000,bid,ask)],SPEC,CFG,NOW+pd.Timedelta(seconds=2))
    assert pending is None and result['exit_reason']=='take_profit'
    assert result['net_cash']==pytest.approx(2.-.03-.05)
    assert not result['broker_fill'] and p==original


def test_duplicate_tick_time_does_not_erase_a_different_quote_at_same_millisecond():
    p=position()
    p,result=advance_ticks(p,[tick(2000,100.1,100.2)],SPEC,CFG,NOW+pd.Timedelta(seconds=2))
    p,result=advance_ticks(p,[tick(2000,100.1,100.2),tick(2000,98.9,99.)],SPEC,CFG,NOW+pd.Timedelta(seconds=2))
    assert result['exit_reason']=='stop_loss'


def test_future_pre_entry_and_missing_tick_evidence_do_not_prove_a_trade():
    p=position()
    q,r=advance_ticks(p,[tick(2000,102.,102.1,seconds=60)],SPEC,CFG,NOW)
    assert r is None and q==p
    q,r=advance_ticks(p,[tick(2000,102.,102.1,seconds=-1)],SPEC,CFG,NOW)
    assert r is None and q==p
    q,r=advance_ticks(p,[tick(2000,102.,102.1,seconds=180)],SPEC,CFG,NOW+pd.Timedelta(minutes=4))
    assert not r['evidence_complete']


def test_unordered_ticks_fail_instead_of_silently_losing_stop_events():
    with pytest.raises(ValueError,match='unordered'):
        advance_ticks(position(),[tick(3000,100.,100.1),tick(2000,99.,99.1)],SPEC,CFG,NOW+pd.Timedelta(minutes=1))


def test_historical_feed_never_exposes_future_higher_timeframe_candles():
    f=pd.DataFrame({'time':pd.date_range('2026-11-10',periods=90,freq='h',tz='UTC'),'close':range(90)})
    feed=HistoricalFeed({'H1':f});feed.now=pd.Timestamp('2026-11-11T12:00:00Z')
    result=feed.get_rates_for_timeframe('H1')
    assert result.time.max()==feed.now
    assert not (result.time>feed.now).any()


def test_empty_or_tiny_profitable_samples_cannot_pass_review():
    assert not stage([])['review_passed']
    assert not stage([{'entry_at':'2026-11-13T12:00:00Z','net_r':2.,'net_cash':2.}]*2)['review_passed']


def test_paper_supervision_respects_sleep_deadline_and_existing_worker(tmp_path):
    from unittest.mock import Mock
    from tools import smc_validation as tool
    from tools.learn_candidate_ranker import save_signed
    from atlas_ai.atomic_files import atomic_json
    from atlas_ai.learning.observation_checkpoint import observation_lock
    run=tmp_path/'run';run.mkdir()
    save_signed(run,'manifest',{'schema':'atlas_smc_validation_v1','broker_eligible':False,'deadline':(NOW+pd.Timedelta(days=1)).isoformat()})
    atomic_json(tmp_path/'smc_validation_active.json',{'run_dir':str(run)})
    launch=Mock(side_effect=AssertionError('must not launch'))
    assert tool.ensure(tmp_path,{},can_start=False,now=NOW.to_pydatetime(),start=launch)['state']=='waiting_for_backend_and_operator'
    with observation_lock(run/'watch.lock'):
        assert tool.ensure(tmp_path,{},can_start=True,now=NOW.to_pydatetime(),start=launch)['state']=='existing_smc_paper_observer_running'
    assert tool.ensure(tmp_path,{},can_start=True,now=(NOW+pd.Timedelta(days=2)).to_pydatetime(),start=launch)['state']=='deadline_reached'


def test_paper_progress_rejects_escaping_paths_and_changed_manifest(tmp_path):
    from atlas_ai.atomic_files import atomic_json
    from atlas_ai.testing.smc_validation import paper_progress
    atomic_json(tmp_path/'smc_validation_active.json',{'run_dir':str(tmp_path.parent)})
    assert paper_progress(tmp_path)['state']=='unavailable_review_required'
    run=tmp_path/'run';run.mkdir()
    atomic_json(tmp_path/'smc_validation_active.json',{'run_dir':str(run)})
    (run/'manifest.json').write_text('{}');(run/'manifest.sha256').write_text('wrong')
    assert paper_progress(tmp_path)['state']=='unavailable_review_required'


def test_supervised_worker_uses_frozen_source_and_authoritative_storage(tmp_path):
    from unittest.mock import Mock
    from tools import smc_validation as tool
    from tools.learn_candidate_ranker import save_signed
    from atlas_ai.atomic_files import atomic_json
    from atlas_ai.testing.smc_validation import METHOD
    run=tmp_path/'run';run.mkdir()
    save_signed(run,'manifest',{'schema':'atlas_smc_validation_v1','method':METHOD,'source_hashes':{},
        'broker_eligible':False,'orders_sent':0,'deadline':(NOW+pd.Timedelta(days=1)).isoformat()})
    atomic_json(tmp_path/'smc_validation_active.json',{'run_dir':str(run)})
    launch=Mock(return_value=type('Child',(),{'pid':123})())
    result=tool.ensure(tmp_path,{},can_start=True,now=NOW.to_pydatetime(),start=launch)
    assert result['state']=='smc_paper_observer_launched'
    assert launch.call_args.kwargs['env']['STORAGE_DIR']==str(tmp_path.resolve())
    assert launch.call_args.kwargs['cwd']==run/'frozen_source'
    assert 'frozen_source' in launch.call_args.args[0][1]


def test_smc_progress_answer_keeps_paper_and_broker_evidence_separate():
    from atlas_ai.research_status import research_answer
    from atlas_ai.brain.intent import classify_intent_candidates
    assert classify_intent_candidates('How is the SMC validation doing?')[0].name=='research_progress'
    p={'smc_validation':{'stale':False,'first_stage_trades':4,'validation_stage_trades':0,'pending':True}}
    for voice in [True,False]:
        text=research_answer(p,'How is SMC validation doing?',voice=voice)
        assert '4/30' in text and 'no broker authority' in text
