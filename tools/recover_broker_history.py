"""Read-only partial recovery of broker fills; never replace the missing journal."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import hashlib
import json
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import MetaTrader5 as mt5
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import broker_time_to_utc, utc_query_time


def recover_history(settings, *, days=365, end=None):
    if not 1 <= days <= 3650:
        raise ValueError("History window must be 1 to 3650 days")
    initialized = mt5.initialize(path=settings.hfm_terminal_path) if settings.hfm_terminal_path else mt5.initialize()
    if not initialized:
        raise RuntimeError("Cannot attach to the configured MT5 terminal")
    account = mt5.account_info()
    if account is None or account.login != settings.hfm_login or account.server != settings.hfm_server or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("Read-only recovery requires the matching configured demo account")
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    deals = mt5.history_deals_get(utc_query_time(start, settings), utc_query_time(end, settings))
    if deals is None:
        raise RuntimeError("Broker history unavailable; no recovery claim was made")
    rows = {}
    for deal in deals:
        if str(deal.symbol) != settings.symbol or int(deal.magic) != settings.magic_number:
            continue
        when = broker_time_to_utc(deal.time, settings)
        if not start <= when <= end:
            continue
        rows[int(deal.ticket)] = {
            "ticket": int(deal.ticket), "order": int(deal.order), "position_id": int(deal.position_id),
            "time_utc": when.isoformat(), "entry_type": int(deal.entry), "deal_type": int(deal.type),
            "symbol": str(deal.symbol), "volume": float(deal.volume), "price": float(deal.price),
            "net_profit": float(deal.profit) + float(deal.commission) + float(deal.swap),
        }
    return {
        "schema": "atlas_partial_broker_history_recovery_v1", "captured_at": end.isoformat(),
        "source": "MT5 history_deals_get; exact configured account, symbol and Atlas magic",
        "account_fingerprint": hashlib.sha256(f"{settings.hfm_server}:{settings.hfm_login}".encode()).hexdigest(),
        "window_start_utc": start.isoformat(), "window_end_utc": end.isoformat(),
        "broker_rows_available": len(deals), "owned_fill_records_recovered": len(rows),
        "fills": sorted(rows.values(), key=lambda row: (row["time_utc"], row["ticket"])),
        "original_journal_recovered": False, "orders_sent": 0,
        "limitations": ["Broker retention may be shorter than the requested window.", "Fills do not reconstruct strategy decisions, rejected opportunities or original journal events.", "Only exact symbol/magic matches are included; entry and exit legs are separate fills, not separate completed trades.", "Original missing-history manifest remains unchanged; recovered fills are not fed into trading memory automatically."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = recover_history(load_settings(), days=args.days)
    output = args.output or PROJECT / "storage/recovered_history" / f"broker_fills_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"artifact": str(output), "owned_fill_records_recovered": result["owned_fill_records_recovered"], "original_journal_recovered": False, "orders_sent": 0}))


if __name__ == "__main__":
    main()
