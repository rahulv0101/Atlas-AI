"""Broker-confirmed, persistent intraday exit coordination. Never creates entries."""
from datetime import datetime, timezone
import json
from pathlib import Path

from atlas_ai.atomic_files import atomic_json
from atlas_ai.execution.automation_state_store import AutomationStateStore


class IntradayExitManager:
    def __init__(self, path):
        self.path = Path(path)
        self.storage = AutomationStateStore(self.path)

    def _load(self):
        if not self.path.exists():
            return {"schema": 1, "attempts": {}, "entries_blocked": False}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("schema") != 1 or not isinstance(state.get("attempts"), dict):
            raise ValueError("invalid_intraday_exit_journal")
        return state

    def _save(self, state):
        atomic_json(self.path, state)

    def view(self):
        try:
            state = self._load()  # Atomic replacement makes status reads coherent without waiting on a broker call.
            return {k: v for k, v in state.items() if k != "attempts"}
        except Exception:
            return {"state": "exit_monitor_error", "flat_verified": False, "entries_blocked": True}

    def block_reason(self):
        try:
            state = self._load()
            return "intraday_exit_pending_or_cutoff" if state.get("entries_blocked") else ""
        except Exception:
            return "intraday_exit_state_unavailable"

    @staticmethod
    def _inventory(adapter):
        rows = adapter.intraday_inventory()
        if not isinstance(rows, list):
            raise ValueError("intraday_inventory_unavailable")
        owned = [row for row in rows if row.get("owned_by_atlas") is True]
        if any(not row.get("broker_order_id") or row.get("status") not in {"open", "pending"} for row in owned):
            raise ValueError("intraday_inventory_invalid")
        return owned, len(rows) - len(owned)

    def run(self, adapter, *, cutoff_required, actions_allowed, reason, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("aware_UTC_time_required")
        with self.storage._locked():
            state = None
            try:
                state = self._load()
                owned, unmanaged = self._inventory(adapter)
                attempts = state["attempts"]
                stale = False
                for row in owned:
                    if row.get("opened_at_utc"):
                        opened = datetime.fromisoformat(row["opened_at_utc"])
                        if opened.tzinfo is None:
                            raise ValueError("ambiguous_position_time")
                        stale |= opened.astimezone(timezone.utc).date() < now.astimezone(timezone.utc).date()
                unresolved = any(a.get("status") not in {"confirmed", "not_dispatched", "rejected"} for a in attempts.values())
                continuing = bool(state.get("exit_in_progress", False))
                due = bool(cutoff_required or stale or unresolved or continuing)
                state.update(checked_at=now.isoformat(), exit_in_progress=bool(due and (owned or unresolved or continuing)), entries_blocked=due, reason=reason if cutoff_required else ("overnight_exposure" if stale else "exit_reconciliation" if unresolved else "active_session"))
                self._save(state)
                can_act = actions_allowed if callable(actions_allowed) else lambda: bool(actions_allowed)
                if due and can_act():
                    # Cancel entries first, then re-read to catch a cancellation/fill race.
                    for kind in ("cancel", "close"):
                        owned, unmanaged = self._inventory(adapter)
                        for row in owned:
                            if (row["status"] == "pending") != (kind == "cancel"):
                                continue
                            key = kind + ":" + str(row["broker_order_id"])
                            previous = attempts.get(key, {})
                            pending = previous.get("status") not in {None, "not_dispatched", "rejected", "confirmed"}
                            partial_progress = previous.get("status") == "partial" and float(row.get("size", 0)) < float(previous.get("volume", 0))
                            if pending and not partial_progress:
                                continue
                            if not can_act():
                                break
                            attempt = {"status": "dispatching", "volume": row.get("size"), "at": now.isoformat(), "kind": kind, "ticket": str(row["broker_order_id"])}
                            attempts[key] = attempt
                            self._save(state)  # Persist intent BEFORE broker mutation, including across restart.
                            try:
                                response = (adapter.cancel_order(broker_order_id=attempt["ticket"]) if kind == "cancel" else adapter.close_position(position_id=attempt["ticket"]))
                                payload = response.payload or {}
                                attempt.update(status=("confirmed" if response.ok and response.status in {"cancelled", "closed"} else "not_dispatched" if payload.get("dispatch_attempted") is False else "rejected" if response.status == "rejected" else "partial" if response.status == "partially_closed" else "unknown"), message=response.message)
                            except Exception as exc:
                                attempt.update(status="unknown", message=type(exc).__name__)
                            self._save(state)
                owned, unmanaged = self._inventory(adapter)
                ids = {str(row["broker_order_id"]) for row in owned}
                for attempt in attempts.values():
                    if attempt.get("ticket") in ids or attempt.get("status") == "confirmed":
                        continue
                    if attempt.get("kind") == "close":
                        attempt["status"] = "confirmed"  # Position absence is broker-confirmed closure.
                    elif attempt.get("kind") == "cancel":
                        response = adapter.query_order_status(broker_order_id=attempt["ticket"])
                        if response.ok and response.status in {"cancelled", "filled", "rejected"}:
                            attempt["status"] = "confirmed"
                uncertain = sum(a.get("status") in {"dispatching", "unknown", "partial"} for a in attempts.values())
                flat = not owned and uncertain == 0
                state.update(exit_in_progress=bool(due and not flat), state=("flat_verified" if due and flat else "exit_pending" if due else "monitoring"), flat_verified=flat, positions=sum(r["status"] == "open" for r in owned), pending_orders=sum(r["status"] == "pending" for r in owned), unmanaged_exposure_count=unmanaged, uncertain_actions=uncertain, actions_allowed=bool(can_act()), entries_blocked=bool(cutoff_required or (due and not flat)))
                self._save(state)
                return {k: v for k, v in state.items() if k != "attempts"}
            except Exception as exc:
                if state is not None:
                    try:
                        state.update(entries_blocked=True, exit_in_progress=bool(cutoff_required or state.get("exit_in_progress")), state="exit_monitor_error", flat_verified=False, reason=type(exc).__name__)
                        self._save(state)
                    except Exception:
                        pass
                # Existing journal remains intact; missing inventory is never interpreted as flat.
                return {"state": "exit_monitor_error", "entries_blocked": True, "flat_verified": False, "reason": type(exc).__name__, "checked_at": now.isoformat()}
