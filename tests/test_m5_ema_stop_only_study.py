from copy import deepcopy

import pandas as pd
import pytest

from tools.m5_ema_stop_only_study import stop_only


def test_stop_only_preserves_targets_signals_and_ignores_future_bars():
    frame = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=25, freq='5min', tz='UTC'),
                          'open': 100., 'high': 102., 'low': 98., 'close': 100.})
    signal = {'strategy': 'ema_crossover', 'side': 'buy', 'confidence': .8,
              'stop_loss_points': 100., 'take_profit_points': 150.}
    other = {**signal, 'strategy': 'pullback_trend'}
    rows = [{'index': 20, 'available_at': frame.time.iloc[21].isoformat(),
             'signals': [signal, other]}]
    original = deepcopy(rows)
    changed = stop_only(rows, frame, .01)
    assert rows == original
    expected = deepcopy(rows)
    expected[0]['signals'][0]['stop_loss_points'] = 800.
    assert changed == expected
    future = frame.copy()
    future.loc[21:, ['high', 'low', 'close']] = 10000.
    assert stop_only(rows, future, .01) == changed
    with pytest.raises(ValueError, match='positive_point'):
        stop_only(rows, frame, 0)


def test_stop_only_rejects_forming_bar_clock():
    frame = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=25, freq='5min', tz='UTC'),
                          'high': 102., 'low': 98., 'close': 100.})
    with pytest.raises(ValueError, match='clock_mismatch'):
        stop_only([{'index': 20, 'available_at': frame.time.iloc[20].isoformat(), 'signals': []}], frame, .01)
