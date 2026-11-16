from copy import deepcopy
import pandas as pd
import pytest
from atlas_ai.data.top_down import TIMEFRAMES, POLICY
from atlas_ai.testing.aligned_smc import detect, MODELS
from atlas_ai.testing.smc_confirmation import Confirmation


def context(side, now):
    return {'bias': side, 'details': {tf: side for tf in TIMEFRAMES}, 'policy': POLICY,
            'entry_timeframe': 'M5', 'closed_candles_only': True, 'evaluated_at': now.isoformat(),
            'evidence': {tf: {'status': 'available', 'recent_high': 140., 'recent_low': 80.} for tf in TIMEFRAMES}}


def fvg_case(side):
    from test_smc_framework import continuation
    f, _, q = continuation(side)
    now = pd.Timestamp('2026-11-13T12:00Z')
    return f, context(side, now), {**q, 'digits': 2, 'at': now.isoformat()}, now


def sweep_case(side):
    now = pd.Timestamp('2026-11-13T12:00Z')
    f = pd.DataFrame({'time': pd.date_range(end=now-pd.Timedelta(minutes=5), periods=80, freq='5min'),
                      'open': 100.2, 'close': 100.3, 'high': 100.5, 'low': 100.})
    f.loc[78, ['open', 'high', 'low', 'close']] = [100.3, 100.5, 99.7, 100.35]
    f.loc[79, ['open', 'high', 'low', 'close']] = [100.35, 100.9, 100.3, 100.8]
    if side == 'sell':
        old = f.copy()
        f['open'], f['close'], f['high'], f['low'] = 220-old.open, 220-old.close, 220-old.low, 220-old.high
    close = float(f.close.iloc[-1])
    return f, context(side, now), {'bid': close-.02, 'ask': close+.02, 'point': .01, 'digits': 2, 'at': now.isoformat()}, now


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('case,model', [(fvg_case, MODELS[0]), (sweep_case, MODELS[1])])
def test_new_detectors_generate_natural_geometry_with_all_four_aligned_without_opposing_HTF_closes(side, case, model):
    f, c, q, now = case(side)
    before = f.copy()
    result = detect(f, c, q, now)[model]
    assert result['candidate'], result
    assert result['candidate']['side'] == side and result['candidate']['strategy'] == model
    assert result['reward_risk_before_fees_slippage'] >= 2
    assert result['broker_eligible'] is False
    pd.testing.assert_frame_equal(f, before)
    if model == MODELS[0]:
        assert 'FVG' in result
        assert result['stop_reference'] < result['FVG']['low'] if side == 'buy' else result['stop_reference'] > result['FVG']['high']
    else:
        assert result['stop_reference'] < result['sweep']['extreme'] if side == 'buy' else result['stop_reference'] > result['sweep']['extreme']


def test_opposing_context_future_bars_and_used_retests_cannot_manufacture_candidates():
    f, c, q, now = fvg_case('buy')
    baseline = detect(f, c, q, now)
    forming = f.tail(1).assign(time=now, high=9999., low=1., close=9999.)
    assert detect(pd.concat([f, forming], ignore_index=True), c, q, now) == baseline
    wrong = deepcopy(c)
    wrong['details']['M15'] = 'sell'
    assert all(v['candidate'] is None for v in detect(f, wrong, q, now).values())
    f.loc[60, 'close'] = f.close.iloc[59]
    assert detect(f, c, q, now)[MODELS[0]]['candidate'] is None
    f, c, q, now = sweep_case('buy')
    f.loc[78, 'low'] = 100.1
    assert detect(f, c, q, now)[MODELS[1]]['candidate'] is None


def test_named_research_adapter_has_no_broker_inventory_authority_and_legacy_names_stay_unchanged():
    from atlas_ai.strategies.inventory import base_inventory
    assert Confirmation('smc_event_retest_v5').name == 'smc_event_retest_confirmed_v6'
    assert Confirmation(MODELS[0], research_name='smc_aligned_fvg_confirmed_v7').name == 'smc_aligned_fvg_confirmed_v7'
    assert not set(MODELS) & {s.name for s in base_inventory('M5', top_down=True)}
