from copy import deepcopy
import pandas as pd
from atlas_ai.config.settings import Settings
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.entry_horizon import entry_check, target_plan


def test_entry_requires_aligned_M5_persistence_and_confirmed_structure():
    from test_smc_framework import continuation
    f, _, _ = continuation('buy')
    now = pd.Timestamp('2026-11-13T12:00Z')
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = Settings(1, 'test', 'Demo', timeframe='M5')
    passed = entry_check(trader, f, 'buy', now)
    assert passed['passed'], passed
    assert not entry_check(trader, f, 'sell', now)['passed']
    forming = f.tail(1).assign(time=now, high=9999., close=9999.)
    assert entry_check(trader, pd.concat([f, forming]), 'buy', now) == passed
    changed = f.copy()
    changed.loc[changed.index[-1], 'close'] = 100.
    assert not entry_check(trader, changed, 'buy', now)['passed']


def hourly_context():
    now = pd.Timestamp('2026-11-13T12:00Z')
    f = pd.DataFrame({'time': pd.date_range(end=now-pd.Timedelta(minutes=5), periods=300, freq='5min'),
                      'open': 100., 'close': 100.1, 'high': 100.6, 'low': 99.4})
    return f, now


def test_target_uses_only_past_ranges_and_does_not_change_protection_or_seed():
    f, now = hourly_context()
    signal = {'strategy': 'research', 'side': 'buy', 'confidence': .65, 'stop_loss_points': 40., 'take_profit_points': 200.}
    before = deepcopy(signal)
    allowed, changed, _, evidence = target_plan(signal, f, .01, now)
    assert allowed and changed['take_profit_points'] == 80.
    assert changed['stop_loss_points'] == 40. and changed['confidence'] == .65
    assert evidence['past_hour_blocks'] == 20
    assert signal == before
    forming = f.tail(1).assign(time=now, high=9999., low=1.)
    assert target_plan(signal, pd.concat([f, forming]), .01, now) == (allowed, changed, '2R_fits_past_hour_reference', evidence)


def test_unreachable_or_blocked_targets_are_rejected_instead_of_shortening_stops():
    f, now = hourly_context()
    signal = {'stop_loss_points': 100., 'take_profit_points': 300.}
    allowed, unchanged, reason, _ = target_plan(signal, f, .01, now)
    assert not allowed and reason == '2R_exceeds_typical_past_hour_range'
    assert unchanged == signal
    blocked = {'stop_loss_points': 100., 'take_profit_points': 150.}
    assert not target_plan(blocked, f, .01, now)[0]
    gapped = f.drop(index=list(range(0, len(f), 6)))
    assert not target_plan(signal, gapped, .01, now)[0]


def test_time_grid_matches_recent_detector_guard_instead_of_dropping_whole_sessions():
    from atlas_ai.testing.entry_horizon import eligible_window
    times = pd.Series(pd.date_range('2026-04-01', periods=130, freq='5min', tz='UTC'))
    times.loc[60:] += pd.Timedelta(hours=1)
    i = 100
    assert not times.iloc[i-79:i+13].diff().dropna().eq(pd.Timedelta(minutes=5)).all()
    assert eligible_window(times, i, times.iloc[-1]+pd.Timedelta(minutes=5))
    assert not eligible_window(times, 70, times.iloc[-1]+pd.Timedelta(minutes=5))
    future_gap = times.copy()
    future_gap.loc[105:] += pd.Timedelta(minutes=5)
    assert not eligible_window(future_gap, i, future_gap.iloc[-1]+pd.Timedelta(minutes=5))
    assert not eligible_window(times, i, times.iloc[i+10])
