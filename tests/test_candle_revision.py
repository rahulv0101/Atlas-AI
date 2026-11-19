import pandas as pd
from atlas_ai.testing.candle_revision import revision_audit


def frame():
    return pd.DataFrame({'time':pd.date_range('2026-11-19',periods=3,freq='5min'),
        'open':100,'high':102,'low':99,'close':101,'spread':34,'tick_volume':100,'real_volume':0,'atr_price':1.})


def test_csv_dtype_or_recomputed_indicator_does_not_masquerade_as_broker_revision():
    a=frame();b=a.copy();b['atr_price']=2.;b['open']=b.open.astype(float)
    assert revision_audit(a,b)['compatible_overlap']


def test_actual_price_or_volume_change_remains_a_revision():
    a=frame();b=a.copy();b.loc[1,'close']=100;b.loc[2,'tick_volume']=101
    result=revision_audit(a,b)
    assert result['changed_bars']==2 and not result['compatible_overlap']


def test_rolling_window_overlap_and_missing_overlap_are_explicit():
    a=frame()
    assert revision_audit(a,a.iloc[1:])['overlapping_bars']==2
    b=a.copy();b['time']+=pd.Timedelta(days=1)
    assert not revision_audit(a,b)['compatible_overlap']
