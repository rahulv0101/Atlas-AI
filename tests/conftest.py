"""Tests must explicitly mock broker mutations and OS process termination."""
import MetaTrader5 as mt5
import pytest


@pytest.fixture(autouse=True)
def forbid_unmocked_broker_operations(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real MT5 initialization, login, or order submission is forbidden in tests; supply an explicit fake")

    for name in ("initialize", "login", "order_send"):
        monkeypatch.setattr(mt5, name, blocked)


@pytest.fixture(autouse=True)
def forbid_unmocked_process_termination(monkeypatch):
    from atlas_ai import atlas_process_guard

    def blocked(*args, **kwargs):
        raise AssertionError("Real process termination is forbidden in tests; supply an explicit fake")

    monkeypatch.setattr(atlas_process_guard, "_terminate_process_windows", blocked)
