import math
from copy import deepcopy
import pandas as pd
import pytest
from test_smc_pullback import pullback,NOW
from atlas_ai.strategies.smc_framework import evaluate,NAME
from atlas_ai.strategies.smc_retest import evaluate as reversal


def continuation(side='buy'):
    _,c,_=pullback()
    prices=[100+i*.15+math.sin(i*math.pi/4) for i in range(60)]
    rows=[dict(open=p-.1,high=p+.4,low=p-.4,close=p) for p in prices]
    rows[-1].update(open=prices[-1]+.4,high=prices[-1]+.6)
    rows[-1].update(open=109.,high=109.3,low=108.2,close=108.5)
    rows += [dict(open=110.,high=114.5,low=109.8,close=114.),
        dict(open=114.2,high=114.5,low=113.5,close=114.1),
        dict(open=112.,high=113.2,low=111.8,close=113.)]
    f=pd.DataFrame(rows);f['time']=pd.date_range(end='2026-11-13T11:55:00Z',periods=len(f),freq='5min')
    c['evidence']['H1'].update(recent_low=104.,recent_high=128.,recent_closes=[118.,117.,116.,115.,114.,113.])
    q={'bid':112.98,'ask':113.02,'point':.01,'at':NOW.isoformat()}
    if side=='sell':
        old=f.copy();f['open']=220-old.open;f['close']=220-old.close;f['high']=220-old.low;f['low']=220-old.high
        for tf,row in c['evidence'].items():
            row['recent_low'],row['recent_high']=220-row['recent_high'],220-row['recent_low']
            if 'recent_closes' in row:row['recent_closes']=[220-v for v in row['recent_closes']]
        c['details']={tf:('sell' if x=='buy' else 'buy' if x=='sell' else x) for tf,x in c['details'].items()}
        q['bid'],q['ask']=220-q['ask'],220-q['bid']
    return f,c,q


@pytest.mark.parametrize('side',['buy','sell'])
def test_continuation_can_enter_after_BOS_without_inventing_a_liquidity_sweep(side):
    f,c,q=continuation(side);before=f.copy();ctx=deepcopy(c)
    assert reversal(f,c,q,NOW)['candidate'] is None
    r=evaluate(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['family']=='BOS_continuation' and r['candidate']['side']==side
    assert r['candidate']['strategy']==NAME and 'sweep' not in r
    assert r['structure_shift']['prior_structure']==side and r['reward_risk_before_fees_slippage']>=2
    assert not r['broker_eligible'];pd.testing.assert_frame_equal(f,before);assert c==ctx


@pytest.mark.parametrize('side',['buy','sell'])
def test_existing_complete_sweep_setup_keeps_priority(side):
    f,c,q=pullback(side);old=reversal(f,c,q,NOW);r=evaluate(f,c,q,NOW)
    assert r['family']=='sweep_reversal' and r['candidate'] is not None
    assert r['candidate']['stop_loss_points']==old['candidate']['stop_loss_points']


def test_no_BOS_missing_context_or_future_candles_cannot_manufacture_an_entry():
    f,c,q=continuation();f.loc[60,'close']=110.01
    assert evaluate(f,c,q,NOW)['candidate'] is None
    f,c,q=continuation();c['details']['H4']='sell'
    assert evaluate(f,c,q,NOW)['candidate'] is None
    f,c,q=continuation();baseline=evaluate(f,c,q,NOW)
    extra=f.tail(1).copy();extra['time']=pd.Timestamp('2026-11-13T12:00:00Z');extra['high']=9999.;extra['low']=1.;extra['close']=2.
    assert evaluate(pd.concat([f,extra],ignore_index=True),c,q,NOW)==baseline


def test_new_family_does_not_bypass_minimum_target_or_execution_boundary():
    f,c,q=continuation();c['evidence']['M15']['recent_high']=113.5
    r=evaluate(f,c,q,NOW)
    assert r['candidate'] is None
    from atlas_ai.strategies.inventory import base_inventory
    from tools.smc_validation import evaluator_for
    assert NAME not in {s.name for s in base_inventory('M5',top_down=True)}
    assert evaluator_for({'model':NAME}).__module__=='atlas_ai.strategies.smc_framework'


def test_reaction_zone_is_anchored_to_the_pullback_not_the_confirmed_entry_price():
    f,c,q=continuation();c['evidence']['H1'].update(recent_low=100.,recent_high=124.)
    assert q['ask']>112. and q['ask']>110.
    assert reversal(f,c,q,NOW)['candidate'] is None
    r=evaluate(f,c,q,NOW)
    assert r['candidate'] is not None,r
    assert r['setup_context']['reaction_reference']['price']<112.


def test_fast_confirmed_swings_match_original_arithmetic_on_realistic_closed_inputs():
    import random
    from atlas_ai.strategies.smc_composite import structure
    rng=random.Random(42)
    for _ in range(25):
        values=[100.+rng.randrange(-20,21)*.1 for i in range(80)]
        f=pd.DataFrame({'high':[v+.3 for v in values],'low':[v-.3 for v in values]})
        highs=[];lows=[]
        for i in range(2,len(f)-2):
            neighbors=f.iloc[i-2:i+3].drop(f.index[i])
            if f.high.iloc[i]>neighbors.high.max():highs.append(float(f.high.iloc[i]))
            if f.low.iloc[i]<neighbors.low.min():lows.append(float(f.low.iloc[i]))
        bias='unknown'
        if len(highs)>=2 and len(lows)>=2:
            bias='buy' if highs[-1]>highs[-2] and lows[-1]>lows[-2] else 'sell' if highs[-1]<highs[-2] and lows[-1]<lows[-2] else 'mixed'
        assert structure(f)=={'bias':bias,'last_swing_high':highs[-1] if highs else None,'last_swing_low':lows[-1] if lows else None}
