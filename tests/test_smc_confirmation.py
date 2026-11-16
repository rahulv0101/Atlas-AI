from copy import deepcopy
from dataclasses import replace
import pandas as pd
import pytest
from atlas_ai.config.settings import Settings
from atlas_ai.data.top_down import POLICY, TIMEFRAMES
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.smc_confirmation import Confirmation, MODELS, affordable


def case(side='buy'):
    now = pd.Timestamp('2026-11-10T12:00Z')
    frame = pd.DataFrame({'time': pd.date_range(end=now-pd.Timedelta(minutes=5), periods=80, freq='5min'),
                          'open': 100., 'high': 100.5, 'low': 99.5, 'close': 100.01})
    if side == 'sell':
        frame['open'] = 100.02
    context = {'bias': side, 'details': {tf: side for tf in TIMEFRAMES}, 'policy': POLICY,
               'entry_timeframe': 'M5', 'closed_candles_only': True, 'evaluated_at': now.isoformat(),
               'evidence': {tf: {'recent_high': 110., 'recent_low': 90.} for tf in TIMEFRAMES}}
    quote = {'bid': 100.01, 'ask': 100.03, 'point': .01, 'digits': 2, 'at': now.isoformat()}
    raw = {'setup_id': 'fixed-source-anchor', 'stop_reference': 99. if side == 'buy' else 101.02,
           'candidate': {'strategy': 'smc_event_retest_v5', 'side': side, 'confidence': .65,
                         'stop_loss_points': 100., 'take_profit_points': 300.}}
    return frame, context, quote, raw, now


def advance(frame, context, quote, now, side='buy', **changes):
    row = {'time': now, 'open': 100., 'high': 100.5, 'low': 99.5,
           'close': 100.04 if side == 'buy' else 99.98}
    row.update(changes)
    frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
    now += pd.Timedelta(minutes=5)
    context = {**context, 'evaluated_at': now.isoformat()}
    quote = {**quote, 'at': now.isoformat(), 'bid': row['close'], 'ask': row['close']+.02}
    return frame, context, quote, now


def allow(signal, entry):
    return True, 'affordable', {}


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_waits_for_real_confirmation_without_tightening_protection(side):
    f, c, q, raw, now = case(side)
    state = Confirmation(raw['candidate']['strategy'])
    assert state.step(raw, f, c, q, now, lambda s: False, allow)['candidate'] is None
    f, c, q, now = advance(f, c, q, now, side)
    result = state.step({}, f, c, q, now, lambda s: True, allow)
    assert result['candidate'] is not None
    assert result['broker_eligible'] is False and state.pending is None
    assert result['candidate']['strategy'] == MODELS[raw['candidate']['strategy']]
    if side == 'buy':
        assert result['stop_reference'] <= raw['stop_reference']
    else:
        assert result['stop_reference'] >= raw['stop_reference']
    assert state.step(raw, f, c, q, now, lambda s: True, allow)['candidate'] is None


def test_all_four_alignment_required_and_losing_alignment_retires_anchor():
    f, c, q, raw, now = case()
    wrong = deepcopy(c)
    wrong['details']['M15'] = 'sell'
    state = Confirmation('smc_event_retest_v5')
    assert state.step(raw, f, wrong, q, now, lambda s: True, allow)['stage'] == 'higher_timeframe_confluence'
    state = Confirmation('smc_event_retest_v5')
    state.step(raw, f, c, q, now, lambda s: False, allow)
    f, c, q, now = advance(f, c, q, now)
    c['details'] = {**c['details'], 'H1': 'sell'}
    assert state.step({}, f, c, q, now, lambda s: True, allow)['reason'] == 'alignment_lost_before_confirmation'
    assert state.pending is None and raw['setup_id'] in state.retired


def test_breached_and_expired_anchors_cannot_be_rearmed():
    f, c, q, raw, now = case()
    state = Confirmation('smc_event_retest_v5')
    state.step(raw, f, c, q, now, lambda s: False, allow)
    f, c, q, now = advance(f, c, q, now, low=98.9)
    assert state.step({}, f, c, q, now, lambda s: True, allow)['reason'] == 'original_structural_protection_breached'
    assert raw['setup_id'] in state.retired
    f, c, q, raw, now = case()
    state = Confirmation('smc_event_retest_v5')
    state.step(raw, f, c, q, now, lambda s: False, allow)
    for i in range(4):
        f, c, q, now = advance(f, c, q, now)
        result = state.step({}, f, c, q, now, lambda s: False, allow)
    assert result['reason'] == 'confirmation_window_expired'
    assert state.pending is None and raw['setup_id'] in state.retired


def test_forming_prices_cannot_create_confirmation_and_widened_sell_spread_cannot_shrink_stop():
    f, c, q, raw, now = case()
    forming = f.tail(1).assign(time=now, close=9999., high=9999.)
    a, b = Confirmation('smc_event_retest_v5'), Confirmation('smc_event_retest_v5')
    assert a.step(raw, f, c, q, now, lambda s: True, allow) == b.step(raw, pd.concat([f, forming]), c, q, now, lambda s: True, allow)
    f, c, q, raw, now = case('sell')
    state = Confirmation('smc_event_retest_v5')
    state.step(raw, f, c, q, now, lambda s: False, allow)
    f, c, q, now = advance(f, c, q, now, 'sell')
    q['ask'] = q['bid']+.12
    result = state.step({}, f, c, q, now, lambda s: True, allow)
    assert result['candidate'] and result['stop_reference'] >= raw['stop_reference']+.1-1e-9


def test_budget_includes_costs_and_never_rewrites_the_signal():
    cfg = Settings(1, 'test', 'Demo', timeframe='M5')
    spec = BrokerSpec(.01, .01, 17., 17., .01, 100., .01, 2)
    signal = {'stop_loss_points': 200., 'take_profit_points': 600.}
    original = dict(signal)
    assert affordable(signal, 100., spec, cfg, {'lot_cap': .01})[0]
    assert not affordable(signal, 100., replace(spec, roundtrip_fee_per_lot=2000.), cfg, {'lot_cap': .01})[0]
    signal['stop_loss_points'] = 500.
    assert not affordable(signal, 100., spec, cfg, {'lot_cap': .01})[0]
    assert signal['stop_loss_points'] == 500. and original['stop_loss_points'] == 200.
    from atlas_ai.strategies.inventory import base_inventory
    assert not set(MODELS.values()) & {s.name for s in base_inventory('M5', top_down=True)}


def test_duplicate_bar_preserves_pending_state_and_unavailable_window_retires_it():
    f, c, q, raw, now = case()
    state = Confirmation('smc_event_retest_v5')
    state.step(raw, f, c, q, now, lambda s: False, allow)
    anchor = deepcopy(state.pending)
    duplicate = state.step(raw, f, c, q, now, lambda s: True, allow)
    assert duplicate['reason'] == 'await_new_closed_M5_bar'
    assert state.pending == anchor
    f, c, q, now = advance(f, c, q, now)
    f, c, q, now = advance(f, c, q, now)
    skipped = state.step({}, f, c, q, now, lambda s: True, allow)
    assert skipped['reason'] == 'unavailable_confirmation_window_retired'
    assert state.pending is None and raw['setup_id'] in state.retired
