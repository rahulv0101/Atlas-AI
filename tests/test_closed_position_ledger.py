from copy import deepcopy
import json
from types import SimpleNamespace as NS

import MetaTrader5 as mt5
import pytest

from atlas_ai.learning.closed_position_ledger import ClosedPositionLedger


@pytest.fixture
def setup(tmp_path):
    settings = NS(storage_dir=tmp_path, hfm_login=123, hfm_server="demo", symbol="XAUUSD",
                  magic_number=77, mt5_server_timezone="UTC")
    account = NS(login=123, server="demo", trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO, currency="USD")
    ledger = ClosedPositionLedger(settings)
    return ledger, account


def fill(ticket=1, position=10, entry=0, volume=1.0, profit=0.0, **extra):
    fields = dict(ticket=ticket, position_id=position, order=100 + ticket, entry=entry,
                  type=mt5.DEAL_TYPE_BUY if entry == 0 else mt5.DEAL_TYPE_SELL,
                  volume=volume, price=2000.0, profit=profit, commission=-1.0, swap=0.0,
                  fee=0.0, time=1700000000 + ticket, magic=77, symbol="XAUUSD", comment="AAI_Dabcdef_Semax")
    fields.update(extra)
    return NS(**fields)


def event(**extra):
    meta = dict(request_origin="trader_guarded", execution_success=True, execution_mode="demo",
                strategy="ema_crossover", decision_id="abcdef123456", broker_order_id="101")
    meta.update(extra)
    return {"type": "decision_sample", "meta": meta}


def ingest(setup, deals, events=None, positions=()):
    ledger, account = setup
    return ledger.ingest_broker_snapshot(account=account, deals=deals, positions=positions,
                                         decision_events=[event()] if events is None else events)


def test_partial_fills_are_one_net_outcome_and_idempotent(setup):
    deals = [fill(1, volume=.5), fill(2, volume=.5), fill(3, entry=1, volume=.25, profit=4),
             fill(4, entry=1, volume=.75, profit=8, swap=-.5, fee=-.5)]
    result = ingest(setup, list(reversed(deals)))
    assert result["closed_positions"] == result["strict_strategy_positions"] == 1
    assert result["strategy_statistics"]["ema_crossover"] == dict(wins=1, losses=0, draws=0, closed_positions=1, pnl=7.0)
    assert ingest(setup, deals) == {**result, "updated_at": setup[0].snapshot()["updated_at"]}
    assert setup[0].snapshot()["broker_fill_count"] == 4


@pytest.mark.parametrize("changes,expected", [
    ({"positions": [NS(identifier=10, ticket=99, symbol="XAUUSD")]}, "broker_reports_open"),
    ({"deals": [fill(2, entry=1)]}, "incomplete"),
    ({"deals": [fill(), fill(2, entry=1, volume=2)]}, "missing_entry_volume"),
    ({"deals": [fill(), fill(2, entry=2)]}, "reversal_excluded"),
    ({"deals": [fill(time=1700000005), fill(2, entry=1)]}, "invalid_fill_sequence_excluded"),
])
def test_nonclosed_evidence_excluded(setup, changes, expected):
    result = ingest(setup, **{**dict(deals=[fill(), fill(2, entry=1)]), **changes})
    assert result["position_states"] == {expected: 1}
    assert result["strict_strategy_positions"] == 0


@pytest.mark.parametrize("meta", [dict(execution_mode="paper"), dict(request_origin="manual"), dict(execution_success=False)])
def test_unproven_decisions_are_not_strict_evidence(setup, meta):
    result = ingest(setup, [fill(), fill(2, entry=1)], [event(**meta)])
    assert result["closed_positions"] == 1
    assert result["strict_strategy_positions"] == 0


def test_ambiguous_short_id_downgrades_previously_linked_entry(setup):
    deals = [fill(order=999), fill(2, entry=1)]
    assert ingest(setup, deals)["strict_strategy_positions"] == 1
    result = ingest(setup, deals, [event(), event(decision_id="abcdefdifferent", broker_order_id="888")])
    assert result["strict_strategy_positions"] == 0


def test_manual_tests_never_count_even_with_decision_link(setup):
    result = ingest(setup, [fill(comment="manual_broker_test"), fill(2, entry=1)])
    assert result["manual_test_positions"] == 1
    assert result["strict_strategy_positions"] == 0
    result = ingest(setup, [fill(comment=""), fill(2, entry=1)])
    assert result["manual_test_positions"] == 1
    assert result["strict_strategy_positions"] == 0


def test_narrow_journal_query_preserves_known_decision_link(setup):
    deals = [fill(), fill(2, entry=1)]
    ingest(setup, deals)
    assert ingest(setup, deals, [])["strict_strategy_positions"] == 1


@pytest.mark.parametrize("field,value", [("login", 456), ("server", "other"), ("trade_mode", mt5.ACCOUNT_TRADE_MODE_REAL)])
def test_wrong_account_cannot_write(setup, field, value):
    ledger, account = setup
    setattr(account, field, value)
    with pytest.raises(ValueError):
        ingest(setup, [fill()])
    assert not ledger.path.exists()


@pytest.mark.parametrize("inventory", [None, ()])
def test_unavailable_history_preserves_existing_evidence(setup, inventory):
    ingest(setup, [fill(), fill(2, entry=1)])
    original = setup[0].path.read_bytes()
    with pytest.raises(ValueError):
        ingest(setup, None, positions=inventory)
    assert setup[0].path.read_bytes() == original


def test_unavailable_position_inventory_cannot_claim_closed_positions(setup):
    with pytest.raises(ValueError):
        ingest(setup, [fill(), fill(2, entry=1)], positions=None)
    assert not setup[0].path.exists()


def test_invalid_correction_quarantines_whole_position(setup):
    ingest(setup, [fill(), fill(2, entry=1)])
    result = ingest(setup, [fill(profit=float("nan"))])
    assert result["quarantined_row_count"] == 1
    assert result["strict_strategy_positions"] == 0
    assert result["position_states"] == {"quarantined_fill_excluded": 1}


def test_corrupt_ledger_is_never_overwritten(setup):
    ledger, _ = setup
    ledger.path.write_text("broken json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        ingest(setup, [fill()])
    assert ledger.path.read_text(encoding="utf-8") == "broken json"


def test_identity_change_excludes_both_positions(setup):
    ingest(setup, [fill(), fill(2, entry=1)])
    result = ingest(setup, [fill(position=20), fill(3, position=20, entry=1)])
    assert result["strict_strategy_positions"] == 0
    assert result["quarantined_row_count"] == 1


def test_currency_change_preserves_file(setup):
    ingest(setup, [fill()])
    original = setup[0].path.read_bytes()
    setup[1].currency = "EUR"
    with pytest.raises(ValueError):
        ingest(setup, [fill()])
    assert setup[0].path.read_bytes() == original


def test_exact_broker_reference_links_without_a_comment(setup):
    result = ingest(setup, [fill(comment=""), fill(2, entry=1, comment="")])
    assert result["strict_strategy_positions"] == 1


def test_conflicting_comment_is_not_strategy_evidence(setup):
    result = ingest(setup, [fill(comment="AAI_Dabcdef_Sbrkt"), fill(2, entry=1)])
    assert result["strict_strategy_positions"] == 0


def test_atomic_write_failure_preserves_previous_file(setup, monkeypatch):
    ingest(setup, [fill()])
    original = setup[0].path.read_bytes()
    def fail(*args):
        raise PermissionError("test write failure")
    monkeypatch.setattr("atlas_ai.learning.closed_position_ledger.os.replace", fail)
    with pytest.raises(PermissionError):
        ingest(setup, [fill(2, entry=1)])
    assert setup[0].path.read_bytes() == original
    assert not list(setup[0].path.parent.glob("*.tmp"))


def test_concurrent_ingestion_does_not_lose_fills(setup):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(ingest, setup, [fill(i, position=i), fill(i + 1, position=i, entry=1)])
                   for i in (10, 20)]
        for future in futures:
            future.result(timeout=15)
    assert setup[0].snapshot()["broker_fill_count"] == 4
    assert setup[0].snapshot()["closed_positions"] == 2


def test_shadow_comparison_does_not_change_allocator_or_policy(setup):
    from atlas_ai.trader import AtlasTrader
    from atlas_ai.learning.online_allocator import StrategyState
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = NS(win_rate_focus_enabled=True, min_strategy_samples=8, min_strategy_win_rate=.35)
    stats = {"ema_crossover": StrategyState(wins=100, losses=600, pnl=-1)}
    trader.allocator = NS(stats=lambda: stats)
    trader._closed_position_evidence = {"available": True, "strategy_statistics": {
        "ema_crossover": dict(wins=8, losses=2, pnl=10)}}
    original = deepcopy(stats)
    rows = trader._strategy_evidence_comparison(["ema_crossover", "breakout"])["filter_comparison"]
    assert rows[0]["shadow_filter_eligible"] is None
    assert rows[1]["current_filter_eligible"] is False
    assert rows[1]["shadow_filter_eligible"] is True
    assert stats == original


def test_durable_link_verifies_complete_position_after_event_rotation(setup):
    from atlas_ai.learning.decision_index import GuardedDecisionIndex
    ledger,account=setup
    index=GuardedDecisionIndex(ledger.settings)
    assert index.record({"decision_id":"abcdef12","strategy":"ema_crossover","order_id":101,
        "request_origin":"trader_guarded","execution_success":True,"execution_mode":"demo"})
    entry=fill(1);exit=fill(2,entry=1,profit=10)
    first=ledger.ingest_broker_snapshot(account=account,deals=[entry],positions=[NS(symbol="XAUUSD",identifier=10)],decision_events=index.events())
    assert first["strict_strategy_positions"]==0
    closed=ledger.ingest_broker_snapshot(account=account,deals=[entry,exit],positions=[],decision_events=index.events())
    assert closed["strict_strategy_positions"]==1
    assert closed["strategy_statistics"]["ema_crossover"]["pnl"]==8
