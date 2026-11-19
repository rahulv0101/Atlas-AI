import json
from pathlib import Path
import shutil
import subprocess
import pytest


def render(payload):
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=Path('atlas_ai/ui/app.js').read_text(encoding='utf-8')
    helper=source[source.index('function decisionExecutionDisplay('):source.index('function renderDecisionAnalysis(')]
    result=subprocess.run([node,'-'],input=helper+'\nconsole.log(JSON.stringify(decisionExecutionDisplay('+json.dumps(payload)+')));',
        text=True,encoding='utf-8',capture_output=True,check=True,timeout=15)
    return json.loads(result.stdout)


def test_high_analysis_score_cannot_override_failed_timing_in_display():
    result=render({'action':'blocked','timing_discipline':{'passed':False,'hard_block':True},
        'decision_analysis':{'confidence_score':85,'recommended_action':'guarded_sell',
            'decision_protocol':{'act':{'execution_request_eligible':True}}}})
    assert result['action']=='WAIT — timing confirmation'
    assert result['execution']=='blocked' and result['timing']=='blocked'


def test_passed_timing_is_not_execution_approval():
    result=render({'timing_discipline':{'passed':True},'decision_analysis':{'recommended_action':'guarded_sell'}})
    assert result['timing']=='passed'
    assert result['execution']=='not confirmed; remaining execution checks required'


def test_non_timing_rejection_is_not_mislabelled_as_timing():
    result=render({'action':'blocked','timing_discipline':{'passed':True}})
    assert result['action']=='WAIT — execution blocked'
    assert result['timing']=='passed' and result['execution']=='blocked'


def test_missing_runtime_evidence_is_not_a_pass():
    result=render({})
    assert result['timing']=='not confirmed'
    assert result['execution'].startswith('not confirmed')


def test_opposing_analysis_never_displays_as_selected_trade_ready():
    result=render({'chosen':{'side':'sell'},'timing_discipline':{'passed':True},
        'decision_analysis':{'final_trade_bias':'buy','recommended_action':'guarded_buy'}})
    assert result['action']=='WAIT — direction conflict'
    assert result['execution']=='not confirmed; selected signal conflicts with analysis'


def test_legacy_m1_recommendation_is_displayed_with_actual_entry_timeframe():
    result=render({'timeframe':'M5','decision_analysis':{'recommended_action':'wait_for_m1_confirmation_sell'}})
    assert result['action']=='Wait for M5 confirmation (SELL)'
    assert result['analysisRecommendation']==result['action']


def test_missing_timeframe_does_not_invent_m1_and_runtime_block_wins():
    result=render({'action':'blocked','timing_discipline':{'passed':False},'decision_analysis':{'recommended_action':'wait_for_m1_confirmation_sell'}})
    assert 'ENTRY TIMEFRAME' in result['analysisRecommendation']
    assert 'timing confirmation' in result['action']
