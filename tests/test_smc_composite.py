from copy import deepcopy
import math
from types import SimpleNamespace
from unittest.mock import Mock
import pandas as pd
import pytest
from atlas_ai.data.top_down import POLICY,TIMEFRAMES
from atlas_ai.strategies.smc_composite import evaluate,structure,NAME

NOW=pd.Timestamp('2026-11-13T12:00:10Z')


def setup(side='buy'):
    prices=[110-i*.15+math.sin(i*math.pi/4) for i in range(60)]
    rows=[{'open':p+.1,'high':p+.4,'low':p-.4,'close':p} for p in prices]
    prior=pd.DataFrame(rows).tail(20);level=float(prior.low.min())
    rows += [dict(open=level+.5,high=level+.7,low=level-1,close=level+.2),
        dict(open=level+.2,high=106.,low=level+.1,close=105.5),
        dict(open=105.6,high=106.,low=105.,close=105.8),
        dict(open=103.,high=104.6,low=102.8,close=104.4)]
    f=pd.DataFrame(rows)
    f['time']=pd.date_range(end='2026-11-13T11:55:00Z',periods=len(f),freq='5min')
    ctx={'policy':POLICY,'entry_timeframe':'M5','closed_candles_only':True,'bias':'buy',
        'evaluated_at':NOW.isoformat(),'details':{tf:'buy' for tf in TIMEFRAMES},
        'evidence':{tf:{'status':'available','recent_high':130.,'recent_low':90.} for tf in TIMEFRAMES}}
    q={'bid':104.38,'ask':104.42,'point':.01,'at':NOW.isoformat()}
    if side=='sell':
        old=f.copy()
        f['open']=220-old.open;f['close']=220-old.close;f['high']=220-old.low;f['low']=220-old.high
        ctx['bias']='sell';ctx['details']={tf:'sell' for tf in TIMEFRAMES}
        q['bid'],q['ask']=220-q['ask'],220-q['bid']
    return f,ctx,q


@pytest.mark.parametrize('side',['buy','sell'])
def test_complete_sequence_has_structural_protection_and_no_execution_authority(side):
    f,ctx,q=setup(side);before=f.copy(deep=True);context=deepcopy(ctx)
    r=evaluate(f,ctx,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['candidate']['strategy']==NAME and r['candidate']['side']==side
    assert r['structure_shift']['type']=='CHOCH'
    assert r['reward_risk_before_fees_slippage']>=2
    assert r['candidate']['stop_loss_points']>0
    assert not r['broker_eligible'] and not r['auto_promotion'] and r['orders_sent']==0
    pd.testing.assert_frame_equal(f,before);assert ctx==context


@pytest.mark.parametrize('tf',TIMEFRAMES)
def test_each_timeframe_can_block_composite(tf):
    f,c,q=setup();c['details'][tf]='sell'
    assert evaluate(f,c,q,NOW)['candidate'] is None


def test_retest_only_after_sweep_structure_and_gap_confirmation():
    f,c,q=setup()
    for length in [60,61,62,63]:
        assert evaluate(f.iloc[:length],c,q,NOW)['candidate'] is None


def test_forming_candle_and_future_changes_do_not_create_a_candidate():
    f,c,q=setup();extra=f.tail(1).copy();extra['time']=pd.Timestamp('2026-11-13T12:00:00Z')
    extra['high']=10000.;extra['low']=1.;extra['close']=9999.
    assert evaluate(pd.concat([f,extra],ignore_index=True),c,q,NOW)==evaluate(f,c,q,NOW)


def test_quote_context_gaps_and_missing_data_fail_closed():
    f,c,q=setup()
    q['at']=(NOW-pd.Timedelta(minutes=1)).isoformat()
    assert evaluate(f,c,q,NOW)['reason']=='stale_or_future_quote'
    f,c,q=setup();c['evaluated_at']=(NOW-pd.Timedelta(minutes=3)).isoformat()
    assert evaluate(f,c,q,NOW)['reason']=='stale_context'
    f,c,q=setup();f=f.drop(index=30)
    assert evaluate(f,c,q,NOW)['reason']=='M5_input_gap'
    f,c,q=setup();f.loc[5,'high']=float('nan')
    assert evaluate(f,c,q,NOW)['candidate'] is None


def test_price_must_be_in_discount_and_target_must_allow_two_r():
    f,c,q=setup()
    c['evidence']['H4']={'status':'available','recent_high':105.,'recent_low':90.}
    assert evaluate(f,c,q,NOW)['stage']=='premium_discount'
    f,c,q=setup();c['evidence']['M15']['recent_high']=105.
    r=evaluate(f,c,q,NOW)
    assert r['candidate'] is None and r['stage']=='liquidity_target'


def test_remove_sweep_displacement_gap_or_rejection_prevents_candidate():
    for change in ['sweep','displacement','gap','rejection']:
        f,c,q=setup()
        if change=='sweep':f.loc[60,'low']=f.loc[:59,'low'].min()+.1
        elif change=='displacement':f.loc[61,'close']=f.loc[61,'open']+.01
        elif change=='gap':f.loc[62,'low']=f.loc[60,'high']-.01
        else:f.loc[63,'open']=f.loc[63,'close']+.01
        assert evaluate(f,c,q,NOW)['candidate'] is None,change


def test_swings_are_not_confirmed_by_unavailable_right_hand_bars():
    f,_,_=setup()
    before=structure(f.iloc[:60].reset_index(drop=True))
    f.loc[60:,'high']=10000.
    assert structure(f.iloc[:60].reset_index(drop=True))==before


def test_first_mitigation_is_not_reissued_and_distances_use_broker_points():
    f,c,q=setup()
    r=evaluate(f,c,q,NOW)
    q['point']=.001
    scaled=evaluate(f,c,q,NOW)
    assert scaled['candidate']['stop_loss_points']==pytest.approx(r['candidate']['stop_loss_points']*10)
    f,c,q=setup()
    f=pd.concat([f.iloc[:-1],f.tail(1),f.tail(1)],ignore_index=True)
    f['time']=pd.date_range(end='2026-11-13T11:55:00Z',periods=len(f),freq='5min')
    assert evaluate(f,c,q,NOW)['candidate'] is None


def test_model_is_not_registered_as_an_executable_strategy():
    from atlas_ai.strategies.inventory import base_inventory
    assert NAME not in {s.name for s in base_inventory('M5',top_down=True)}
    from atlas_ai.trader import AtlasTrader
    t=AtlasTrader.__new__(AtlasTrader);t.settings=SimpleNamespace(top_down_confluence_enabled=False)
    t.executor=Mock(side_effect=AssertionError('observer cannot execute'))
    assert t._smc_composite_observation(None,{})['mode']=='inactive'
    t.executor.assert_not_called()
