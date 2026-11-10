"""Broker-confirmed position evidence, isolated from live allocator learning.

This ledger has no order submission, model training or promotion path. Counts
come from completed positions, never reward ticks, backtests or initial priors.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import MetaTrader5 as mt5

from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.broker_clock import broker_time_to_utc
from atlas_ai.execution.automation_state_store import AutomationStateStore
from atlas_ai.execution.comment_codec import parse_broker_comment
from atlas_ai.learning.evidence_provenance import is_manual_broker_test
from atlas_ai.strategy_aliases import canonical_strategy_name

SCHEMA = "atlas_closed_position_ledger_v1"


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite_broker_number")
    return number


def _decisions(events):
    refs, ids = defaultdict(list), defaultdict(list)
    for event in events:
        meta = dict(event.get("meta", {}) or {})
        if (meta.get("request_origin") != "trader_guarded"
                or meta.get("execution_success") is not True
                or meta.get("execution_mode") != "demo"):
            continue
        strategy = canonical_strategy_name(meta.get("strategy", ""))
        decision = str(meta.get("decision_id", ""))
        if strategy == "unknown" or not decision:
            continue
        for key in ("order_id", "deal_id", "broker_order_id"):
            value = str(meta.get(key, "") or "")
            if value and value != "0":
                refs[value].append(meta)
        ids[decision[:6]].append(meta)
    return refs, ids


def _attribution(deal, refs, ids):
    parsed = parse_broker_comment(getattr(deal, "comment", ""))
    candidates = refs.get(str(deal.order), []) + refs.get(str(deal.ticket), [])
    if not candidates and parsed.get("decision_id"):
        candidates = ids.get(parsed["decision_id"][:6], [])
    unique = {(str(row.get("decision_id")), canonical_strategy_name(row.get("strategy", ""))) for row in candidates}
    manual = is_manual_broker_test({"comment": getattr(deal, "comment", ""), **parsed}) or any(is_manual_broker_test(row) for row in candidates)
    if len(unique) == 1:
        decision, strategy = next(iter(unique))
        tagged = canonical_strategy_name(parsed.get("strategy", ""))
        if tagged != "unknown" and tagged != strategy.split("(", 1)[0]:
            return "unknown", "", "conflicting_strategy_tag", manual
        return strategy, decision, "decision_linked", manual
    if len(unique) > 1:
        return "unknown", "", "ambiguous_decision_link", manual
    strategy = canonical_strategy_name(parsed.get("strategy", ""))
    return strategy, parsed.get("decision_id", ""), "broker_comment_only" if strategy != "unknown" else "unattributed", manual


def rebuild_positions(fills, open_ids, invalid_ids=()):
    groups = defaultdict(list)
    for row in fills.values():
        groups[row["position_id"]].append(row)
    positions = {}
    for position_id, rows in groups.items():
        rows = sorted(rows, key=lambda row: (row["time_utc"], row["ticket"]))
        entries = [row for row in rows if row["entry_type"] == mt5.DEAL_ENTRY_IN]
        exits = [row for row in rows if row["entry_type"] in {mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY}]
        state = "incomplete"
        if position_id in invalid_ids:
            state = "quarantined_fill_excluded"
        elif any(row["entry_type"] == mt5.DEAL_ENTRY_INOUT for row in rows):
            state = "reversal_excluded"
        elif position_id in open_ids:
            state = "broker_reports_open"
        elif entries and exits:
            entry_volume = sum(row["volume"] for row in entries)
            exit_volume = sum(row["volume"] for row in exits)
            if math.isclose(entry_volume, exit_volume, rel_tol=1e-9, abs_tol=1e-8):
                types = {row["deal_type"] for row in entries}
                if len(types) == 1 and all(row["deal_type"] not in types for row in exits):
                    state = "closed"
                    balance = 0.0
                    for row in rows:
                        balance += row["volume"] if row["entry_type"] == mt5.DEAL_ENTRY_IN else -row["volume"]
                        if balance < -1e-8:
                            state = "invalid_fill_sequence_excluded"
                            break
                else:
                    state = "conflicting_direction_excluded"
            elif exit_volume > entry_volume:
                state = "missing_entry_volume"
        strategies = {row["strategy"] for row in entries if row["strategy"] != "unknown"}
        strategy = next(iter(strategies)) if len(strategies) == 1 else "unknown"
        manual = any(row["manual_test"] for row in rows)
        linked = bool(entries) and all(row["attribution"] == "decision_linked" for row in entries)
        strict = state == "closed" and not manual and strategy != "unknown" and linked
        net = sum(row["profit"] + row["commission"] + row["swap"] + row["fee"] for row in rows)
        positions[position_id] = {
            "position_id": position_id, "state": state, "strategy": strategy,
            "fill_tickets": [row["ticket"] for row in rows], "fill_count": len(rows),
            "opened_at": entries[0]["time_utc"] if entries else None,
            "closed_at": exits[-1]["time_utc"] if state == "closed" else None,
            "net_profit": net, "outcome": ("win" if net > 0 else "loss" if net < 0 else "draw") if state == "closed" else None,
            "manual_test": manual, "decision_linked": linked,
            "strict_strategy_evidence": strict,
        }
    return positions


def summarize(document):
    positions = document.get("positions", {})
    states = Counter(row["state"] for row in positions.values())
    stats = {}
    for row in positions.values():
        if not row["strict_strategy_evidence"]:
            continue
        item = stats.setdefault(row["strategy"], {"wins": 0, "losses": 0, "draws": 0, "closed_positions": 0, "pnl": 0.0})
        item[{"win": "wins", "loss": "losses", "draw": "draws"}[row["outcome"]]] += 1
        item["closed_positions"] += 1
        item["pnl"] += row["net_profit"]
    return {
        "schema": SCHEMA, "mode": "shadow_only", "updated_at": document.get("updated_at"),
        "currency": document.get("currency", "unknown"), "broker_fill_count": len(document.get("fills", {})),
        "position_states": dict(states), "closed_positions": states.get("closed", 0),
        "strict_strategy_positions": sum(row["strict_strategy_evidence"] for row in positions.values()),
        "manual_test_positions": sum(row["manual_test"] for row in positions.values()),
        "unlinked_closed_positions": sum(row["state"] == "closed" and not row["strict_strategy_evidence"] for row in positions.values()),
        "strategy_statistics": stats, "quarantined_row_count": len(document.get("quarantine", {})),
        "live_policy_changed": False,
        "limitations": ["Broker retention may omit entry legs or separate fees.", "Broker tags alone do not prove an autonomous strategy decision.", "Only balanced, broker-flat, decision-linked, non-test positions enter strict strategy statistics."],
    }


class ClosedPositionLedger:
    def __init__(self, settings):
        self.settings = settings
        self.fingerprint = hashlib.sha256(f"{settings.hfm_server}:{settings.hfm_login}:{settings.symbol}".encode()).hexdigest()
        self.path = Path(settings.storage_dir) / "performance" / f"closed_positions_{self.fingerprint[:16]}.json"
        # Reuse the existing cross-process file lock, not its automation state.
        self._storage = AutomationStateStore(self.path)

    def _load(self):
        if not self.path.exists():
            return {"schema": SCHEMA, "account_fingerprint": self.fingerprint, "fills": {}, "positions": {}, "quarantine": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA or data.get("account_fingerprint") != self.fingerprint:
            raise ValueError("Ledger schema/account identity mismatch")
        return data

    def _write(self, document):
        atomic_json(self.path, document)

    def ingest_broker_snapshot(self, *, account, deals, positions, decision_events=(), window_start=None, window_end=None):
        if (account is None or account.login != self.settings.hfm_login or account.server != self.settings.hfm_server
                or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO):
            raise ValueError("Ledger requires the matching configured demo account")
        if deals is None or positions is None:
            raise ValueError("Broker history/open-position inventory unavailable")
        deals = list(deals)
        open_ids = {str(getattr(row, "identifier", None) or row.ticket) for row in positions if row.symbol == self.settings.symbol}
        refs, ids = _decisions(decision_events)
        with self._storage._locked():
            document = self._load()
            currency = str(getattr(account, "currency", "unknown"))
            if document.get("currency", currency) != currency:
                raise ValueError("Broker account currency changed")
            document["currency"] = currency
            fills = document["fills"]
            owned = {row["position_id"] for row in fills.values()}
            owned.update(str(getattr(row, "position_id", "")) for row in deals
                         if getattr(row, "symbol", "") == self.settings.symbol and int(getattr(row, "magic", 0)) == self.settings.magic_number)
            for deal in deals:
                if getattr(deal, "symbol", "") != self.settings.symbol or str(getattr(deal, "position_id", "")) not in owned:
                    continue
                ticket = str(getattr(deal, "ticket", "unknown"))
                try:
                    if int(ticket) <= 0 or int(deal.position_id) <= 0:
                        raise ValueError("invalid_broker_identifiers")
                    volume = _number(deal.volume)
                    price = _number(deal.price)
                    if volume <= 0 or price <= 0 or int(deal.type) not in {mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL}:
                        raise ValueError("not_a_supported_trade_fill")
                    if int(deal.entry) not in {mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT, mt5.DEAL_ENTRY_OUT_BY}:
                        raise ValueError("unknown_entry_type")
                    strategy, decision, attribution, manual = _attribution(deal, refs, ids)
                    candidate = {
                        "ticket": int(ticket), "order_id": str(deal.order), "position_id": str(deal.position_id),
                        "source": "mt5_history_deals", "symbol": deal.symbol,
                        "time_utc": broker_time_to_utc(deal.time, self.settings).isoformat(),
                        "entry_type": int(deal.entry), "deal_type": int(deal.type), "volume": volume, "price": price,
                        "profit": _number(deal.profit), "commission": _number(deal.commission),
                        "swap": _number(deal.swap), "fee": _number(getattr(deal, "fee", 0)),
                        "strategy": strategy, "decision_id": decision, "attribution": attribution, "manual_test": manual,
                    }
                    previous = fills.get(ticket)
                    candidate["manual_test"] = manual or bool((previous or {}).get("manual_test"))
                    # A narrow incremental journal query must not discard a
                    # previously established full decision link.
                    if previous and any(candidate[key] != previous[key] for key in ("position_id", "order_id", "entry_type", "deal_type")):
                        raise ValueError("broker_fill_identity_changed")
                    if previous and previous["attribution"] == "decision_linked" and attribution in {"unattributed", "broker_comment_only"}:
                        for key in ("strategy", "decision_id", "attribution"):
                            candidate[key] = previous[key]
                    fills[ticket] = candidate
                    document["quarantine"].pop(ticket, None)
                except (ValueError, TypeError, AttributeError, OverflowError) as exc:
                    document["quarantine"][ticket] = {"reason": type(exc).__name__, "source": "mt5_history_deals", "position_id": str(getattr(deal, "position_id", "")), "previous_position_id": fills.get(ticket, {}).get("position_id", "")}
            invalid_ids = {row.get(key) for row in document["quarantine"].values() for key in ("position_id", "previous_position_id")}
            document["positions"] = rebuild_positions(fills, open_ids, invalid_ids)
            document.update(updated_at=datetime.now(timezone.utc).isoformat(), window_start_utc=window_start, window_end_utc=window_end)
            self._write(document)
            return summarize(document)

    def snapshot(self):
        with self._storage._locked():
            return summarize(self._load())
