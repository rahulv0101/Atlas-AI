import pandas as pd
from tools.h1_entry_quality_research import confirms


def sample():
    f=pd.DataFrame({'time':pd.date_range('2026-11-01T00:00Z',periods=31,freq='h'),
                    'open':100.,'high':102.,'low':99.,'close':101.5})
    return f,f.time.iloc[-1]+pd.Timedelta(hours=1)


def test_only_closed_directional_body_confirms():
    f,now=sample()
    assert confirms(f,'buy',now) and not confirms(f,'sell',now)
    forming=f.iloc[-1:].copy();forming['time']=now;forming['close']=99.
    assert confirms(pd.concat([f,forming],ignore_index=True),'buy',now)
    f.loc[30,'close']=100.1
    assert not confirms(f,'buy',now)


def test_missing_stale_and_invalid_ohlc_fail_closed():
    f,now=sample()
    assert not confirms(f.iloc[:10],'buy',now)
    assert not confirms(f,'buy',now+pd.Timedelta(hours=4))
    f.loc[30,'low']=103.
    assert not confirms(f,'buy',now)
