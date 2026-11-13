from copy import deepcopy
from dataclasses import replace
import math

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.models import TradeSignal
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.low_energy_audit import current_audit,evaluate,trace_pair,traders,summarize_publications


def settings():
    return Settings(0,'','',timeframe='M1',learning_mode=False)


def context(**kw):
    return {'session':'london','allowed_session':True,'regime':'range','trend_strength':.04,
        'volatility_pct':.01,'volatility_state':'low','entry_location_state':'pullback',
        'entry_momentum_state':'strong',**kw}


def test_alternative_changes_only_one_setting_and_preserves_signal_inputs():
    cfg=settings(); left,right=traders(cfg)
    assert right.settings==replace(cfg,signal_regime_gate_min_trend_strength_pct=-1.)
    signal=TradeSignal('ema_crossover','buy',.8,100.,150.)
    before=deepcopy(signal)
    result=trace_pair(left,right,signal,context())
    assert result['baseline']['side']=='flat'
    assert result['alternative']['side']=='buy'
    assert result['alternative']['confidence']==pytest.approx(.8*cfg.signal_trend_strength_weak_confidence_multiplier)
    assert 'weak_trend_confidence_reduction' in result['alternative_reasons']
    assert signal==before and cfg.signal_regime_gate_min_trend_strength_pct==.18


def test_remaining_momentum_and_session_filters_are_not_bypassed():
    left,right=traders(settings())
    for name,ctx,reason in [
        ('momentum_continuation',context(),'momentum_regime_requirements_not_met'),
        ('ema_crossover',context(allowed_session=False),'outside_allowed_session_suppression')]:
        r=trace_pair(left,right,TradeSignal(name,'buy',.8,100.,150.),ctx)
        assert r['alternative']['side']=='flat'
        assert reason in r['alternative_reasons']


def test_learning_mode_cannot_masquerade_as_single_veto_comparison():
    with pytest.raises(ValueError,match='learning_mode_false'):
        traders(replace(settings(),learning_mode=True))


class Fixed:
    name='ema_crossover'
    def generate_signal(self,window):
        return TradeSignal(self.name,'buy',.8,100.,150.)


def frame():
    prices=[2000+math.sin(i)*.1 for i in range(1260)]
    return pd.DataFrame({'time':pd.date_range('2026-11-02 12:00',periods=1260,freq='min'),
        'open':prices,'high':[p+.3 for p in prices],'low':[p-.3 for p in prices],
        'close':prices,'spread':20.,'tick_volume':100.})


def test_closed_windows_costs_and_future_prices_do_not_change_predictions():
    f=frame(); spec=BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2,roundtrip_fee_per_lot=5.)
    a=evaluate(f,settings(),spec,pack=[Fixed()])
    altered=f.copy();altered.loc[1200:,'high']+=5
    b=evaluate(altered,settings(),spec,pack=[Fixed()])
    first=a['cases'][0]; other=b['cases'][0]
    assert first['entry_at']=='2026-11-03T08:00:00+00:00'
    assert first['raw']==other['raw'] and first['context']==other['context']
    assert first['net_r']!=other['net_r']
    assert first['retained_by_remaining_signal_filters']
    assert not first['full_execution_eligibility_verified']
    assert not a['broker_eligible'] and a['orders_sent']==0 and a['policy_changes']==[]


def test_missing_input_or_outcome_bars_cannot_be_labelled_as_contiguous():
    f=frame().drop(index=1201).reset_index(drop=True)
    result=evaluate(f,settings(),BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2),pack=[Fixed()])
    assert result['cases']==[]
    assert result['counts']['execution_horizon_gap']>=1


def test_point_twelve_threshold_still_suppresses_low_volatility_ranges():
    left,_=traders(replace(settings(),signal_regime_gate_min_trend_strength_pct=.12))
    ctx=context(trend_strength=.1199)
    s=left._apply_signal_generation_gating(TradeSignal('ema_crossover','buy',.8,100.,150.),ctx)
    assert s.side=='flat'
    report=current_audit(settings(),{'signal_generation':{'context':ctx}})
    assert report['predicate_from_published_context'] and not report['broker_eligible']


def test_archive_summary_deduplicates_publications_and_separates_later_gates():
    a={'publication':{'updated_at':'2026-11-13T12:00:00+00:00','chosen':{'side':'buy'},
        'signal_generation':{'candidates':[]},'primary_blocker':'Higher-timeframe alignment required: buy vs sell'}}
    # Real pipelines contain other fields even when their candidate list is empty.
    b=deepcopy(a);b['publication']['updated_at']='2026-11-13T12:01:00+00:00'
    b['publication']['primary_blocker']='Timing discipline blocked trade: weak'
    r=summarize_publications([a,a,b,{'publication':{}}])
    assert r['counts']=={'publications':2,'directional_chosen':2}
    assert r['primary_blockers']=={'higher_timeframe_alignment':1,'timing_discipline':1}
