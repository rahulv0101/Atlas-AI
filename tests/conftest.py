"""Unit/integration tests must explicitly mock every mutating broker operation."""
import MetaTrader5 as mt5
import pytest


@pytest.fixture(autouse=True)
def forbid_unmocked_broker_operations(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real MT5 initialization, login, or order submission is forbidden in tests; supply an explicit fake")

    for name in ("initialize", "login", "order_send"):
        monkeypatch.setattr(mt5, name, blocked)
