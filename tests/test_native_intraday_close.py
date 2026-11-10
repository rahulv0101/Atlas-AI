from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock
import MetaTrader5 as mt5
import pytest
from atlas_ai.config.settings import Settings
from atlas_ai.execution.trade_executor import TradeExecutor
from atlas_ai.execution.mt5_broker_adapter import MT5BrokerAdapter


@pytest.fixture
def transport(monkeypatch):
    settings=Settings(hfm_login=1,hfm_password="test",hfm_server="Demo",execute_trades=True)
    adapter=MT5BrokerAdapter(TradeExecutor(settings))
    pos=NS(ticket=10,symbol=settings.symbol,magic=settings.magic_number,comment="AAI_Ddemo_Sema",type=mt5.POSITION_TYPE_BUY,volume=.01)
    rows=[pos]
    monkeypatch.setattr(mt5,"terminal_info",lambda:NS(connected=True,trade_allowed=True,tradeapi_disabled=False))
    monkeypatch.setattr(mt5,"account_info",lambda:NS(login=1,server="Demo",trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO))
    monkeypatch.setattr(mt5,"positions_get",lambda **kwargs:rows[:])
    monkeypatch.setattr(mt5,"symbol_info_tick",lambda _:NS(bid=2000,ask=2000.2))
    monkeypatch.setattr(mt5,"symbol_info",lambda _:NS(filling_mode=2))
    monkeypatch.setattr(mt5,"order_check",lambda _:NS(retcode=0))
    def send(req):
        rows.clear()
        return NS(retcode=mt5.TRADE_RETCODE_DONE)
    sender=Mock(side_effect=send);monkeypatch.setattr(mt5,"order_send",sender)
    return adapter,pos,rows,sender


def test_native_close_is_position_specific_and_broker_confirmed(transport):
    adapter,pos,rows,sender=transport
    result=adapter.close_position(position_id="10")
    assert result.ok and result.status=="closed"
    request=sender.call_args.args[0]
    assert request["position"]==10 and request["type"]==mt5.ORDER_TYPE_SELL and request["volume"]==.01
    assert sender.call_count==1


@pytest.mark.parametrize("change",["magic","comment","symbol","real","account","disabled"])
def test_close_refuses_unowned_or_unauthorized_position(transport,monkeypatch,change):
    adapter,pos,rows,sender=transport
    if change=="magic":pos.magic+=1
    if change=="comment":pos.comment="manual"
    if change=="symbol":pos.symbol="EURUSD"
    if change=="real":monkeypatch.setattr(mt5,"account_info",lambda:NS(login=1,server="Demo",trade_mode=mt5.ACCOUNT_TRADE_MODE_REAL))
    if change=="account":monkeypatch.setattr(mt5,"account_info",lambda:NS(login=2,server="Demo",trade_mode=0))
    if change=="disabled":adapter._executor.settings=replace(adapter._executor.settings,execute_trades=False)
    assert not adapter.close_position(position_id="10").ok
    sender.assert_not_called()


@pytest.mark.parametrize("response",[None,RuntimeError("IPC"),NS(retcode=mt5.TRADE_RETCODE_TIMEOUT),NS(retcode=mt5.TRADE_RETCODE_DONE)])
def test_close_acceptance_is_not_flat_confirmation_and_never_retries(transport,response):
    adapter,pos,rows,sender=transport
    sender.side_effect=response if isinstance(response,Exception) else None
    sender.return_value=response
    result=adapter.close_position(position_id="10")
    assert not result.ok and result.status=="unknown"
    sender.assert_called_once()


def test_missing_inventory_cannot_confirm_flat(transport,monkeypatch):
    adapter,pos,rows,sender=transport
    monkeypatch.setattr(mt5,"positions_get",lambda **kwargs:None)
    assert not adapter.close_position(position_id="10").ok
    sender.assert_not_called()


def test_account_change_during_precheck_prevents_close(transport,monkeypatch):
    adapter,pos,rows,sender=transport
    def check(request):
        monkeypatch.setattr(mt5,"account_info",lambda:NS(login=2,server="Demo",trade_mode=0))
        return NS(retcode=0)
    monkeypatch.setattr(mt5,"order_check",check)
    assert not adapter.close_position(position_id="10").ok
    sender.assert_not_called()
