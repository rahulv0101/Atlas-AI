from copy import deepcopy
import pytest
from test_smc_composite import setup,NOW
from atlas_ai.strategies.smc_composite import evaluate as original
from atlas_ai.strategies.smc_pullback import evaluate,setup_context,NAME


def pullback(side='buy'):
    f,c,q=setup(side)
    c['bias']='mixed'
    c['details']['H1']='sell' if side=='buy' else 'buy'
    c['details']['M15']='flat'
    c['evidence']['H1'].update(recent_low=96.,recent_high=118.,recent_closes=[108.,107.,106.,105.,104.,103.])
    c['evidence']['M15']['recent_closes']=[104.4]*6
    if side=='sell':
        for tf in ['H1','M15']:
            row=c['evidence'][tf];row['recent_closes']=[220-v for v in row['recent_closes']]
        c['evidence']['H1']['recent_low']=102.;c['evidence']['H1']['recent_high']=124.
    return f,c,q


@pytest.mark.parametrize('side',['buy','sell'])
def test_opposing_lower_timeframe_pullback_can_form_a_complete_M5_entry(side):
    f,c,q=pullback(side);before=deepcopy(c)
    assert original(f,c,q,NOW)['candidate'] is None
    r=evaluate(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['candidate']['strategy']==NAME and r['candidate']['side']==side
    assert r['setup_context']['pullback_timeframes']==['H1']
    assert r['setup_context']['lower_timeframe_biases']['M15']=='flat'
    assert c==before and not r['broker_eligible']


def test_local_reaction_zone_replaces_the_conflicting_H4_midpoint_veto():
    f,c,q=pullback();c['evidence']['H4']['recent_high']=115.
    assert q['ask']>(115.+90.)/2
    r=evaluate(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['setup_context']['reaction_zones'][0]['timeframe']=='H1'


@pytest.mark.parametrize('tf',['D1','H4'])
def test_conflicting_direction_still_blocks(tf):
    f,c,q=pullback();c['details'][tf]='sell'
    assert evaluate(f,c,q,NOW)['candidate'] is None


def test_missing_lower_timeframe_evidence_and_unobserved_pullbacks_fail_closed():
    f,c,q=pullback();del c['evidence']['M15']['recent_closes']
    assert evaluate(f,c,q,NOW)['stage']=='input_validation'
    f,c,q=pullback()
    for tf in ['H1','M15']:c['evidence'][tf]['recent_closes']=[100.,101.,102.,103.,104.,105.]
    assert evaluate(f,c,q,NOW)['stage']=='pullback_context'


def test_no_local_reaction_zone_or_M5_trigger_does_not_become_a_trade():
    f,c,q=pullback()
    for tf in ['H1','M15']:c['evidence'][tf].update(recent_low=90.,recent_high=110.)
    assert evaluate(f,c,q,NOW)['stage']=='setup_location'
    f,c,q=pullback();f.loc[63,'open']=f.loc[63,'close']+.01
    assert evaluate(f,c,q,NOW)['candidate'] is None


def test_future_higher_timeframe_changes_are_not_needed_to_release_the_pullback():
    # The callback consumes only six already closed prices, never a forming
    # candle or live chart inference. Freshness is enforced by the shared core.
    f,c,q=pullback();r=evaluate(f,c,q,NOW)
    assert r['candidate'] is not None
    c['evaluated_at']='2020-01-01T00:00:00+00:00'
    assert evaluate(f,c,q,NOW)['candidate'] is None


def test_frozen_model_selection_is_explicit_and_new_model_is_not_executable():
    from tools.smc_validation import evaluator_for
    from atlas_ai.strategies.inventory import base_inventory
    assert evaluator_for({'model':NAME}).__module__=='atlas_ai.strategies.smc_pullback'
    assert evaluator_for({}).__module__=='atlas_ai.strategies.smc_composite'
    with pytest.raises(ValueError,match='unsupported'):evaluator_for({'model':'arbitrary_model'})
    assert NAME not in {s.name for s in base_inventory('M5',top_down=True)}


def test_cached_context_matches_direct_closed_candle_collection():
    import pandas as pd
    from atlas_ai.testing.smc_validation import historical,HistoricalFeed
    from atlas_ai.data.top_down import collect,MINUTES,TIMEFRAMES
    from atlas_ai.config.settings import Settings
    from atlas_ai.testing.historical_broker import BrokerSpec
    end=pd.Timestamp('2026-11-14T00:00:00Z')
    frames={}
    for tf in TIMEFRAMES:
        times=pd.date_range(end=end,periods=100,freq=pd.Timedelta(minutes=MINUTES[tf]))
        prices=[2000.+i for i in range(100)]
        frames[tf]=pd.DataFrame({'time':times,'open':prices,'high':[p+2 for p in prices],'low':[p-2 for p in prices],'close':prices,'spread':2.})
    times=pd.date_range('2026-11-13',periods=170,freq='5min',tz='UTC')
    frames['M5']=pd.DataFrame({'time':times,'open':2000.,'high':2001.,'low':1999.,'close':2000.,'spread':2.})
    direct=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES});checked=[]
    def inspect(frame,context,quote,now):
        direct.now=now
        assert context==collect(direct,now,broker_timezone='UTC')
        checked.append(now)
        return {'stage':'test_no_candidate','candidate':None}
    cfg=Settings(0,'','',timeframe='M5')
    historical(frames,cfg,BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2),
        {'day_trades':6,'loss_streak':3,'daily_loss_percent':1.,'lot_cap':.01},
        pd.Timestamp('2026-11-13T00:00:00Z'),end,evaluator=inspect)
    assert len(checked)>3
