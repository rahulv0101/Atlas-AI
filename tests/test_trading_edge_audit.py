from tools.trading_edge_audit import summarize


def stats(rows):
    return {'trade_list': rows, 'trades': len(rows),
            'wins': sum(t['net_cash'] > 0 for t in rows)}


def test_edge_summary_empty_sample_has_no_invented_expectancy():
    result = summarize(stats([]), '2026-11-16T00:00Z', '2026-11-20T23:59Z')
    assert result['win_rate'] is None
    assert result['mean_net_r_day_block_bootstrap_95_interval'] is None
    assert result['observed_weekdays'] == 5
    assert result['active_entry_days'] == 0


def test_edge_summary_groups_days_and_strategies_without_counting_deposits():
    rows = [{'entry_at': '2026-11-16T09:00Z', 'strategy': 'a', 'net_r': -1., 'net_cash': -10.,
             'ambiguous_stop_first': True},
            {'entry_at': '2026-11-16T10:00Z', 'strategy': 'a', 'net_r': -1., 'net_cash': -10.},
            {'entry_at': '2026-11-17T09:00Z', 'strategy': 'b', 'net_r': -1., 'net_cash': -10.}]
    result = summarize(stats(rows), '2026-11-16T00:00Z', '2026-11-20T23:59Z')
    assert result['mean_net_r_day_block_bootstrap_95_interval'] == [-1., -1.]
    assert result['observed_weekdays'] == 5
    assert result['active_entry_days'] == 2
    assert result['ambiguous_stop_first'] == 1
    assert result['by_strategy']['a']['net_cash'] == -20.
    assert 'trade_list' not in result
