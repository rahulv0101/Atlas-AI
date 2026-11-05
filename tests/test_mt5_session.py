from types import SimpleNamespace

import pytest

from atlas_ai.execution import mt5_session


@pytest.mark.parametrize("connected,login,server", [
    (False, 123, "Demo"), (True, 456, "Demo"), (True, 123, "Other"),
])
def test_other_or_disconnected_session_requires_login(monkeypatch, connected, login, server):
    state = {"connected": connected, "login": login, "server": server}
    calls = []
    monkeypatch.setattr(mt5_session.mt5, "terminal_info", lambda: SimpleNamespace(connected=state["connected"]))
    monkeypatch.setattr(mt5_session.mt5, "account_info", lambda: SimpleNamespace(login=state["login"], server=state["server"]))

    def authorize(**kwargs):
        calls.append(kwargs)
        state.update(connected=True, login=123, server="Demo")
        return True

    monkeypatch.setattr(mt5_session.mt5, "login", authorize)
    assert mt5_session.ensure_configured_session(login=123, password="test", server="Demo")
    assert len(calls) == 1


def test_matching_connected_session_does_not_login_or_toggle_trading(monkeypatch):
    monkeypatch.setattr(mt5_session.mt5, "terminal_info", lambda: SimpleNamespace(connected=True, trade_allowed=False))
    monkeypatch.setattr(mt5_session.mt5, "account_info", lambda: SimpleNamespace(login=123, server="Demo"))
    # The suite's broker guard rejects any actual login. Reusing a session must
    # also leave a deliberately disabled Algo Trading switch untouched.
    assert mt5_session.ensure_configured_session(login=123, password="test", server="Demo")


@pytest.mark.parametrize("authorized", [False, True])
def test_login_failure_or_wrong_returned_identity_is_not_authorized(monkeypatch, authorized):
    monkeypatch.setattr(mt5_session.mt5, "terminal_info", lambda: SimpleNamespace(connected=True))
    monkeypatch.setattr(mt5_session.mt5, "account_info", lambda: SimpleNamespace(login=456, server="Demo"))
    monkeypatch.setattr(mt5_session.mt5, "login", lambda **kwargs: authorized)
    assert not mt5_session.ensure_configured_session(login=123, password="test", server="Demo")


@pytest.mark.parametrize("trade_allowed", [True, False])
@pytest.mark.parametrize("caller", ["readiness", "connector"])
def test_startup_paths_reuse_session_and_preserve_algo_switch(monkeypatch, trade_allowed, caller):
    from atlas_ai import atlas_process_guard as guard
    from atlas_ai.execution.broker import HFMConnector

    settings = SimpleNamespace(hfm_login=123, hfm_password="test", hfm_server="Demo", hfm_terminal_path="terminal64.exe", symbol="XAUUSD")
    terminal = SimpleNamespace(connected=True, trade_allowed=trade_allowed)
    monkeypatch.setattr(mt5_session.mt5, "initialize", lambda **kwargs: True)
    monkeypatch.setattr(mt5_session.mt5, "terminal_info", lambda: terminal)
    monkeypatch.setattr(mt5_session.mt5, "account_info", lambda: SimpleNamespace(login=123, server="Demo"))
    monkeypatch.setattr(mt5_session.mt5, "shutdown", lambda: None)
    monkeypatch.setattr(mt5_session.mt5, "symbol_select", lambda *args: True)
    monkeypatch.setattr(mt5_session.mt5, "copy_rates_from_pos", lambda *args: [1, 2, 3])
    monkeypatch.setattr(guard.time, "sleep", lambda *args: None)
    if caller == "readiness":
        monkeypatch.setattr(guard, "load_settings", lambda: settings)
        assert guard.is_mt5_ready(SimpleNamespace(mt5_executable_path="terminal64.exe")) == (
            (True, "mt5_ready") if trade_allowed else (False, "autotrading_disabled")
        )
    else:
        connector = HFMConnector(settings)
        monkeypatch.setattr(connector, "_acquire_broker_mutex", lambda: None)
        monkeypatch.setattr(connector, "_release_broker_mutex", lambda: None)
        monkeypatch.setattr(connector, "_launch_hfm_terminal", lambda: None)
        if trade_allowed:
            connector.connect()
        else:
            with pytest.raises(RuntimeError, match="AutoTrading is disabled"):
                connector.connect()
    assert terminal.trade_allowed is trade_allowed
