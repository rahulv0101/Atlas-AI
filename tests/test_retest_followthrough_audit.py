import pandas as pd
from tools.audit_retest_followthrough import first_barrier


def test_stop_first_target_and_ambiguous_outcomes():
    frame=pd.DataFrame({'time':pd.date_range('2026-11-02T08:00Z',periods=3,freq='5min'),
                        'high':[100.5,102.1,101.],'low':[99.5,100.,100.],'spread':[0.,0.,0.]})
    trade={'side':'buy','entry_price':100.,'entry_bar':0}
    assert first_barrier(frame,trade,100,.01,3)=='two_R_first'
    frame.loc[0,'low']=98.9
    assert first_barrier(frame,trade,100,.01,3)=='initial_stop_first'
    frame.loc[0,'high']=102.1
    assert first_barrier(frame,trade,100,.01,3)=='ambiguous_stop_first'


def test_short_or_gapped_path_is_not_complete_followthrough_evidence():
    frame=pd.DataFrame({'time':pd.date_range('2026-11-02T08:00Z',periods=3,freq='5min'),
                        'high':100.5,'low':99.5,'spread':0.})
    trade={'side':'buy','entry_price':100.,'entry_bar':0}
    assert first_barrier(frame,trade,100,.01,3)=='neither_within_one_hour'
    assert first_barrier(frame,trade,100,.01,12)=='coverage_gap'
    frame.loc[1,'time']+=pd.Timedelta(minutes=1)
    assert first_barrier(frame,trade,100,.01,3)=='coverage_gap'
