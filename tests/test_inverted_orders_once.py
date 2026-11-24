from types import SimpleNamespace
import pytest
from atlas_ai.models import TradeSignal
from tools import backtest_inverted_orders_once as study


@pytest.mark.parametrize('side,opposite',[('buy','sell'),('sell','buy')])
def test_only_submitted_side_is_inverted_without_mutating_detection(monkeypatch,side,opposite):
    signal=TradeSignal('ema_crossover',side,.8,100.,150.)
    observed=[]
    def simulated(frame,index,order,*args,**kw):
        observed.append(order)
        return {'net_cash':-1.,'exit_reason':'stop_loss'}
    monkeypatch.setattr(study,'simulate',simulated)
    result=study.inverted_simulation(None,3,signal,.01,None,None,None,last_index=8)
    assert signal.side==side
    assert observed[0].side==opposite
    assert observed[0].stop_loss_points==100 and observed[0].take_profit_points==150
    assert observed[0].confidence==.8 and observed[0].strategy=='ema_crossover'
    assert result['detected_side']==side and result['executed_side']==opposite


def test_flat_cannot_become_an_order():
    with pytest.raises(ValueError,match='directional_signal'):
        study.inverted_simulation(None,0,TradeSignal('ema','flat',0,100,150))


def test_real_simulator_uses_opposite_quote_and_does_not_negate_PnL():
    import pandas as pd
    from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant,simulate
    frame=pd.DataFrame({'open':[100.,100.],'high':[100.5,100.5],
                        'low':[99.5,99.5],'close':[100.,100.],'spread':[20.,20.]})
    spec=BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2)
    cfg=SimpleNamespace(backtest_max_hold_bars=2,backtest_break_even_r_trigger=1.,
        backtest_trailing_r_trigger=2.,backtest_trailing_buffer_r=.5,
        backtest_stale_exit_bars=10,backtest_stale_min_progress_r=.2)
    signal=TradeSignal('ema','buy',.8,100.,150.)
    args=(frame,0,signal,.01,spec,cfg,ExitVariant('configured',0.,3.))
    normal=simulate(*args);reverse=study.inverted_simulation(*args)
    assert normal['entry_price']==pytest.approx(100.23)
    assert reverse['entry_price']==pytest.approx(99.97)
    assert normal['net_cash']<0 and reverse['net_cash']<0
