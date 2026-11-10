from types import SimpleNamespace as NS
import MetaTrader5 as mt5
from tools.demo_lifecycle_diagnostic import balanced,linked_position_ids,protective


def fill(**kwargs):
    d=dict(position_id=1,order=10,ticket=20,entry=mt5.DEAL_ENTRY_IN,type=mt5.DEAL_TYPE_BUY,volume=.01,symbol="XAUUSD",magic=77)
    d.update(kwargs);return NS(**d)


def test_position_link_requires_exact_broker_reference_symbol_and_magic():
    s=NS(symbol="XAUUSD",magic_number=77)
    assert linked_position_ids([fill()],"10",s)=={1}
    assert linked_position_ids([fill(order=11,ticket=21)],"10",s)==set()
    assert linked_position_ids([fill(magic=1)],"10",s)==set()


def test_balanced_broker_fills_require_complete_opposite_exit():
    entry=fill();out=fill(entry=mt5.DEAL_ENTRY_OUT,type=mt5.DEAL_TYPE_SELL)
    assert balanced([entry,out],{1})
    assert not balanced([entry],{1})
    assert not balanced([entry,fill(entry=mt5.DEAL_ENTRY_OUT,volume=.005,type=mt5.DEAL_TYPE_SELL)],{1})
    assert not balanced([entry,fill(entry=mt5.DEAL_ENTRY_OUT)],{1})
    assert not balanced([entry,out],set())


def test_protective_readback_needs_valid_sided_stops():
    assert protective(NS(type=mt5.POSITION_TYPE_BUY,sl=1999,tp=2002,price_current=2000))
    assert not protective(NS(type=mt5.POSITION_TYPE_BUY,sl=0,tp=2002,price_current=2000))
    assert not protective(NS(type=mt5.POSITION_TYPE_BUY,sl=2001,tp=2002,price_current=2000))
