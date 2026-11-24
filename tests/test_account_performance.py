from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS
import pytest
from atlas_ai.risk.account_performance import calculate
from atlas_ai.trader import AtlasTrader

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)


def deal(ticket, kind, profit, at=NOW, **costs):
    return NS(ticket=ticket, type=kind, profit=profit, at=at,
              commission=costs.get('commission',0), swap=costs.get('swap',0), fee=costs.get('fee',0))


def pnl(balance, equity, deals, credit=0):
    return calculate(NS(balance=balance,equity=equity,credit=credit,currency='ZAR'),deals,NOW,lambda d:d.at)


def test_deposit_cannot_hide_loss_or_trigger_profit_target():
    result = pnl(19900,19900,[deal(1,2,10000),deal(2,1,-100)])
    assert result['day']['pnl_including_floating'] == -100
    assert result['day']['net_funding'] == 10000
    assert result['day']['loss_fraction'] == .01
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = NS(daily_profit_target_zar=1000)
    trader._account_pnl = result
    objective = trader._daily_profit_objective(19900,10000)
    assert not objective['reached'] and objective['remaining_zar'] == 1100


def test_withdrawal_is_not_loss_and_fees_are_not_ignored():
    result = pnl(5100,5120,[deal(1,2,-5000),deal(2,1,110,commission=-5,swap=-3,fee=-2)])
    assert result['day']['realized_pnl'] == 100
    assert result['day']['pnl_including_floating'] == 120
    assert result['day']['loss_fraction'] == 0


def test_credit_bonus_and_duplicate_or_unknown_evidence():
    assert pnl(10000,11000,[deal(1,3,1000)],credit=1000)['day']['pnl_including_floating'] == 0
    assert pnl(11000,11000,[deal(1,6,1000)])['day']['pnl_including_floating'] == 0
    for rows in (None,[deal(1,99,100)],[deal(1,13,0)],[deal(1,2,100),deal(1,2,100)]):
        with pytest.raises(ValueError): pnl(10000,10000,rows)


def test_day_and_week_reconstructed_independently_and_old_funding_not_subtracted_twice():
    rows=[deal(1,2,5000,NOW-timedelta(days=1)),deal(2,1,-200,NOW-timedelta(days=1)),deal(3,1,-100)]
    result=pnl(14700,14700,rows)
    assert result['day']['realized_pnl'] == -100 and result['day']['opening_balance'] == 14800
    assert result['week']['realized_pnl'] == -300 and result['week']['opening_balance'] == 10000
    assert result['week']['loss_fraction'] == .03


def test_unknown_profit_is_not_replaced_by_equity_increase():
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=NS(daily_profit_target_zar=1000)
    result=trader._daily_profit_objective(1000000,100)
    assert result['trading_pnl_zar'] is None and not result['reached']


def test_history_failure_blocks_risk_without_nonfinite_UI_values(monkeypatch):
    from atlas_ai.config.settings import Settings
    from atlas_ai.risk.risk_manager import RiskManager
    import json
    from dataclasses import asdict
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=Settings(0,'','')
    trader._load_guard_state=lambda flags: {}
    monkeypatch.setattr('atlas_ai.trader.mt5.account_info',lambda:NS(balance=20000.,equity=20000.,credit=0))
    monkeypatch.setattr('atlas_ai.trader.mt5.positions_get',lambda **kw:[])
    monkeypatch.setattr('atlas_ai.trader.mt5.symbol_info_tick',lambda symbol:None)
    monkeypatch.setattr('atlas_ai.trader.mt5.symbol_info',lambda symbol:None)
    monkeypatch.setattr('atlas_ai.trader.mt5.history_deals_get',lambda *args:None)
    snapshot=trader._risk_snapshot({})
    assert RiskManager(trader.settings).evaluate(snapshot)==(False,'Account cash-flow accounting unavailable')
    json.dumps(asdict(snapshot),allow_nan=False)


def test_cache_invalidates_immediately_on_balance_change(monkeypatch):
    from atlas_ai.config.settings import Settings
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=Settings(0,'','')
    calls=[]
    def history(*args): calls.append(args); return []
    monkeypatch.setattr('atlas_ai.trader.mt5.history_deals_get',history)
    account=NS(balance=10000.,equity=10000.,credit=0,login=1,server='demo')
    trader._account_performance(account);trader._account_performance(account)
    assert len(calls)==1
    account.balance=account.equity=20000.
    trader._account_performance(account)
    assert len(calls)==2
