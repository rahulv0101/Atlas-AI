from types import SimpleNamespace as NS
import MetaTrader5 as mt5
import pytest
from atlas_ai.config.settings import Settings
from atlas_ai.risk.risk_manager import RiskSnapshot
from atlas_ai.trader import AtlasTrader


@pytest.mark.parametrize("connected,login,visible,ready",[(True,1,True,True),(False,1,True,False),(True,2,True,False),(True,1,False,True)])
def test_cutoff_preserves_fresh_broker_risk_and_ai_evidence(monkeypatch,connected,login,visible,ready):
    trader=AtlasTrader.__new__(AtlasTrader)
    trader.settings=Settings(hfm_login=1,hfm_password="test",hfm_server="Demo",symbol="XAUUSD",timeframe="M1")
    trader.gemini=NS(enabled=True,health_summary=lambda:{"enabled":True})
    trader._intraday_exit_status={"entries_blocked":True,"flat_verified":True,"session":"asia"}
    trader._risk_snapshot=lambda flags:RiskSnapshot(9995,9995,.0005,0,30,.0005)
    monkeypatch.setattr(mt5,"terminal_info",lambda:NS(connected=connected))
    monkeypatch.setattr(mt5,"account_info",lambda:NS(login=login,server="Demo",trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO))
    monkeypatch.setattr(mt5,"symbol_info",lambda symbol:NS(visible=visible))
    result=trader._session_cutoff_status({"risk_guard_state":{"start_balance":10000,"trades_today":1}},execute_trades=True,gemini_influence_enabled=False)
    assert result["health"]["broker"]["connected"] is ready
    assert result["health"]["broker"]["symbol_selected"] is visible
    assert result["risk"]["equity"]==9995 and result["risk"]["daily_profit_zar"]==-5
    assert result["gemini_enabled"] and result["action"]=="hold"
    from atlas_ai.system_health import build_system_health
    health=build_system_health(result,trader.settings,{"execute_trades":True})
    assert health["broker_connectivity_status"]["connected"] is ready
    assert "Session cutoff" in result["message"]


def test_broker_read_failure_does_not_invent_connection(monkeypatch):
    trader=AtlasTrader.__new__(AtlasTrader);trader.settings=NS(symbol="XAUUSD")
    def fail():raise RuntimeError("IPC")
    monkeypatch.setattr(mt5,"terminal_info",fail)
    assert trader._broker_status_snapshot()["connected"] is False
