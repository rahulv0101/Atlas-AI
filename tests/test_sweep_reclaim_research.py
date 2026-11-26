import pandas as pd
from tools.sweep_reclaim_research import pattern


def sample(side='buy'):
    f=pd.DataFrame({'time':pd.date_range('2026-11-02T08:00Z',periods=60,freq='5min'),
                    'open':100.,'high':101.,'low':99.,'close':100.})
    f.loc[58,['open','high','low','close']]=[99.8,100.5,98.5,100.]
    f.loc[59,['open','high','low','close']]=[100.,101.5,99.8,101.2]
    if side=='sell':
        old=f.copy();f['open']=200-old.open;f['close']=200-old.close;f['high']=200-old.low;f['low']=200-old.high
    return f,f.time.iloc[-1]+pd.Timedelta(minutes=5)


def test_sweep_requires_distinct_closed_confirmation_for_both_sides():
    for side in ('buy','sell'):
        f,now=sample(side);result=pattern(f,side,now)
        assert result and result['side']==side
        assert pd.Timestamp(result['sweep_at'])<pd.Timestamp(result['confirmation_at'])<now
        assert result['authority']=='research_only'


def test_forming_bar_does_not_change_setup_and_unconfirmed_sweep_fails():
    f,now=sample();before=pattern(f,'buy',now)
    forming=f.iloc[-1:].copy();forming['time']=now;forming[['open','high','low','close']]=[500.,900.,1.,800.]
    assert pattern(pd.concat([f,forming],ignore_index=True),'buy',now)==before
    f.loc[59,'close']=100.2
    assert pattern(f,'buy',now) is None


def test_gap_weak_wick_and_wrong_side_do_not_qualify():
    f,now=sample();assert pattern(f,'sell',now) is None
    f.loc[58,'low']=99.1
    assert pattern(f,'buy',now) is None


def test_verified_sweep_maps_to_existing_timing_gate_without_broadening_it(monkeypatch):
    from types import SimpleNamespace
    from atlas_ai.config.settings import Settings
    from atlas_ai.models import TradeSignal
    from atlas_ai.trader import AtlasTrader
    from tools.sweep_reclaim_research import sweep_overlay,NAME
    f,now=sample();proof=pattern(f,'buy',now)
    monkeypatch.setattr(AtlasTrader,'_derive_runtime_chart_features',lambda self,**k:{
        'location_state':'mid_range','momentum_state':'weak','trend_state':'uptrend','trend_strength':.6})
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=Settings(1,'','Demo',timeframe='M5')
    signal=TradeSignal(NAME,'buy',.7,100,200)
    with sweep_overlay([{'available_at':now.isoformat(),'signals':[{'side':'buy'}],'sweep_evidence':proof}]):
        features=trader._derive_runtime_chart_features(df=f,chosen=signal,regime={})
    assert features['location_state']=='structure_reclaim'
    context={'location_state':features['location_state'],'momentum_state':features['momentum_state'],
             'trend_state':'uptrend','trend_strength':.6,'session':'asia'}
    result=trader._timing_discipline_snapshot(signal,context,{'chart_features':features})
    assert result['passed'],result
    f,now=sample();f.loc[45,'time']-=pd.Timedelta(minutes=1)
    assert pattern(f,'buy',now) is None
