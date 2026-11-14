from copy import deepcopy
import pandas as pd
import pytest

from tools.m5_stop_research import corrected_candidates,disjoint,review


def fixture():
    frame=pd.DataFrame({'time':pd.date_range('2026-04-01',periods=35,freq='5min'),
        'open':100.,'high':102.,'low':98.,'close':100.})
    rows=[{'index':20,'available_at':'2026-04-01T01:45:00+00:00','higher_context':{'bias':'buy'},
           'signals':[{'strategy':'ema_crossover','side':'buy','confidence':.7,'stop_loss_points':100.,'take_profit_points':150.}]}]
    return frame,rows


def test_unit_correction_changes_only_distances_and_excludes_future_bars():
    frame,rows=fixture();before=deepcopy(rows)
    result=corrected_candidates(frame,rows,.01)
    signal=result[0]['signals'][0]
    assert signal['stop_loss_points']==800 and signal['take_profit_points']==1200
    assert signal['confidence']==.7 and signal['side']=='buy'
    assert result[0]['available_at']==rows[0]['available_at'] and result[0]['higher_context']==rows[0]['higher_context']
    assert rows==before
    frame.loc[21:,'high']=100000
    assert corrected_candidates(frame,rows,.01)==result


def test_invalid_timing_cannot_be_corrected_as_a_valid_prediction():
    frame,rows=fixture();rows[0]['available_at']='2026-04-01T01:40:00+00:00'
    with pytest.raises(ValueError,match='candidate_time_changed'):corrected_candidates(frame,rows,.01)


def test_validation_must_be_separate_and_ordered():
    ts=lambda x:pd.Timestamp(x,tz='UTC')
    assert disjoint(ts('2026-04-01'),ts('2026-05-01'),ts('2026-10-15'),ts('2026-11-14'))
    assert not disjoint(ts('2026-10-01'),ts('2026-11-01'),ts('2026-10-15'),ts('2026-11-14'))
    with pytest.raises(ValueError,match='ordered'):disjoint(ts('2026-05-01'),ts('2026-04-01'),ts('2026-10-15'),ts('2026-11-14'))


def test_no_trades_is_not_successful_risk_adaptation():
    result=review({'trade_list':[],'trades':0,'wins':0,'mean_net_r':None,'profit_factor':None,'max_drawdown_r':0})
    assert not result['passed'] and 'fewer_than_30_trades' in result['reasons']
    assert 'no_positive_mean_net_R' in result['reasons']


@pytest.mark.parametrize('stale',[False,True])
def test_dashboard_cannot_present_zero_trades_as_success(stale):
    import json
    from pathlib import Path
    import shutil
    import subprocess
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=(Path(__file__).resolve().parents[1]/'atlas_ai/ui/app.js').read_text(encoding='utf-8')
    render=source[source.index('function renderResearchProgress('):source.index('function renderLearningLoop(')]
    payload={'research_progress':{'stop_distance_research':{'stale':stale,'state':'completed_research_only',
        'corrected':{'trades':0,'review':{'passed':False}}}}}
    script='const values={};function setText(k,v){values[k]=v;}\n'+render+'\nrenderResearchProgress('+json.dumps(payload)+');process.stdout.write(values["research-stop-study"]);'
    text=subprocess.run([node,'-'],input=script,text=True,capture_output=True,check=True,timeout=15).stdout
    if stale:assert text=='Current study evidence unavailable'
    else:assert '0 separate-period' in text and 'review failed' in text and 'Live trading unchanged' in text


def test_proposal_freezes_sources_and_display_pointer_without_broker_or_live_learning(tmp_path,monkeypatch):
    import json
    from unittest.mock import Mock
    from atlas_ai.config.settings import Settings
    from tools import m5_stop_research as study
    from tools.learn_candidate_ranker import save_signed,signed,digest
    from tools.guarded_research_audit import safe_settings
    cfg=Settings(1,'secret','demo',storage_dir=str(tmp_path),timeframe='M5',top_down_confluence_enabled=True)
    monkeypatch.setattr(study,'load_settings',lambda:cfg)
    forbidden=Mock(side_effect=AssertionError('Proposal freeze must be offline'))
    monkeypatch.setattr(study.mt5,'initialize',forbidden);monkeypatch.setattr(study.mt5,'order_send',forbidden)
    source=tmp_path/'source';source.mkdir()
    manifest={'settings':json.loads(json.dumps(safe_settings(cfg))),
        'source_hashes':{name:digest(study.ROOT/name) for name in study.POLICY_SOURCES},
        'start_utc':'2026-10-15T00:00:00Z','end_utc':'2026-11-14T00:00:00Z',
        'limits':{},'spec':{},'cost_evidence':{}}
    save_signed(source,'manifest',manifest)
    save_signed(source,'report',{'state':'completed_research_only','manifest_sha256':digest(source/'manifest.json')})
    output=tmp_path/'proposal'
    result=study.initialize(output,source,pd.Timestamp('2026-04-01T00:00:00Z'),pd.Timestamp('2026-05-01T00:00:00Z'))
    assert result['broker_eligible'] is False and result['auto_promotion'] is False
    receipt=signed(output,'source_receipt')
    assert receipt['protocol_sha256']==digest(output/'protocol.json')
    assert receipt['frozen_source_hashes']['tools/m5_stop_research.py']==digest(study.ROOT/'tools/m5_stop_research.py')
    assert json.loads((tmp_path/'m5_stop_research_active.json').read_text())=={'run_dir':str(output)}
    assert not (tmp_path/'learning_state.json').exists() and not (tmp_path/'smc_validation_active.json').exists()
    forbidden.assert_not_called()
