from types import SimpleNamespace
import pandas as pd
from atlas_ai.config.settings import Settings
from test_h1_m5_retest_timing import sample
from tools.test_complete_retest_setup import generate, NAME


def test_complete_setup_uses_closed_confirmation_and_h1_then_next_bar(monkeypatch):
    f,_,now=sample('buy')
    previous=f.iloc[:1].copy()
    prefix=pd.concat([previous]*256,ignore_index=True)
    prefix['time']=pd.date_range(f.time.iloc[0]-pd.Timedelta(minutes=256*5),periods=256,freq='5min')
    forming=f.iloc[-1:].copy();forming['time']=now
    frame=pd.concat([prefix,f,forming],ignore_index=True)
    h1=pd.DataFrame({'time':pd.date_range(now.floor('h')-pd.Timedelta(hours=60),periods=61,freq='h'),
                     'close':[100+i for i in range(61)]})
    cfg=Settings(1,'','Demo',timeframe='M5')
    monkeypatch.setattr('tools.test_complete_retest_setup.policy_trader',lambda *a:SimpleNamespace(_market_regime=lambda x:'trending'))
    def run():return generate(frame,h1,cfg,now,now+pd.Timedelta(minutes=1),lambda **k:None)[0]
    rows=run()
    assert len(rows)==1 and rows[0]['available_at']==now.isoformat()
    assert rows[0]['signals'][0]['strategy']==NAME
    assert rows[0]['signals'][0]['take_profit_points']==2*rows[0]['signals'][0]['stop_loss_points']
    frame.loc[len(frame)-1,['open','high','low','close']]=[1000,2000,1,1500]
    assert run()==rows
    h1['close']=list(reversed(h1.close.tolist()))
    assert run()==[]
