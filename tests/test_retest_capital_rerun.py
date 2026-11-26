from types import SimpleNamespace
import pytest
from tools import retest_capital_rerun as module


def setup(monkeypatch, **changes):
    cfg=SimpleNamespace(hfm_login=1,hfm_server='Demo')
    account=SimpleNamespace(login=1,server='Demo',trade_mode=module.mt5.ACCOUNT_TRADE_MODE_DEMO,
                            balance=12345.,currency='ZAR')
    for name,value in changes.items():setattr(account,name,value)
    monkeypatch.setattr(module,'load_settings',lambda:cfg)
    monkeypatch.setattr(module,'MarketDataFeed',lambda cfg:SimpleNamespace(_ensure_initialized=lambda:None))
    monkeypatch.setattr(module.mt5,'account_info',lambda:account)
    shutdown=[];monkeypatch.setattr(module.mt5,'shutdown',lambda:shutdown.append(True))
    return shutdown


def test_capital_snapshot_uses_matched_demo_balance(monkeypatch):
    closed=setup(monkeypatch)
    assert module.capture_capital()['balance']==12345.
    assert closed==[True]


@pytest.mark.parametrize('change',[{'login':2},{'trade_mode':-1},{'currency':'USD'},{'balance':float('nan')},{'balance':0.}])
def test_wrong_scope_or_invalid_capital_fails_closed(monkeypatch,change):
    closed=setup(monkeypatch,**change)
    with pytest.raises(ValueError):module.capture_capital()
    assert closed==[True]
