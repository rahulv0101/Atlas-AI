from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pandas as pd
import pytest
from tools import entry_forecast_observer as module
from tools.learn_candidate_ranker import save_signed,digest


def test_closed_bar_append_never_revises_or_backfills_past_inputs():
    rows=[{'time':'2026-11-26T08:00:00Z','close':100.},{'time':'2026-11-26T08:10:00Z','close':101.}]
    original=deepcopy(rows)
    assert len(module.merge_closed(rows,[rows[-1],{'time':'2026-11-26T08:15:00Z','close':102.}]))==3
    assert rows==original
    with pytest.raises(ValueError):module.merge_closed(rows,[{'time':rows[0]['time'],'close':999.}])
    with pytest.raises(ValueError):module.merge_closed(rows,[{'time':'2026-11-26T08:05:00Z','close':100.}])


def test_retrospective_late_and_future_predictions_cannot_count_as_timely():
    now=pd.Timestamp('2026-11-26T09:00Z');start=now-pd.Timedelta(minutes=5)
    assert module.timely(now,now+pd.Timedelta(seconds=120),start)
    assert not module.timely(now,now+pd.Timedelta(seconds=121),start)
    assert not module.timely(now,now-pd.Timedelta(seconds=1),start)
    assert not module.timely(now,now+pd.Timedelta(seconds=1),now+pd.Timedelta(minutes=5))


def test_native_final_row_is_not_closed_merely_because_wall_clock_advanced():
    f=pd.DataFrame({'time':pd.date_range('2026-11-26T10:00Z',periods=3,freq='5min'),'close':[100.,101.,102.]})
    now=pd.Timestamp('2026-11-26T10:20Z')
    closed=module.proven_closed_bars(f,5,now)
    assert list(closed.close)==[100.,101.]
    # Only the appearance of a following bar confirms the previous final row.
    f.loc[3]=[pd.Timestamp('2026-11-26T10:15Z'),103.]
    assert list(module.proven_closed_bars(f,5,now).close)==[100.,101.,102.]


def fixture(tmp_path):
    directory=tmp_path/'entry';directory.mkdir();now=datetime.now(timezone.utc)
    save_signed(directory,'plan',{'deadline':(now+timedelta(days=1)).isoformat()})
    (tmp_path/'entry_forecast_active.json').write_text(json.dumps({'run_dir':str(directory)}))
    return directory,now


def test_supervision_respects_standby_deadline_and_blocked_evidence(tmp_path):
    directory,now=fixture(tmp_path);launch=Mock(side_effect=AssertionError('cannot start'))
    assert module.ensure(tmp_path,{},can_start=False,now=now,start=launch)['state']=='waiting_for_backend_and_operator'
    assert module.ensure(tmp_path,{},can_start=True,now=now+timedelta(days=2),start=launch)['state']=='deadline_reached'
    (directory/'status.json').write_text(json.dumps({'state':'blocked_evidence_review_required'}))
    assert module.ensure(tmp_path,{},can_start=True,now=now,start=launch)['state']=='blocked_evidence_review_required'


def test_forecast_collector_denies_changed_boundary_before_native_reads(tmp_path):
    save_signed(tmp_path,'plan',{'schema':'atlas_entry_forecast_v1','broker_eligible':True,'auto_promotion':False,'orders_sent':0})
    save_signed(tmp_path,'checkpoint',{})
    with pytest.raises(ValueError,match='diagnostic_boundary'):module.once(tmp_path)


def test_repeat_registration_does_not_reset_existing_predictions(tmp_path,monkeypatch):
    directory=tmp_path/'run';directory.mkdir();history=tmp_path/'history';history.mkdir()
    (history/'report.json').write_text('{}')
    cfg=SimpleNamespace(storage_dir=str(tmp_path))
    monkeypatch.setattr(module,'load_settings',lambda:cfg);monkeypatch.setattr(module,'account_scope',lambda cfg:'same')
    save_signed(directory,'plan',{'account_scope':'same','historical_report_sha256':digest(history/'report.json')})
    (tmp_path/'entry_forecast_active.json').write_text(json.dumps({'run_dir':str(directory)}))
    assert module.initialize(history)==directory
    (history/'report.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='no_reset'):module.initialize(history)


def test_actual_collection_records_once_with_no_orders_or_outcome_claims(tmp_path,monkeypatch):
    from atlas_ai.config.settings import Settings
    from tools.guarded_research_audit import safe_settings
    from atlas_ai.learning.observation_checkpoint import account_scope
    from tools.learn_candidate_ranker import signed
    available=pd.Timestamp('2026-11-26T09:00Z');now=available+pd.Timedelta(seconds=30)
    cfg=Settings(1,'','Demo',timeframe='M5',storage_dir=str(tmp_path))
    plan={'schema':'atlas_entry_forecast_v1','broker_eligible':False,'auto_promotion':False,'orders_sent':0,
          'deadline':(now+pd.Timedelta(days=1)).isoformat(),'start':available.isoformat(),
          'account_scope':account_scope(cfg),'broker_timezone':cfg.mt5_server_timezone,
          'settings':safe_settings(cfg),'source_hashes':{},'historical_qualified':False}
    save_signed(tmp_path,'plan',plan)
    save_signed(tmp_path,'checkpoint',{'last_available':None,'bars_evaluated':0,'late_discarded':0,
        'forecasts':{'unchanged_retest':[],'sweep_reclaim':[]},'frame_hash':None,'plan_sha256':digest(tmp_path/'plan.json')})
    def rates(tf,bars):
        end=available if tf=='M5' else available.floor('h')
        return pd.DataFrame({'time':pd.date_range(end=end,periods=bars,freq='5min' if tf=='M5' else 'h'),
                             'open':100.,'high':101.,'low':99.,'close':100.,'spread':20.})
    monkeypatch.setattr(module,'load_settings',lambda:cfg)
    monkeypatch.setattr(module,'MarketDataFeed',lambda cfg:SimpleNamespace(_ensure_initialized=lambda:None,get_rates_for_timeframe=lambda tf,bars:rates(tf,bars)))
    monkeypatch.setattr(module.mt5,'account_info',lambda:SimpleNamespace(login=1,server='Demo',trade_mode=module.mt5.ACCOUNT_TRADE_MODE_DEMO))
    monkeypatch.setattr(module.mt5,'shutdown',lambda:None)
    def generator(*args,**kwargs):return ([{'available_at':available.isoformat(),'signals':[{'side':'buy'}]}],{})
    monkeypatch.setattr(module,'retest_generate',generator);monkeypatch.setattr(module,'sweep_generate',generator)
    result=module.once(tmp_path,clock=lambda:now)
    assert result['forecasts']=={'unchanged_retest':1,'sweep_reclaim':1}
    assert result['orders_sent']==result['qualification_cases']==result['natural_broker_cycles']==0
    repeated=module.once(tmp_path,clock=lambda:now)
    assert repeated['forecasts']==result['forecasts'] and repeated['bars_evaluated']==1
    assert signed(tmp_path,'checkpoint')['forecasts']['sweep_reclaim'][0]['observed_at']==now.isoformat()
