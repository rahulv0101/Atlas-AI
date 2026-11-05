from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import MetaTrader5 as mt5
import pytest

from atlas_ai.config.settings import Settings
from tools.recover_broker_history import recover_history


def setup(monkeypatch, login=1):
    monkeypatch.setattr(mt5,"initialize",lambda **kw:True)
    monkeypatch.setattr(mt5,"account_info",lambda:SimpleNamespace(login=login,server="Demo",trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO))


def test_wrong_account_cannot_supply_recovery_evidence(monkeypatch):
    setup(monkeypatch,login=2)
    query=Mock();monkeypatch.setattr(mt5,"history_deals_get",query)
    with pytest.raises(RuntimeError,match="matching configured"):
        recover_history(Settings(1,"test","Demo"))
    query.assert_not_called()


def test_recovery_deduplicates_owned_fills_without_claiming_original_journal(monkeypatch):
    setup(monkeypatch)
    settings=Settings(1,"test","Demo")
    now=datetime(2026,11,5,8,tzinfo=timezone.utc)
    row=SimpleNamespace(ticket=10,order=20,position_id=30,time=now.timestamp()-60,entry=1,type=1,symbol=settings.symbol,magic=settings.magic_number,volume=.01,price=3000,profit=2,commission=-.1,swap=0)
    other=SimpleNamespace(**{**vars(row),"ticket":11,"magic":999})
    monkeypatch.setattr(mt5,"history_deals_get",lambda *args:[row,row,other])
    result=recover_history(settings,end=now)
    assert result["owned_fill_records_recovered"]==1
    assert not result["original_journal_recovered"]
    assert result["orders_sent"]==0
    assert result["fills"][0]["net_profit"]==pytest.approx(1.9)


def test_unavailable_broker_history_is_not_zero_trade_evidence(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(mt5,"history_deals_get",lambda *args:None)
    with pytest.raises(RuntimeError,match="unavailable"):
        recover_history(Settings(1,"test","Demo"))
