from dataclasses import replace
from datetime import datetime,timezone
from types import SimpleNamespace
import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.data.top_down import TIMEFRAMES,MINUTES,closed_bars,collect,entry_gate
from atlas_ai.strategies.inventory import base_inventory
from atlas_ai.trader import AtlasTrader

NOW=pd.Timestamp('2026-11-13T12:03:00Z')


def candles(tf,side='buy'):
    delta=pd.Timedelta(minutes=MINUTES[tf]);last=NOW.floor('D') if tf=='D1' else NOW.floor(f'{MINUTES[tf]}min')
    ts=pd.date_range(end=last,periods=80,freq=delta)
    values=[2000+i*(1 if side=='buy' else -1) for i in range(80)]
    return pd.DataFrame({'time':ts,'open':values,'high':[v+2 for v in values],
        'low':[v-2 for v in values],'close':values})


class Feed:
    def __init__(self,opposite=None,broken=None):self.requested=[];self.opposite=opposite;self.broken=broken
    def get_rates_for_timeframe(self,tf,bars=90):
        self.requested.append(tf)
        if tf==self.broken:raise RuntimeError('terminal error')
        return candles(tf,'sell' if tf==self.opposite else 'buy')


def test_top_down_order_all_closed_and_directional_gate():
    f=Feed();ctx=collect(f,NOW)
    assert f.requested==list(TIMEFRAMES)
    assert ctx['aligned'] and ctx['bias']=='buy'
    assert entry_gate(ctx,'buy')['passed']
    assert not entry_gate(ctx,'sell')['passed']
    assert not entry_gate(ctx,'flat')['passed']
    assert ctx['evidence']['M15']['last_closed_bar_utc']=='2026-11-13T11:45:00+00:00'


@pytest.mark.parametrize('side', ['buy', 'sell'])
@pytest.mark.parametrize('d1', ['buy', 'sell', 'flat', 'unknown'])
@pytest.mark.parametrize('h1', ['buy', 'sell', 'flat', 'unknown'])
@pytest.mark.parametrize('h4', ['buy', 'sell', 'flat', 'unknown'])
@pytest.mark.parametrize('m15', ['buy', 'sell', 'flat', 'unknown'])
def test_bounded_confluence_truth_table(side, d1, h1, h4, m15):
    from atlas_ai.data.top_down import POLICY
    details = dict(D1=d1, H1=h1, H4=h4, M15=m15)
    ctx = dict(policy=POLICY, entry_timeframe='M5', closed_candles_only=True,
               details=details, evidence={tf: {'status': 'unavailable' if bias=='unknown' else 'available'}
                                         for tf, bias in details.items()})
    result = entry_gate(ctx, side)
    assert result['passed'] == (h1 == side)


def test_gate_rejects_invalid_context_and_unavailable_claimed_confirmation():
    ctx = collect(Feed(), NOW)
    for field, value in [('policy', 'old'), ('closed_candles_only', False), ('entry_timeframe', 'M1')]:
        assert not entry_gate({**ctx, field: value}, 'buy')['passed']
    ctx['evidence']['H1']['status'] = 'unavailable'
    assert not entry_gate(ctx, 'buy')['passed']


def test_forming_or_future_candles_cannot_change_bias():
    f=candles('M5');expected=closed_bars(f,'M5',NOW)
    f.loc[f.index[-1],'close']=99999
    assert closed_bars(f,'M5',NOW).equals(expected)
    assert expected.time.iloc[-1]==pd.Timestamp('2026-11-13T11:55:00Z')


def test_stale_insufficient_duplicate_and_invalid_closed_prices_fail():
    f=candles('M5')
    for bad in [f.iloc[:20],f.iloc[:-5],pd.concat([f,f.tail(1)])]:
        with pytest.raises(ValueError):closed_bars(bad,'M5',NOW)
    f.loc[f.index[-2],'close']=float('nan')
    with pytest.raises(ValueError,match='invalid_closed_prices'):closed_bars(f,'M5',NOW)


def test_daily_calendar_close_handles_broker_dst_boundary():
    # Athens daily 00:00 crosses the autumn 25-hour day.
    dates=pd.date_range('2026-09-20',periods=40,freq='D',tz='Europe/Athens').tz_convert('UTC')
    f=pd.DataFrame({'time':dates,'close':range(2000,2040)})
    now=pd.Timestamp('2026-10-25T21:30:00Z')  # still before broker midnight
    out=closed_bars(f,'D1',now,broker_timezone='Europe/Athens')
    assert out.time.iloc[-1].tz_convert('Europe/Athens').day==24


@pytest.mark.parametrize('date',['2026-11-16','2026-10-26'])
def test_monday_daily_reference_requires_current_forming_bar_and_handles_dst(date):
    monday=pd.Timestamp(date,tz='Europe/Athens')
    friday=monday-pd.DateOffset(days=3)
    dates=pd.date_range(end=friday,periods=50,freq='B').append(pd.DatetimeIndex([monday])).tz_convert('UTC')
    f=pd.DataFrame({'time':dates,'close':range(2000,2051)})
    now=(monday+pd.Timedelta(hours=8)).tz_convert('UTC')
    out=closed_bars(f,'D1',now,broker_timezone='Europe/Athens')
    assert out.time.iloc[-1]==friday.tz_convert('UTC')
    assert out.attrs['freshness_basis']=='weekend_confirmed_by_current_daily_bar'
    assert out.attrs['freshness_age_seconds']==8*3600
    f.loc[f.index[-1],'close']=999999
    assert closed_bars(f,'D1',now,broker_timezone='Europe/Athens').equals(out)
    with pytest.raises(ValueError,match='stale_closed_candles'):
        closed_bars(f.iloc[:-1],'D1',now,broker_timezone='Europe/Athens')
    # A future timestamp cannot establish that the feed has resumed.
    f.loc[f.index[-1],'time']=now+pd.Timedelta(hours=1)
    with pytest.raises(ValueError,match='stale_closed_candles'):
        closed_bars(f,'D1',now,broker_timezone='Europe/Athens')


def test_weekend_exception_does_not_accept_a_missing_friday_or_stuck_tuesday_feed():
    monday=pd.Timestamp('2026-11-16',tz='Europe/Athens')
    dates=pd.date_range(end=monday-pd.DateOffset(days=4),periods=50,freq='B').append(pd.DatetimeIndex([monday])).tz_convert('UTC')
    f=pd.DataFrame({'time':dates,'close':range(2000,2051)})
    with pytest.raises(ValueError,match='stale_closed_candles'):
        closed_bars(f,'D1',monday+pd.Timedelta(hours=8),broker_timezone='Europe/Athens')
    f.loc[f.index[-2],'time']=(monday-pd.DateOffset(days=3)).tz_convert('UTC')
    with pytest.raises(ValueError,match='stale_closed_candles'):
        closed_bars(f.iloc[:-1],'D1',monday+pd.Timedelta(days=1,hours=8),broker_timezone='Europe/Athens')


def test_m5_sweep_inventory_is_explicit_and_legacy_defaults_unchanged():
    assert 'gold_liquidity_sweep' not in {s.name for s in base_inventory('M5')}
    assert 'gold_liquidity_sweep' in {s.name for s in base_inventory('M5',top_down=True)}
    cfg=Settings(0,'','',timeframe='M1',top_down_confluence_enabled=True)
    with pytest.raises(ValueError,match='M5 entries'):AtlasTrader(cfg)


def test_live_context_uses_shared_top_down_collector(monkeypatch):
    t=AtlasTrader.__new__(AtlasTrader);t.settings=Settings(0,'','',timeframe='M5',top_down_confluence_enabled=True)
    t.feed=Feed();from atlas_ai.data import top_down
    real=top_down.collect
    monkeypatch.setattr(top_down,'collect',lambda feed,now,**kw:real(feed,NOW,**kw))
    assert t._higher_tf_context()['context_tfs']==list(TIMEFRAMES)


def test_single_frame_replays_cannot_claim_top_down_validation():
    from atlas_ai.backtest import Backtester
    from atlas_ai.testing.policy_replay import cache_candidates
    cfg=Settings(0,'','',timeframe='M5',top_down_confluence_enabled=True)
    with pytest.raises(ValueError,match='separate'):Backtester(settings=cfg).run(candles('M5'))
    with pytest.raises(ValueError,match='separate'):cache_candidates(candles('M5'),cfg,None)


def test_top_down_signal_path_does_not_load_legacy_evolved_or_chromosome_pools():
    from atlas_ai.models import TradeSignal
    from unittest.mock import Mock
    t=AtlasTrader.__new__(AtlasTrader)
    t.settings=Settings(0,'','',timeframe='M5',top_down_confluence_enabled=True)
    t.base_strategies=[SimpleNamespace(name='ema_crossover',generate_signal=lambda df:TradeSignal('ema_crossover','sell',.6,100.,150.))]
    t._load_evolved_strategy_pool=Mock(side_effect=AssertionError('M1 pool must not be reused'))
    t._load_chromosome_demo_pool=Mock(side_effect=AssertionError('M1 demo chromosomes must not be reused'))
    t.store=Mock();t._logged_evolved_fallback=False
    signals=t._build_signals(candles('M5'))
    assert len(signals)==1
    t._load_evolved_strategy_pool.assert_not_called()
    t._load_chromosome_demo_pool.assert_not_called()


def test_daily_feed_mapping_and_unsupported_timeframe_fail_without_terminal_access(monkeypatch):
    import MetaTrader5 as mt5
    from atlas_ai.data.market_data import MarketDataFeed,_TIMEFRAME_MAP
    assert _TIMEFRAME_MAP['D1']==mt5.TIMEFRAME_D1
    feed=MarketDataFeed(Settings(0,'',''))
    monkeypatch.setattr(feed,'_ensure_initialized',lambda:pytest.fail('must validate before terminal access'))
    with pytest.raises(ValueError,match='Unsupported'):feed.get_rates_for_timeframe('BAD')


def test_live_confluence_changes_do_not_rewrite_frozen_smc_research_hypothesis():
    from atlas_ai.strategies.smc_research_confluence import entry_gate as research_gate
    ctx=collect(Feed(opposite='D1'),NOW)
    assert entry_gate(ctx,'buy')['passed']
    assert not research_gate(ctx,'buy')['passed']
    ctx=collect(Feed(opposite='H1'),NOW)
    assert not entry_gate(ctx,'buy')['passed']
    assert not research_gate(ctx,'buy')['passed']


def test_h1_drives_bias_when_context_timeframes_disagree():
    ctx = collect(Feed(opposite='H1'), NOW)
    assert ctx['bias'] == 'sell' and ctx['confirm_tf'] == 'H1'
    assert ctx['all_timeframes_bias'] == 'mixed'
    assert entry_gate(ctx, 'sell')['passed']
    for tf in ('D1', 'H4', 'M15'):
        ctx['evidence'][tf]['status'] = 'unavailable'
    assert entry_gate(ctx, 'sell')['passed']
    assert not entry_gate(collect(Feed(broken='H1'), NOW), 'buy')['passed']
