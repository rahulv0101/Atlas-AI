from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.models import TradeSignal
from atlas_ai.testing import policy_replay as policy
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.data.top_down import collect


def candles(start, periods, freq):
    price=pd.Series(range(periods),dtype=float)+2000
    return pd.DataFrame({'time':pd.date_range(start,periods=periods,freq=freq),
        'open':price,'high':price+2,'low':price-2,'close':price+1,'spread':10,'tick_volume':100})


def test_m5_candidates_use_five_minute_close_and_native_completed_evidence(monkeypatch):
    settings=Settings(1,'x','demo',timeframe='M5',top_down_confluence_enabled=True)
    frame=candles('2026-11-10',255,'5min')
    native={tf:candles('2026-07-01',n,freq) for tf,n,freq in
            [('D1',150,'D'),('H4',900,'4h'),('H1',3600,'h'),('M15',14400,'15min')]}
    fake=SimpleNamespace(_strategy_enabled=lambda name:True,
        _signal_generation_context=lambda f,t:{},_sanitize_signal=lambda s:s,
        _apply_signal_generation_gating=lambda s,c:s,_market_regime=lambda c:{})
    monkeypatch.setattr(policy,'policy_trader',lambda *a:fake)
    inventory=Mock(side_effect=lambda tf,**kw:[SimpleNamespace(name='test',
        generate_signal=lambda f:TradeSignal('test','buy',.8,100,200))])
    monkeypatch.setattr(policy,'base_inventory',inventory)
    rows,counts,names=policy.cache_candidates(frame,settings,None,native_frames=native)
    assert len(rows)==4 and names==['test']
    inventory.assert_called_once_with('M5',top_down=True)
    for row in rows:
        at=pd.Timestamp(row['available_at'])
        assert at==pd.Timestamp(frame.time.iloc[row['index']],tz='UTC')+pd.Timedelta(minutes=5)
        # Independent direct collection at that time must match cached native context.
        feed=HistoricalFeed(native);feed.now=at
        direct=collect(feed,at,broker_timezone=settings.mt5_server_timezone or 'UTC')
        assert row['higher_context']['details']==direct['details']
        for tf,evidence in row['higher_context']['evidence'].items():
            assert evidence['status']=='available'
            assert pd.Timestamp(evidence['last_closed_bar_utc'])<at
    assert counts['test:gated_directional']==4


def test_top_down_replay_cannot_fall_back_to_single_frame():
    settings=Settings(1,'x','demo',timeframe='M5',top_down_confluence_enabled=True)
    with pytest.raises(ValueError,match='separate higher-timeframe'):
        policy.cache_candidates(candles('2026-11-10',255,'5min'),settings,None)
    with pytest.raises(ValueError,match='all_native'):
        policy.cache_candidates(candles('2026-11-10',255,'5min'),settings,None,native_frames={})


def test_missing_native_confluence_blocks_before_historical_decision(monkeypatch):
    from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
    settings=Settings(1,'x','demo',timeframe='M5',top_down_confluence_enabled=True,
                      require_higher_tf_alignment=False)
    frame=candles('2026-11-10T09:00',20,'5min')
    cache=[{'index':1,'available_at':'2026-11-10T09:10:00+00:00','regime':{},'higher_tf_bias':'buy',
        'signals':[{'strategy':'ema_crossover','side':'buy','confidence':.8,'stop_loss_points':100,'take_profit_points':200}]}]
    fake=SimpleNamespace(_filter_weak_strategies=lambda s,**kw:(s,{}),allocator=SimpleNamespace(stats=lambda:{}))
    monkeypatch.setattr(policy,'policy_trader',lambda *a:fake)
    denied=Mock(side_effect=AssertionError('Confluence must reject before decision synthesis'))
    monkeypatch.setattr(policy,'historical_decision',denied)
    spec=BrokerSpec(.01,.01,1,1,.01,100,.01,2)
    result=policy.replay(frame,cache,settings,spec,ExitVariant('test',0,0),None,
        {'day_trades':6,'loss_streak':2,'daily_loss_percent':.6,'lot_cap':.01,'setup_family':'continuation'})
    assert result['rejections']=={'higher_timeframe_confluence':1}
    assert result['trades']==0 and result['orders_sent']==0
    denied.assert_not_called()


def test_m5_portfolio_uses_five_minute_execution_intervals_and_sixty_minute_horizon(tmp_path,monkeypatch):
    from atlas_ai.data.top_down import POLICY,TIMEFRAMES
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
    from atlas_ai.testing import historical_decision as decisions
    from atlas_ai.trader import AtlasTrader
    settings=Settings(1,'x','demo',timeframe='M5',top_down_confluence_enabled=True,
        min_same_side_signals=1,backtest_max_hold_bars=12,backtest_stale_min_progress_r=0)
    frame=candles('2026-11-09T12:10',300,'5min')
    frame[['open','close']]=100.;frame['high']=100.01;frame['low']=99.99;frame['spread']=0.
    at=pd.Timestamp(frame.time.iloc[250],tz='UTC')+pd.Timedelta(minutes=5)
    row={'index':250,'available_at':at.isoformat(),
         'regime':{'name':'trend','trend_strength':.3,'volatility_pct':.05},'higher_tf_bias':'buy',
         'higher_context':{'policy':POLICY,'entry_timeframe':'M5','closed_candles_only':True,
                           'details':{tf:'buy' for tf in TIMEFRAMES},'bias':'buy'},
         'signals':[{'strategy':'ema_crossover','side':'buy','confidence':.99,'stop_loss_points':100,'take_profit_points':1000}]}
    monkeypatch.setattr(AtlasTrader,'_timing_discipline_snapshot',lambda *a,**kw:{'passed':True})
    monkeypatch.setattr(decisions,'build_structured_decision_analysis',lambda **kw:{'confidence_score':99})
    result=policy.replay(frame,[row],settings,BrokerSpec(.01,.01,1,1,.01,100,.01,2),
        ExitVariant('test',0,0),KnowledgeStore(str(tmp_path)),
        {'day_trades':6,'loss_streak':2,'daily_loss_percent':.6,'lot_cap':.01,'setup_family':'continuation'})
    assert result['trades']==1
    trade=result['trade_list'][0]
    assert trade['exit_bar']-trade['entry_bar']+1==12 and trade['exit_reason']=='max_hold'
    assert pd.Timestamp(trade['exit_at'])-pd.Timestamp(trade['entry_at'])==pd.Timedelta(minutes=55)
    assert result['orders_sent']==0 and trade['broker_fill'] is False
