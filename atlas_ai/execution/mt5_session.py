"""Authenticate only when the terminal is not already on the configured session."""
from __future__ import annotations

import MetaTrader5 as mt5


def ensure_configured_session(*, login: int, password: str, server: str) -> bool:
    def matches(account) -> bool:
        return bool(
            account is not None
            and getattr(account, "login", None) == login
            and getattr(account, "server", None) == server
        )

    terminal = mt5.terminal_info()
    if terminal is not None and terminal.connected and matches(mt5.account_info()):
        # A redundant login can reset MT5's Algo Trading switch when its
        # account-change protection is enabled. Reuse the verified session.
        return True
    if not mt5.login(login=login, password=password, server=server):
        return False
    terminal = mt5.terminal_info()
    return bool(terminal is not None and terminal.connected and matches(mt5.account_info()))
