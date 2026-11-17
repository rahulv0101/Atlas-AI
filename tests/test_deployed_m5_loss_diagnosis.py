import pytest
from tools.diagnose_deployed_m5_losses import summarize


def trade(cash,reason='stop_loss',entry=1,exit=1,ambiguous=False):
    return {'net_cash':cash,'exit_reason':reason,'entry_bar':entry,'exit_bar':exit,'ambiguous_stop_first':ambiguous}


def test_profitable_protected_stops_and_flat_exits_are_not_losses():
    s=summarize([trade(15),trade(-10,ambiguous=True),trade(0,'max_hold')])
    assert (s['wins'],s['losses'],s['flat'])==(1,1,1)
    assert s['net_cash']==5
    assert s['losing_first_bar_stops']==1 and s['ambiguous_stop_first']==1
    assert s['break_even_win_rate_at_observed_payoffs']==pytest.approx(.4)


def test_no_outcomes_or_no_losers_does_not_invent_a_break_even_rate():
    assert summarize([])['observed_win_rate'] is None
    assert summarize([trade(1,'take_profit')])['break_even_win_rate_at_observed_payoffs'] is None
