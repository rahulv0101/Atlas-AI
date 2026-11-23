from datetime import datetime,timezone
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from tools import backtest_today_learning as module


def test_archived_memory_must_be_observed_before_decision(monkeypatch,tmp_path):
    rows=[{'id':0,'decision_at':'2026-11-23T07:55:00Z'}, {'id':1,'decision_at':'2026-11-23T07:59:00Z'}]
    monkeypatch.setattr(module,'index_rows',lambda _:rows)
    records={0:{'observed_at':'2026-11-23T07:56:00Z'},1:{'observed_at':'2026-11-23T08:02:00Z'}}
    monkeypatch.setattr(module,'read_record',lambda _,row:records[row['id']])
    monkeypatch.setattr(module,'load_saved',lambda _,record,name:{'chosen_observation':record['observed_at']})
    for row in rows:row['record_id']=str(row['id'])
    state,receipt=module.archived_before(tmp_path,module.pd.Timestamp('2026-11-23T08:00Z'))
    assert receipt['record_id']=='0' and state['chosen_observation']=='2026-11-23T07:56:00Z'


def test_probe_does_not_mutate_candidate_or_treat_earlier_haircut_as_final_veto():
    trader=SimpleNamespace(settings=SimpleNamespace(),
        _loss_pattern_lesson_adjustment=Mock(return_value=(.5,{'applied':True})),
        _online_learning_adjustment=Mock(return_value=(.95,{'applied':False})),
        _load_loss_memory=lambda:{},_loss_pattern_penalty_detail=lambda *a:{'penalty':.1},
        _recent_side_penalty_detail=lambda *a,**k:{'penalty':0},
        _loss_learning_recovery_evidence=lambda **k:{'reduction_factor':1},
        _loss_pattern_block_detail=lambda *a:{'blocked':False})
    status={'chosen':{'strategy':'ema_crossover','side':'buy','confidence':.95,'stop_loss_points':100,'take_profit_points':150},
            'min_confidence_threshold':.8,'context_snapshot':{'session':'london'}}
    original=deepcopy(status)
    result=module.learning_probe(trader,status,datetime(2026,11,23,8,tzinfo=timezone.utc))
    assert result['post_conviction_confidence']==.855
    assert not result['learning_would_block'] and result['stop_loss_points']==100
    assert result['lesson_probe_is_diagnostic_on_M5'] and not result['lesson_adjustment_used_by_entry_timing_path']
    assert status==original


def test_current_m5_entry_lesson_and_pattern_block_are_not_active_guards():
    from atlas_ai.trader import AtlasTrader
    from atlas_ai.config.settings import Settings
    from atlas_ai.models import TradeSignal
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=Settings(0,'','',timeframe='M5')
    trader._loss_pattern_lesson_adjustment=Mock(side_effect=AssertionError('M5 must not claim this path ran'))
    signal=TradeSignal('ema_crossover','buy',.95,100,150)
    assert trader._apply_entry_timing_learning(signal,{}) is signal
    detail=trader._loss_pattern_block_detail('buy',{'recent_outcomes':[{'side':'buy','outcome':'loss'}]*10},
        datetime(2026,11,23,8,tzinfo=timezone.utc))
    assert not detail['blocked']
