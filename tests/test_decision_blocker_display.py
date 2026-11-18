import json
from pathlib import Path
import shutil
import subprocess
import pytest


def render(payload):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    source = Path('atlas_ai/ui/app.js').read_text(encoding='utf-8')
    helper = source[source.index('function decisionBlockerDisplay('):source.index('function renderDecisionAnalysis(')]
    result = subprocess.run([node, '-'], input=helper+'\nconsole.log(JSON.stringify(decisionBlockerDisplay('+json.dumps(payload)+')));',
                            text=True, capture_output=True, check=True, timeout=15)
    return json.loads(result.stdout)


def test_empty_hard_list_still_exposes_quality_shortfall_and_actual_timing_rejection():
    result = render({'action':'blocked','message':'Timing discipline blocked trade: wait for a pullback.',
        'timing_discipline':{'hard_block':True,'detail':'M5 momentum confirmation missing.'},
        'decision_analysis':{'hard_blockers':[],'recommended_action':'hold','entry_quality':'avoid',
            'top_blockers':[{'detail':'Confluence below threshold','actual':65,'target':85}]}})
    assert result['reasons'] == ['Timing discipline blocked trade: wait for a pullback.',
        'M5 momentum confirmation missing.', 'Setup quality: Confluence below threshold (65 / 85)']


@pytest.mark.parametrize('analysis,expected', [
    ({},'Decision evidence unavailable'),
    ({'recommended_action':'hold'},'Entry conditions not met; execution is not cleared'),
    ({'recommended_action':'guarded_sell','entry_quality':'good'},'No listed analysis blockers; execution checks still required')])
def test_empty_list_never_implies_execution_authority(analysis, expected):
    result = render({'decision_analysis':analysis})
    assert result['reasons'] == [] and result['emptyLabel'] == expected


def test_passed_timing_does_not_resurrect_old_rejection_and_hard_reasons_remain():
    result = render({'action':'hold','message':'Old unrelated message',
        'timing_discipline':{'hard_block':False,'detail':'Not a current blocker'},
        'decision_analysis':{'hard_blockers':['spread_liquidity_too_poor']}})
    assert result['reasons'] == ['spread liquidity too poor']


def test_direction_and_location_conflicts_are_explained_without_picking_a_winner():
    result=render({'chosen':{'side':'sell'},'decision_analysis':{'final_trade_bias':'buy'},
        'timing_discipline':{'observed':{'visual_watch_used':True,'location':'pullback','visual_location':'mid_range'}}})
    assert any('selected strategy SELL; analysis BUY' in r for r in result['reasons'])
    assert any('candles pullback; visual viewport mid_range' in r for r in result['reasons'])
    assert any('alignment is unverified' in r for r in result['reasons'])
