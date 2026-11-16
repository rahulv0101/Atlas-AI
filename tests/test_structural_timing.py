from copy import deepcopy
import pandas as pd
import pytest
from atlas_ai.testing.structural_timing import verify
from atlas_ai.testing.aligned_smc import detect, MODELS
from test_aligned_smc import sweep_case, fvg_case


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_real_closed_sweep_reclaim_supplies_turning_evidence(side):
    f, c, q, now = sweep_case(side)
    anchor = detect(f, c, q, now)[MODELS[1]]
    result = verify(f, c, q, anchor, now, now)
    assert result['passed'], result
    assert result['fields'] == {'location_state': 'sweep_rejection', 'momentum_state': 'turning'}
    assert result['evidence']['location_source'] == 'reconstructed_closed_OHLC'


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_FVG_evidence_waits_for_actual_closed_structure_turn(side):
    f, c, q, anchor_at = fvg_case(side)
    anchor = detect(f, c, q, anchor_at)[MODELS[0]]
    assert not verify(f, c, q, anchor, anchor_at, anchor_at)['passed']
    now = anchor_at+pd.Timedelta(minutes=5)
    row = {'time': anchor_at, 'open': 113., 'high': 113.6, 'low': 112.8, 'close': 113.5}
    if side == 'sell':
        row.update(open=220-113., high=220-112.8, low=220-113.6, close=220-113.5)
    f = pd.concat([f, pd.DataFrame([row])], ignore_index=True)
    c = {**c, 'evaluated_at': now.isoformat()}
    q = {**q, 'bid': row['close']-.02, 'ask': row['close']+.02, 'at': now.isoformat()}
    result = verify(f, c, q, anchor, anchor_at, now)
    assert result['passed'], result
    assert result['fields']['location_state'] == 'fresh_retest'


def test_claimed_labels_stale_context_and_forming_candles_cannot_approve_evidence():
    f, c, q, now = sweep_case('buy')
    anchor = detect(f, c, q, now)[MODELS[1]]
    baseline = verify(f, c, q, anchor, now, now)
    forming = f.tail(1).assign(time=now, high=9999., low=1., close=9999.)
    assert verify(pd.concat([f, forming]), c, q, anchor, now, now) == baseline
    fake = deepcopy(anchor)
    fake['sweep']['level'] += 1
    assert not verify(f, c, q, fake, now, now)['passed']
    weak = f.copy()
    weak.loc[79, 'open'] = weak.close.iloc[-1]-.1
    assert not verify(weak, c, q, anchor, now, now)['passed']
    wrong = deepcopy(c)
    wrong['details']['H1'] = 'sell'
    assert not verify(f, wrong, q, anchor, now, now)['passed']
    assert not verify(f, c, q, anchor, now-pd.Timedelta(minutes=20), now)['passed']


def test_shared_timing_gate_sees_verified_turn_instead_of_generic_mixed_momentum():
    from atlas_ai.config.settings import Settings
    from atlas_ai.models import TradeSignal
    from atlas_ai.trader import AtlasTrader
    f, c, q, now = sweep_case('buy')
    anchor = detect(f, c, q, now)[MODELS[1]]
    evidence = verify(f, c, q, anchor, now, now)
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = Settings(1, 'test', 'Demo', timeframe='M5')
    signal = TradeSignal('test_smc_evidence', 'buy', .65, 100., 300.)
    chart = trader._derive_runtime_chart_features(df=f, chosen=signal, regime={'trend_strength': .4})
    old = {'location': chart['location_state'], 'momentum': chart['momentum_state'], 'session': 'london'}
    assert not trader._timing_discipline_snapshot(signal, old, {'chart_features': chart})['passed']
    actual = {**chart, **evidence['fields']}
    context = {**old, 'location': actual['location_state'], 'momentum': actual['momentum_state']}
    assert trader._timing_discipline_snapshot(signal, context, {'chart_features': actual})['passed']


def test_prior_confirmed_turn_cannot_be_reused_as_a_fresh_trigger():
    f, c, q, now = sweep_case('buy')
    anchor_at = now
    anchor = detect(f, c, q, now)[MODELS[1]]
    row = {'time': now, 'open': 100.8, 'high': 101.2, 'low': 100.75, 'close': 101.1}
    f = pd.concat([f, pd.DataFrame([row])], ignore_index=True)
    now += pd.Timedelta(minutes=5)
    c = {**c, 'evaluated_at': now.isoformat()}
    q = {**q, 'bid': 101.08, 'ask': 101.12, 'at': now.isoformat()}
    assert verify(f, c, q, anchor, anchor_at, now)['reason'] == 'structural_confirmation_already_occurred'


def test_research_adapter_is_scoped_and_restores_the_original_feature_path():
    from atlas_ai.config.settings import Settings
    from atlas_ai.models import TradeSignal
    from atlas_ai.trader import AtlasTrader
    from atlas_ai.testing.structural_timing import research_features
    f, c, q, now = sweep_case('buy')
    anchor = detect(f, c, q, now)[MODELS[1]]
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = Settings(1, 'test', 'Demo', timeframe='M5')
    signal = TradeSignal('smc_structural_timing_sweep_v8', 'buy', .65, 100., 300.)
    ordinary = TradeSignal('ema_crossover', 'buy', .65, 100., 300.)
    original = AtlasTrader._derive_runtime_chart_features
    before = trader._derive_runtime_chart_features(df=f, chosen=ordinary, regime={})
    lookup = {(signal.strategy, now.isoformat()): {'context': c, 'quote': q, 'anchor': anchor, 'anchor_at': now, 'now': now}}
    audit = {}
    with research_features(lookup, audit):
        assert trader._derive_runtime_chart_features(df=f, chosen=ordinary, regime={}) == before
        supplemented = trader._derive_runtime_chart_features(df=f, chosen=signal, regime={})
        assert supplemented['momentum_state'] == 'turning'
        assert supplemented['range_momentum_state'] != 'turning'
        assert supplemented['structural_timing_evidence']['passed']
    assert AtlasTrader._derive_runtime_chart_features is original
    assert audit[(signal.strategy, now.isoformat())]['passed']
