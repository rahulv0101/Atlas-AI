from copy import deepcopy
from types import SimpleNamespace
import pandas as pd
import pytest
from atlas_ai.data.top_down import TIMEFRAMES,POLICY
from atlas_ai.testing.structural_retest import evaluate,NAME
from atlas_ai.testing.tick_reconstruction import normalize_ticks,first_barrier,candle_coverage


def setup(side='buy'):
    times=pd.date_range('2026-11-10',periods=80,freq='5min',tz='UTC')
    f=pd.DataFrame({'time':times,'open':100.,'close':100.,'high':100.2,'low':99.8})
    f.loc[72,['high','low']]=[101.,99.7]
    f.loc[77,['open','high','low','close']]=[100.,101.8,100.,101.6]
    f.loc[78,['open','high','low','close']]=[101.6,101.8,101.3,101.5]
    f.loc[79,['open','high','low','close']]=[101.,101.3,100.95,101.1]
    if side=='sell':
        f[['open','close']]=200-f[['open','close']]
        high=f.high.copy();f['high']=200-f.low;f['low']=200-high
    now=times[-1]+pd.Timedelta(minutes=5)
    context={'bias':side,'policy':POLICY,'entry_timeframe':'M5','closed_candles_only':True,
        'evaluated_at':now.isoformat(),'details':{tf:side for tf in TIMEFRAMES},
        'evidence':{tf:{'recent_high':110.,'recent_low':90.} for tf in TIMEFRAMES}}
    bid=float(f.close.iloc[-1]);quote={'bid':bid,'ask':bid+.02,'point':.01,'at':now.isoformat()}
    return f,context,quote,now


@pytest.mark.parametrize('side',['buy','sell'])
def test_structural_stop_stays_beyond_first_retest_and_is_not_a_broker_strategy(side):
    f,c,q,now=setup(side);result=evaluate(f,c,q,now)
    assert result['candidate'] is not None,result
    assert result['broker_eligible'] is False and result['candidate']['strategy']==NAME
    if side=='buy':assert result['stop_reference']<f.low.iloc[-1]
    else:assert result['stop_reference']>f.high.iloc[-1]+q['ask']-q['bid']
    assert result['reward_risk_before_fees_slippage']>=2
    from atlas_ai.strategies.inventory import base_inventory
    assert NAME not in {x.name for x in base_inventory('M5',top_down=True)}


def test_forming_prices_cannot_improve_structure_or_reissue_a_prior_touch():
    f,c,q,now=setup();expected=evaluate(f,c,q,now)
    f=pd.concat([f,f.tail(1).assign(time=now,high=99999,close=99999)],ignore_index=True)
    assert evaluate(f,c,q,now)==expected
    c=deepcopy(c);c['evaluated_at']=(now+pd.Timedelta(minutes=5)).isoformat();q['at']=c['evaluated_at']
    f.loc[80,['open','high','low','close']]=[101.1,101.3,100.95,101.2]
    assert evaluate(f,c,q,now+pd.Timedelta(minutes=5))['candidate'] is None


def test_opposing_HTF_and_missing_recent_M5_data_prevent_entry():
    f,c,q,now=setup();c['details']['D1']='sell'
    assert evaluate(f,c,q,now)['candidate'] is None
    f,c,q,now=setup();f=f.drop(index=75)
    assert evaluate(f,c,q,now)['reason']=='recent_M5_gap'


def ticks(prices,side='sell'):
    at=pd.date_range('2026-10-01T00:00:00Z',periods=len(prices),freq='s')
    return pd.DataFrame({'utc':at,'bid':[x-.2 for x in prices],'ask':prices})


def test_tick_order_uses_ask_for_short_exits_and_reports_timestamp_ties():
    f=ticks([100.2,101.1,98.4])
    assert first_barrier(f,'sell',101,98.5)['outcome']=='stop_first'
    f=ticks([100.2,98.4,101.1])
    assert first_barrier(f,'sell',101,98.5)['outcome']=='target_first'
    f.loc[2,'utc']=f.utc.iloc[1]
    assert first_barrier(f,'sell',101,98.5)['outcome']=='same_millisecond_order_unresolved'


def test_tick_clock_normalization_is_explicit_and_bad_quotes_fail():
    raw=[{'time':1793577600,'time_msc':1793577600123,'bid':100.,'ask':100.2}]
    f=normalize_ticks(raw,SimpleNamespace(mt5_server_timezone='Europe/Athens'))
    expected=pd.Timestamp(1793577600123,unit='ms').tz_localize('Europe/Athens').tz_convert('UTC')
    assert f.utc.iloc[0]==expected
    raw[0]['ask']=99
    with pytest.raises(ValueError,match='invalid_bid_ask'):normalize_ticks(raw,SimpleNamespace(mt5_server_timezone='UTC'))


def test_missing_or_wrong_candle_history_does_not_resolve_ordering():
    start=pd.Timestamp('2026-10-01T00:00Z');end=start+pd.Timedelta(minutes=5)
    f=ticks([100.2,101.1,98.4]);rows,evidence=candle_coverage(f,{'open':100,'high':105,'low':90,'close':104},start,end,.01)
    assert not evidence['usable']


def test_verified_tick_candle_and_streamed_prediction_input(tmp_path):
    import json
    from tools.reconstruct_m5_losses import iter_first_array,barriers
    from atlas_ai.models import TradeSignal
    from atlas_ai.testing.historical_broker import BrokerSpec
    path=tmp_path/'predictions.json'
    rows=[{'index':1,'payload':'a'*10000},{'index':2,'payload':'b'}]
    path.write_text(json.dumps({'repaired_baseline':rows,'other':[{'must_not_be_read':True}]}))
    assert list(iter_first_array(path,'repaired_baseline'))==rows
    start=pd.Timestamp('2026-10-01T00:00Z');end=start+pd.Timedelta(minutes=5)
    f=pd.DataFrame({'utc':pd.date_range(start,periods=30,freq='10s'),'bid':100.,'ask':100.2})
    _,coverage=candle_coverage(f,{'open':100,'high':100,'low':100,'close':100},start,end,.01)
    assert coverage['usable']
    spec=BrokerSpec(.01,.01,1,1,.01,100,.01,2)
    assert barriers(100.,TradeSignal('test','sell',.7,100,150),spec,20)==(101.,98.5)


def test_structural_study_rejects_changed_frozen_model(tmp_path):
    from atlas_ai.testing.structural_retest import RULES
    from tools.research_structural_retest import verify_source,ROOT
    from tools.learn_candidate_ranker import save_signed,digest
    source=tmp_path/'source';tick=tmp_path/'tick'
    source.mkdir();tick.mkdir()
    save_signed(source,'protocol',{'test_fixture':True})
    save_signed(source,'source_receipt',{'source_hashes':{}})
    save_signed(source,'prediction_receipt',{'test_fixture':True})
    save_signed(source,'report',{'state':'completed_research_only',
        'protocol_sha256':digest(source/'protocol.json'),
        'prediction_receipt_sha256':digest(source/'prediction_receipt.json')})
    protocol={'source_report_sha256':digest(source/'report.json'),
        'structural_rules_frozen_before_tick_labels':RULES,
        'structural_model_sha256':digest(ROOT/'atlas_ai/testing/structural_retest.py')}
    save_signed(tick,'protocol',protocol)
    verify_source(source,tick)
    protocol['structural_model_sha256']='changed'
    save_signed(tick,'protocol',protocol)
    with pytest.raises(ValueError,match='structural_model_changed_after_tick_labels'):
        verify_source(source,tick)
