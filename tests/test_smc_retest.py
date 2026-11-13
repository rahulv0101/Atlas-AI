from copy import deepcopy
import pandas as pd
import pytest
from test_smc_pullback import pullback,NOW
from atlas_ai.strategies.smc_pullback import evaluate as previous
from atlas_ai.strategies.smc_retest import first_retest,evaluate,NAME


def frame(rows):return pd.DataFrame(rows,columns=['open','high','low','close'])
ZONES=[('FVG',100.,102.),('order_block',96.,98.)]


def test_previously_touched_gap_does_not_discard_untouched_order_block():
    f=frame([[103.,103.2,101.,101.2],[97.,99.,96.5,98.5]])
    r=first_retest(f,ZONES,'buy',95.)
    assert r['valid_zones']==[['order_block',96.,98.]]
    assert r['zones']['FVG']['state']=='zone_close_invalidated'


def test_confirmation_can_follow_touch_without_another_zone_touch():
    f=frame([[103.,103.2,100.5,101.2],[102.4,103.5,102.3,103.2]])
    r=first_retest(f,[ZONES[0]],'buy',95.)
    assert r['valid_zones']==[['FVG',100.,102.]]
    assert r['zones']['FVG']['bars_since_touch']==1


def test_expired_second_visit_and_previous_confirmation_are_rejected():
    expired=frame([[103.,103.2,100.5,101.2],[101.8,102.,100.8,101.2],
        [101.7,102.,100.9,101.2],[102.4,103.5,102.3,103.2]])
    assert not first_retest(expired,[ZONES[0]],'buy',95.)['valid_zones']
    revisit=frame([[103.,103.2,100.5,101.2],[103.,103.2,102.2,102.4],[100.8,102.5,100.5,102.2]])
    assert first_retest(revisit,[ZONES[0]],'buy',95.)['zones']['FVG']['state']=='second_visit_rejected'
    confirmed=frame([[100.8,102.5,100.5,102.2],[102.3,103.,102.1,102.9]])
    assert first_retest(confirmed,[ZONES[0]],'buy',95.)['reason']=='setup_already_confirmed_on_prior_bar'


@pytest.mark.parametrize('side',['buy','sell'])
def test_setup_extreme_breach_invalidates_even_if_the_candle_closes_back_inside(side):
    f=frame([[103.,104.,94.,102.]])
    if side=='sell':
        f=frame([[117.,126.,116.,118.]])
    r=first_retest(f,ZONES,side,95. if side=='buy' else 125.)
    assert r['reason']=='setup_extreme_breached_before_confirmation'


@pytest.mark.parametrize('side',['buy','sell'])
def test_complete_original_signal_still_qualifies_and_has_stable_setup_identity(side):
    f,c,q=pullback(side);original=deepcopy(c)
    r=evaluate(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['candidate']['strategy']==NAME and r['setup_id'].startswith(NAME+':'+side)
    assert r['candidate']['stop_loss_points']==pytest.approx(previous(f,c,q,NOW)['candidate']['stop_loss_points'])
    assert c==original and not r['broker_eligible']


def test_full_model_recovers_an_order_block_after_unconfirmed_gap_touch():
    f,c,q=pullback()
    f.loc[63,'open']=104.4;f.loc[63,'close']=103.
    ob=f.iloc[60];close=float(ob.high)-.1
    new=pd.DataFrame([{'open':close-.8,'high':float(ob.high)+.2,'low':float(ob.low)+.2,'close':close,'time':f.time.iloc[-1]+pd.Timedelta(minutes=5)}])
    f=pd.concat([f,new],ignore_index=True)
    f['time']=pd.date_range(end='2026-11-13T11:55:00Z',periods=len(f),freq='5min')
    q['bid']=close-.02;q['ask']=close+.02
    assert previous(f,c,q,NOW)['candidate'] is None
    r=evaluate(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['retest_zone']=='order_block'


def test_model_remains_absent_from_executable_inventory():
    from atlas_ai.strategies.inventory import base_inventory
    from tools.smc_validation import evaluator_for
    assert NAME not in {s.name for s in base_inventory('M5',top_down=True)}
    assert evaluator_for({'model':NAME}).__module__=='atlas_ai.strategies.smc_retest'


def test_setup_identity_prevents_different_confirmation_bars_reissuing_same_sweep():
    from atlas_ai.testing.smc_validation import setup_identity
    a={'setup_id':'smc_retest_v3:buy:sweep1','trigger_bar_utc':'bar1','side':'buy'}
    b={**a,'trigger_bar_utc':'bar2'}
    assert setup_identity(a)==setup_identity(b)
