from dataclasses import asdict
import pandas as pd
from atlas_ai.config.settings import Settings
from atlas_ai.models import TradeSignal
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant,simulate
from tools.retest_exit_research import hypothesis


def test_hypothesis_changes_only_two_exit_triggers():
    cfg=Settings(1,'','Demo',backtest_break_even_r_trigger=1.,backtest_trailing_r_trigger=1.4)
    changed=hypothesis(cfg)
    assert {k for k,v in asdict(cfg).items() if v!=asdict(changed)[k]}=={
        'backtest_break_even_r_trigger','backtest_trailing_r_trigger'}
    assert changed.max_risk_per_trade==cfg.max_risk_per_trade


def test_counterfactual_retains_initial_stop_but_can_allow_target_followthrough():
    cfg=Settings(1,'','Demo',backtest_max_hold_bars=10,backtest_stale_exit_bars=20,
                 backtest_break_even_r_trigger=1.,backtest_break_even_lock_r=.05,backtest_trailing_r_trigger=1.4)
    frame=pd.DataFrame({'open':[100.,100.5,100.5],'high':[101.2,101.,102.1],
                        'low':[99.8,100.,100.2],'close':[100.5,100.5,102.],'spread':[0.,0.,0.]})
    spec=BrokerSpec(.01,.01,1.,1.,.01,100.,.01,2)
    signal=TradeSignal('research','buy',.7,100.,200.)
    def run(settings):return simulate(frame,0,signal,.01,spec,settings,ExitVariant('test',.05,0.))
    baseline,changed=run(cfg),run(hypothesis(cfg))
    assert baseline['net_r']<.1 and changed['net_r']==2.
    frame.loc[0,'low']=98.9
    assert run(cfg)['net_r']==run(hypothesis(cfg))['net_r']==-1.
