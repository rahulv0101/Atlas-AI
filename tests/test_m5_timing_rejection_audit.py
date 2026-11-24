from types import SimpleNamespace

import pandas as pd

from atlas_ai.testing.historical_broker import BrokerSpec
from tools.audit_m5_timing_rejections import entry_index, unique_timing, model, extract


def test_no_borrowing_the_already_open_decision_candle():
    frame = pd.DataFrame({'time': pd.date_range('2026-11-24T14:00Z', periods=4, freq='5min')})
    assert entry_index(frame, '2026-11-24T14:08:31Z') == 2
    assert entry_index(frame, '2026-11-24T14:10:00Z') == 3
    assert entry_index(frame, '2026-11-24T14:19:00Z') is None


def test_duplicate_scans_keep_first_and_do_not_pool_policies():
    def row(at, policy):
        return {'at': at, 'policy': policy, 'primary': 'timing_discipline',
                'chosen': {'strategy': 'ema_crossover', 'side': 'sell'}}
    first = row('2026-11-24T14:06:00Z', 'new')
    later = row('2026-11-24T14:08:00Z', 'new')
    old = row('2026-11-24T14:07:00Z', 'old')
    assert unique_timing([later, old, first]) == [first, old]


def test_incomplete_forward_window_is_pending_unless_exit_is_observed():
    frame = pd.DataFrame({'time': pd.date_range('2026-11-24T14:00Z', periods=4, freq='5min'),
                          'open': 100., 'high': 100.1, 'low': 99.9, 'close': 100., 'spread': 1.})
    row = {'at': '2026-11-24T14:08:31Z', 'chosen': {
        'strategy': 'ema_crossover', 'side': 'buy', 'confidence': .8,
        'stop_loss_points': 100., 'take_profit_points': 150.}}
    settings = SimpleNamespace(backtest_max_hold_bars=12, backtest_break_even_lock_r=0,
        backtest_break_even_r_trigger=1., backtest_trailing_r_trigger=2.,
        backtest_trailing_buffer_r=.5, backtest_stale_exit_bars=10,
        backtest_stale_min_progress_r=.2)
    spec = BrokerSpec(.01, .01, 1., 1., .01, 1., .01, 2)
    assert model(row, frame, settings, spec)['state'] == 'forward_horizon_pending'
    frame.loc[2, 'low'] = 98.
    result = model(row, frame, settings, spec)
    assert result['state'] == 'modeled' and result['net_r'] < 0
    assert result['exit_reason'] == 'stop_loss'


def test_extract_ignores_non_M5_and_retains_recorded_gate_not_invented_pass():
    event = {'time': '2026-11-24T14:08:31Z', 'message': 'Timing discipline blocked trade',
             'meta': {'timeframe': 'M5', 'action': 'blocked',
                      'chosen': {'strategy': 'ema_crossover', 'side': 'sell'}}}
    assert extract(event)['htf_gate_passed'] is None
    event['meta']['timeframe'] = 'M1'
    assert extract(event) is None
