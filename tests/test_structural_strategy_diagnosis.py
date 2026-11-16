import pandas as pd
import pytest
from atlas_ai.testing.historical_broker import BrokerSpec
from tools.diagnose_structural_strategy import payoff_summary, path_excursions


def test_payoff_summary_explains_losing_sample_without_claiming_a_forecast():
    result = payoff_summary([{'net_cash': 100.}, {'net_cash': -60.}, {'net_cash': -60.}])
    assert result['net_cash_sum_separate_stage_runs'] == -20.
    assert result['profit_factor_pooled_fixed_sample'] == pytest.approx(100/120)
    assert result['break_even_win_rate_at_observed_payoffs'] == pytest.approx(60/160)
    assert result['win_rate'] == pytest.approx(1/3)
    assert 'Not one continuous portfolio' in result['note']


def test_empty_payoffs_do_not_invent_a_win_rate_or_profit_factor():
    result = payoff_summary([])
    assert result['win_rate'] is None and result['profit_factor_pooled_fixed_sample'] is None
    assert result['break_even_win_rate_at_observed_payoffs'] is None


def test_preexit_excursions_use_ask_for_shorts_and_exclude_ambiguous_exit_bar():
    spec = BrokerSpec(.01, .01, 1., 1., .01, 10., .01, 2)
    frame = pd.DataFrame({'high': [100., 1000.], 'low': [99., 1.], 'spread': [20., 20.]})
    trade = {'entry_bar': 0, 'exit_bar': 1, 'side': 'sell', 'entry_price': 100.,
             'initial_risk_cash': 1., 'volume': .01}
    result = path_excursions(frame, trade, spec)
    assert result['completed_preexit_mfe_r'] == pytest.approx(.8)
    assert result['completed_preexit_mae_r'] == pytest.approx(.2)
    assert result['completed_preexit_bars'] == 1 and result['exit_bar_order_unknown']
    trade['exit_bar'] = 0
    result = path_excursions(frame, trade, spec)
    assert result['completed_preexit_mfe_r'] is None
    assert result['completed_preexit_mae_r'] is None


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_tick_peak_excludes_stop_timestamp_ties_and_post_exit_prices(side):
    from tools.audit_early_stop_ticks import peak_before_stop
    times = pd.to_datetime(['2026-11-01T00:00:00Z', '2026-11-01T00:00:01Z',
                            '2026-11-01T00:00:02Z', '2026-11-01T00:00:02Z',
                            '2026-11-01T00:00:03Z'])
    if side == 'buy':
        bids = [100., 100.95, 99., 103., 105.]
        asks = [v+.2 for v in bids]
    else:
        asks = [100., 99.05, 101., 97., 95.]
        bids = [v-.2 for v in asks]
    rows = pd.DataFrame({'utc': times, 'bid': bids, 'ask': asks})
    result = peak_before_stop(rows, side, 100., 1., times[2].isoformat())
    assert result['peak_R_strictly_before_stop_timestamp'] == pytest.approx(.95)
    assert result['same_millisecond_quotes_at_stop'] == 2


@pytest.mark.parametrize('active', [None, [{'ProcessId': 123}]])
def test_optional_native_review_refuses_to_share_an_active_or_unverified_backend(monkeypatch, active):
    from tools import audit_early_stop_ticks as tool
    monkeypatch.setattr(tool, 'atlas_mode_processes', lambda *a, **k: active)
    with pytest.raises(RuntimeError, match='requires_idle_Atlas_terminal'):
        tool.require_idle_terminal()
