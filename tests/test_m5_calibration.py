from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from atlas_ai.testing.m5_proposal import matched_volatility,calibrate,proposal_candidates,volatility_policy


def minute_frames():
    times=pd.date_range('2026-10-01',periods=4500,freq='min')
    closes=100+np.arange(len(times))*.001+np.sin(np.arange(len(times))*.2)*.1
    one=pd.DataFrame({'time':times,'close':closes})
    five=one.set_index('time').resample('5min').last().reset_index()
    return one,five


def test_paired_volatility_uses_only_closed_matching_windows_and_rejects_gaps():
    one,five=minute_frames();before=matched_volatility(one,five)
    cutoff=pd.Timestamp('2026-10-02T00:00:00Z')
    one.loc[pd.to_datetime(one.time,utc=True)+pd.Timedelta(minutes=1)>cutoff,'close']=99999
    five.loc[pd.to_datetime(five.time,utc=True)+pd.Timedelta(minutes=5)>cutoff,'close']=99999
    after=matched_volatility(one,five)
    pd.testing.assert_frame_equal(before[before.index<=cutoff],after[after.index<=cutoff])
    one,five=minute_frames();gap=pd.Timestamp(one.time.iloc[1000],tz='UTC')
    pairs=matched_volatility(one.drop(index=1000),five)
    assert not ((pairs.index>gap)&(pairs.index<gap+pd.Timedelta(minutes=295))).any()


def test_calibration_is_fixed_without_using_validation_outcomes():
    index=pd.date_range('2026-10-01',periods=4000,freq='5min',tz='UTC')
    pairs=pd.DataFrame({'m1':.02,'m5':.04},index=index)
    start=pd.Timestamp('2026-10-01T00:00Z');split=pd.Timestamp('2026-10-15T00:00Z')
    expected=calibrate(pairs,start,split)
    assert expected['scale']==2 and expected['extreme_pct']==.14 and expected['elevated_pct']==.09
    pairs.loc[pairs.index>=split,'m5']=99999
    assert calibrate(pairs,start,split)==expected
    with pytest.raises(ValueError,match='1000_pairs'):calibrate(pairs.iloc[:10],start,split)
    with pytest.raises(ValueError,match='bounds'):calibrate(pairs.assign(m5=1),start,split)


def test_raw_input_reuse_normalizes_json_lists_and_rejects_changed_windows_or_bytes(tmp_path):
    from tools.m5_calibration_study import load_reused_frames
    from tools.learn_candidate_ranker import save_signed,digest
    p={'development_start':'a','split':'b','validation_end':'c','settings':{'enabled_strategies':('ema_crossover',)}}
    save_signed(tmp_path,'protocol',p)
    frame=pd.DataFrame({'time':pd.date_range('2026-10-01',periods=3,freq='min'),
                        'open':100.,'high':101.,'low':99.,'close':100.,'spread':1})
    inputs={}
    for tf in ['D1','H4','H1','M15','M5','M1']:
        frame.to_csv(tmp_path/(tf+'.csv'),index=False);inputs[tf]=digest(tmp_path/(tf+'.csv'))
    save_signed(tmp_path,'inputs',inputs)
    assert len(load_reused_frames(tmp_path,p))==6
    with pytest.raises(ValueError,match='window_or_settings'):load_reused_frames(tmp_path,{**p,'split':'changed'})
    with (tmp_path/'M1.csv').open('a') as stream:stream.write('\n')
    with pytest.raises(ValueError,match='input_changed'):load_reused_frames(tmp_path,p)


def test_vix_panic_and_price_extremes_still_veto_proposal_entries():
    calibration={'extreme_pct':.14,'elevated_pct':.09}
    assert volatility_policy({'vix_regime':'panic'},{'volatility_pct':.001},calibration)['volatility_action']=='block_new_entries'
    assert volatility_policy({}, {'volatility_pct':.14},calibration)['volatility_action']=='block_new_entries'
    assert volatility_policy({}, {'volatility_pct':.09},calibration)['volatility_action']=='reduce_aggressiveness'
    assert volatility_policy({}, {'volatility_pct':.08},calibration)['volatility_action']=='allow'


def test_closed_M5_confirmation_and_ATR_units_do_not_change_confidence_or_use_future_prices():
    values=np.arange(35)*.1+100
    frame=pd.DataFrame({'time':pd.date_range('2026-10-01',periods=35,freq='5min'),'close':values,
        'open':values-.05,'high':values+.5,'low':values-.5})
    rows=[{'index':20,'available_at':'2026-10-01T01:45:00Z','signals':[
        {'strategy':'ema_crossover','side':side,'confidence':.7,'stop_loss_points':100.,'take_profit_points':150.} for side in ['buy','sell']]}]
    original=deepcopy(rows);result,counts=proposal_candidates(frame,rows,.01)
    assert rows==original and result[0]['signals'][0]['confidence']==.7
    assert result[0]['signals'][0]['stop_loss_points']==pytest.approx(200)
    assert result[0]['signals'][1]['side']=='flat' and counts['closed_candle_confirmation_rejections']==1
    frame.loc[21:,'high']=99999
    assert proposal_candidates(frame,rows,.01)[0]==result


def test_observer_not_configured_or_study_incomplete_cannot_spawn(tmp_path,monkeypatch):
    from tools import m5_demo_observer as observer
    spawn=Mock(side_effect=AssertionError('No unconfigured observer'))
    now=pd.Timestamp('2026-11-16T09:00Z').to_pydatetime()
    assert observer.ensure(tmp_path,{},can_start=True,now=now,start=spawn)['state']=='not_configured'
    from atlas_ai.atomic_files import atomic_json
    directory=tmp_path/'study';directory.mkdir()
    atomic_json(tmp_path/'m5_calibration_active.json',{'run_dir':str(directory)})
    monkeypatch.setattr(observer,'validate',lambda d:{'forward_deadline':'2026-12-01T00:00Z'})
    assert observer.ensure(tmp_path,{},can_start=True,now=now,start=spawn)['state']=='historical_study_running'
    spawn.assert_not_called()


def test_forward_observer_persists_forecast_before_entry_bar_outcomes(tmp_path,monkeypatch):
    from dataclasses import asdict
    from atlas_ai.config.settings import Settings
    from atlas_ai.testing.historical_broker import BrokerSpec
    from tools import m5_demo_observer as observer
    from tools.guarded_research_audit import safe_settings
    from tools.learn_candidate_ranker import save_signed,signed,digest
    now=pd.Timestamp('2026-11-16T09:00:00Z');cfg=Settings(1,'x','demo',timeframe='M5',top_down_confluence_enabled=True,storage_dir=str(tmp_path))
    p={'settings':safe_settings(cfg),'spec':asdict(BrokerSpec(.01,.01,1,1,.01,100,.01,2)),
       'limits':{},'forward_deadline':'2026-12-01T00:00:00Z'}
    save_signed(tmp_path,'protocol',p)
    save_signed(tmp_path,'calibration',{'extreme_pct':.14,'elevated_pct':.09,'protocol_sha256':digest(tmp_path/'protocol.json')})
    save_signed(tmp_path,'report',{'state':'completed_research_only','calibration_sha256':digest(tmp_path/'calibration.json')})
    monkeypatch.setattr(observer,'validate',lambda d,**kw:p)
    monkeypatch.setattr(observer,'load_settings',lambda:cfg)
    monkeypatch.setattr('tools.smc_validation.check_account',lambda s:None)
    times=pd.date_range(end=now.tz_localize(None),periods=350,freq='5min');price=np.arange(350)*.1+100
    frame=pd.DataFrame({'time':times,'open':price-.05,'close':price,'high':price+.5,'low':price-.5,'spread':1})
    monkeypatch.setattr(observer,'fetch_frames',lambda *a,**kw:{'M5':frame.copy()})
    forecast={'index':348,'available_at':now.isoformat(),'signals':[{'strategy':'ema_crossover','side':'buy','confidence':.7,'stop_loss_points':100.,'take_profit_points':150.}]}
    monkeypatch.setattr(observer,'cache_candidates',lambda *a,**kw:([forecast],{},['ema_crossover']))
    def replay_closed(frame,rows,*args,**kwargs):
        assert not rows  # Entry bar is still forming; no outcome prices may be labelled.
        saved=signed(tmp_path,'forward_predictions')
        assert len(saved['lanes']['repaired_baseline'])==1
        return {'trade_list':[],'trades':0,'net_cash':0.,'rejections':{}}
    monkeypatch.setattr(observer,'replay_lane',replay_closed)
    forbidden=Mock(side_effect=AssertionError('No broker execution'))
    monkeypatch.setattr(observer.mt5,'order_send',forbidden)
    r=observer.once(tmp_path,now=now)
    assert r['lanes']['fixed_M5_proposal']['trades']==0
    assert r['lanes']['fixed_M5_proposal']['pending_exit_windows']==1
    assert r['broker_eligible'] is False
    frame.loc[0,'close']=99
    with pytest.raises(ValueError,match='observed_closed_candles_revised'):observer.once(tmp_path,now=now)
    forbidden.assert_not_called()


@pytest.mark.parametrize('stale',[True,False])
def test_calibration_dashboard_never_labels_research_limit_as_live(stale):
    import json,shutil,subprocess
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=(Path(__file__).resolve().parents[1]/'atlas_ai/ui/app.js').read_text(encoding='utf-8')
    render=source[source.index('function renderResearchProgress('):source.index('function renderLearningLoop(')]
    payload={'research_progress':{'m5_calibration':{'stale':stale,'state':'completed_research_only',
        'historical_review_passed':False,'research_thresholds':{'extreme_pct':.1536},
        'demo_observation':{'state':'collecting_prospective_demo_bars','stale':True,'lanes':{'fixed_M5_proposal':{'trades':0}}}}}}
    script='const values={};function setText(k,v){values[k]=v;}\n'+render+'\nrenderResearchProgress('+json.dumps(payload)+');process.stdout.write(values["research-m5-calibration"]);'
    text=subprocess.run([node,'-'],input=script,text=True,capture_output=True,check=True,timeout=15).stdout
    if stale:assert text=='Current calibration evidence unavailable'
    else:assert 'Research-only' in text and 'Live policy unchanged' in text and 'Last known (stale)' in text
