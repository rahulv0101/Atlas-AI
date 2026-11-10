"""Backfill isolated broker-confirmed evidence; never submit orders or alter learning."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import MetaTrader5 as mt5
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import utc_query_time
from atlas_ai.learning.closed_position_ledger import ClosedPositionLedger
from atlas_ai.learning.decision_index import GuardedDecisionIndex
from atlas_ai.memory.knowledge_store import KnowledgeStore


def sync(settings, *, days=365):
    if not 1 <= days <= 3650:
        raise ValueError("History window must be 1 to 3650 days")
    attached = mt5.initialize(path=settings.hfm_terminal_path) if settings.hfm_terminal_path else mt5.initialize()
    if not attached:
        raise RuntimeError("Cannot attach to configured MT5 terminal")
    try:
        account = mt5.account_info()
        # Validate before querying another account's trading history.
        if (account is None or account.login != settings.hfm_login or account.server != settings.hfm_server
                or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO):
            raise RuntimeError("Matching configured demo account required")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        ledger = ClosedPositionLedger(settings)
        result = ledger.ingest_broker_snapshot(
            account=account,
            deals=mt5.history_deals_get(utc_query_time(start, settings), utc_query_time(end, settings)),
            positions=mt5.positions_get(),
            decision_events=[*KnowledgeStore(settings.storage_dir).tail_events(limit=50000, event_type="decision_sample"),
                             *GuardedDecisionIndex(settings).events()],
            window_start=start.isoformat(), window_end=end.isoformat(),
        )
        return {**result, "available": True, "ledger_path": str(ledger.path), "orders_sent": 0}
    finally:
        mt5.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = sync(load_settings(), days=args.days)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
