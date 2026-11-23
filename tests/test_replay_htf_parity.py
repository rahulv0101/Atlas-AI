from dataclasses import replace
from types import SimpleNamespace
import pandas as pd
import pytest
from atlas_ai.config.settings import load_settings
from atlas_ai.testing import policy_replay as module
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant


@pytest.mark.parametrize('bias,expected',[('mixed','timing_discipline'),('flat','timing_discipline'),
    ('unknown','timing_discipline'),('buy','timing_discipline'),('sell','higher_timeframe_alignment')])
def test_only_opposing_directional_bias_blocks_before_timing(monkeypatch,tmp_path,bias,expected):
    cfg=replace(load_settings(),timeframe='M5',storage_dir=str(tmp_path),top_down_confluence_enabled=False,
        require_higher_tf_alignment=True,min_same_side_signals=1,backtest_initial_balance=100000.)
    fake=SimpleNamespace(_filter_weak_strategies=lambda signals,**kwargs:(signals,{}),
        _same_side_support_count=lambda *args:1,_strategy_to_setup_family=lambda _: 'continuation',
        allocator=SimpleNamespace(stats=lambda:{}))
    monkeypatch.setattr(module,'policy_trader',lambda *args:fake)
    monkeypatch.setattr(module,'historical_decision',lambda *args,**kwargs:{'timing_passed':False})
    monkeypatch.setattr(module.RiskManager,'evaluate',lambda *args:(True,''))
    frame=pd.DataFrame({'time':pd.date_range(end='2026-11-23T10:15Z',periods=265,freq='5min'),
        'open':100.,'high':101.,'low':99.,'close':100.,'spread':10.})
    i=250;at=frame.time.iloc[i]+pd.Timedelta(minutes=5)
    cache=[{'index':i,'available_at':at.isoformat(),'higher_tf_bias':bias,'regime':{},
        'signals':[{'strategy':'ema_crossover','side':'buy','confidence':.9,'stop_loss_points':100.,'take_profit_points':150.}]}]
    result=module.replay(frame,cache,cfg,BrokerSpec(.01,.01,1,1,.01,100,.01,2),ExitVariant('test',0,0),
        None,{'day_trades':6,'loss_streak':2,'daily_loss_percent':.6,'setup_family':'continuation','lot_cap':.01})
    assert result['rejections']=={expected:1}
