from __future__ import annotations

from typing import Any
import MetaTrader5 as mt5

from atlas_ai.execution.broker_adapter import BrokerAdapter, BrokerOrderResponse
from atlas_ai.execution.trade_executor import TradeExecutor
from atlas_ai.models import TradeSignal


class MT5BrokerAdapter(BrokerAdapter):
    """Production BrokerAdapter that delegates to TradeExecutor for real MT5 execution."""

    def __init__(self, executor: TradeExecutor) -> None:
        self._executor = executor

    def submit_order(self, *, idempotency_key: str, request: dict[str, Any]) -> BrokerOrderResponse:
        """Translate ExecutionGate request into TradeExecutor call."""
        payload = dict(request or {})
        # Reconstruct a minimal TradeSignal from the payload_summary or request fields
        side = str(payload.get("side", payload.get("action_type", "flat"))).lower()
        if side not in {"buy", "sell"}:
            return BrokerOrderResponse(
                ok=False,
                status="rejected",
                broker_order_id="",
                message="invalid_side",
            )

        strategy = str(payload.get("strategy", payload.get("setup_family", "unknown")))
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        stop_loss_points = float(payload.get("stop_loss_points", 0.0) or 0.0)
        take_profit_points = float(payload.get("take_profit_points", 0.0) or 0.0)
        volume = float(payload.get("size", payload.get("volume", 0.0)) or 0.0)
        decision_id = str(payload.get("decision_id", idempotency_key) or idempotency_key)

        signal = TradeSignal(
            strategy=strategy,
            side=side,  # type: ignore[arg-type]
            confidence=confidence,
            stop_loss_points=stop_loss_points,
            take_profit_points=take_profit_points,
        )

        result = self._executor.execute(signal, volume=volume, decision_id=decision_id)
        broker_order_id = str(result.order_id or result.deal_id or "")
        if getattr(result, "status", "") == "unknown":
            return BrokerOrderResponse(ok=False, status="unknown", broker_order_id=broker_order_id, message=result.comment)

        if result.success:
            if not broker_order_id:
                return BrokerOrderResponse(
                    ok=False,
                    status="unknown",
                    broker_order_id="",
                    message=f"missing_broker_confirmation retcode={result.retcode} comment={result.comment}",
                )
            return BrokerOrderResponse(
                ok=True,
                status=str(getattr(result, "status", "") or "filled"),
                broker_order_id=broker_order_id,
                message=result.comment,
                fill_qty=(float(getattr(result, "fill_qty", 0.0) or 0.0) if getattr(result, "status", "") else volume),
                avg_fill_price=float(getattr(result, "avg_fill_price", 0.0) or 0.0),
            )
        return BrokerOrderResponse(
            ok=False,
            status="rejected",
            broker_order_id="",
            message=f"retcode={result.retcode} comment={result.comment}",
        )

    def cancel_order(self, *, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel only an explicitly requested, Atlas-owned demo pending order.

        Never turn cancellation into a position close or retry an ambiguous send.
        The gate calls this only for a tracked request with a broker ticket.
        """
        def failed(message: str, status: str = "cancel_failed") -> BrokerOrderResponse:
            return BrokerOrderResponse(ok=False, status=status, broker_order_id=broker_order_id, message=message)

        try:
            ticket = int(broker_order_id)
            if ticket <= 0:
                return failed("invalid_broker_order_id")
            if not self._executor.settings.execute_trades:
                return failed("execution_disabled")
            terminal = mt5.terminal_info()
            if terminal is None or not bool(getattr(terminal, "connected", False)):
                return failed("terminal_not_connected")
            account_rejection = self._executor._account_rejection(mt5.account_info())
            if account_rejection:
                return failed(account_rejection)
            if not bool(getattr(terminal, "trade_allowed", False)) or bool(getattr(terminal, "tradeapi_disabled", True)):
                return failed("terminal_trading_not_allowed")
            orders = mt5.orders_get(ticket=ticket)
            if orders is None:
                return failed("mt5_orders_get_failed")
            order = next((item for item in orders if int(item.ticket) == ticket), None)
            if order is None:
                existing = self.query_order_status(broker_order_id=broker_order_id)
                if existing.ok and existing.status == "cancelled":
                    return existing
                return failed("pending_order_not_found")
            if str(order.symbol) != self._executor.settings.symbol or int(order.magic) != self._executor.settings.magic_number:
                return failed("pending_order_not_owned_by_atlas")
            pending_types = {mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP, mt5.ORDER_TYPE_BUY_STOP_LIMIT, mt5.ORDER_TYPE_SELL_STOP_LIMIT}
            if int(order.type) not in pending_types:
                return failed("not_a_pending_order")
            result = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket, "symbol": order.symbol})
            if result is None:
                return failed("cancel_result_unknown", "unknown")
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                confirmed = self.query_order_status(broker_order_id=broker_order_id)
                if confirmed.ok and confirmed.status == "cancelled":
                    return confirmed
                return failed("cancel_not_yet_confirmed", "unknown")
            return failed(f"cancel_retcode:{result.retcode}")
        except Exception as exc:
            return failed(f"cancel_failed:{type(exc).__name__}", "unknown")

    def query_order_status(self, *, broker_order_id: str) -> BrokerOrderResponse:
        def unknown(message: str) -> BrokerOrderResponse:
            return BrokerOrderResponse(ok=False, status="unknown", broker_order_id=broker_order_id, message=message)

        try:
            ticket = int(broker_order_id)
            if ticket <= 0:
                return unknown("invalid_broker_order_id")
            if mt5.terminal_info() is None and not mt5.initialize():
                return unknown("mt5_initialize_failed")
            rows = mt5.orders_get(ticket=ticket)
            if rows is None:
                return unknown("mt5_orders_get_failed")
            if not rows:
                rows = mt5.history_orders_get(ticket=ticket)
            if rows is None:
                return unknown("mt5_history_orders_get_failed")
            order = next((row for row in rows if int(row.ticket) == ticket), None)
            if order is None:
                return unknown("broker_order_not_found")
            status = {
                mt5.ORDER_STATE_STARTED: "submitted",
                mt5.ORDER_STATE_PLACED: "acknowledged",
                mt5.ORDER_STATE_PARTIAL: "partially_filled",
                mt5.ORDER_STATE_FILLED: "filled",
                mt5.ORDER_STATE_CANCELED: "cancelled",
                mt5.ORDER_STATE_EXPIRED: "cancelled",
                mt5.ORDER_STATE_REJECTED: "rejected",
                mt5.ORDER_STATE_REQUEST_ADD: "submitted",
                mt5.ORDER_STATE_REQUEST_MODIFY: "submitted",
                mt5.ORDER_STATE_REQUEST_CANCEL: "submitted",
            }.get(int(order.state))
            if status is None:
                return unknown("unrecognized_broker_order_state")
            initial = float(getattr(order, "volume_initial", 0.0) or 0.0)
            remaining = float(getattr(order, "volume_current", 0.0) or 0.0)
            filled = initial if status == "filled" else max(0.0, min(initial, initial - remaining))
            return BrokerOrderResponse(ok=True, status=status, broker_order_id=str(ticket), fill_qty=filled)
        except Exception as exc:
            return unknown(f"broker_query_failed:{type(exc).__name__}")

    def list_open_orders(self) -> list[dict[str, Any]]:
        if mt5.terminal_info() is None and not mt5.initialize():
            raise RuntimeError(f"mt5_initialize_failed:{mt5.last_error()}")
        try:
            mt5.symbol_select(self._executor.settings.symbol, True)
        except Exception:
            pass
        positions_raw = mt5.positions_get(symbol=self._executor.settings.symbol)
        if positions_raw is None:
            raise RuntimeError(f"mt5_positions_get_failed:{mt5.last_error()}")
        positions = list(positions_raw or [])
        out: list[dict[str, Any]] = []
        for pos in positions:
            pos_type = int(getattr(pos, "type", -1))
            side = "buy" if pos_type == int(getattr(mt5, "POSITION_TYPE_BUY", 0)) else "sell"
            out.append(
                {
                    "broker_order_id": str(getattr(pos, "ticket", "") or ""),
                    "instrument": str(getattr(pos, "symbol", self._executor.settings.symbol) or self._executor.settings.symbol),
                    "side": side,
                    "size": float(getattr(pos, "volume", 0.0) or 0.0),
                    "status": "open",
                    "profit": float(getattr(pos, "profit", 0.0) or 0.0),
                    "sl": float(getattr(pos, "sl", 0.0) or 0.0),
                    "tp": float(getattr(pos, "tp", 0.0) or 0.0),
                    "magic": int(getattr(pos, "magic", 0) or 0),
                    "comment": str(getattr(pos, "comment", "") or ""),
                }
            )
        pending = mt5.orders_get(symbol=self._executor.settings.symbol)
        if pending is None:
            raise RuntimeError(f"mt5_orders_get_failed:{mt5.last_error()}")
        seen = {row["broker_order_id"] for row in out}
        buy_types = {mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_BUY_STOP_LIMIT}
        for order in pending:
            ticket = str(getattr(order, "ticket", "") or "")
            if ticket in seen:
                continue
            out.append({
                "broker_order_id": ticket,
                "instrument": str(getattr(order, "symbol", self._executor.settings.symbol)),
                "side": "buy" if int(order.type) in buy_types else "sell",
                "size": float(getattr(order, "volume_current", 0.0) or 0.0),
                "status": "submitted",
                "profit": 0.0,
                "sl": float(getattr(order, "sl", 0.0) or 0.0),
                "tp": float(getattr(order, "tp", 0.0) or 0.0),
                "magic": int(getattr(order, "magic", 0) or 0),
                "comment": str(getattr(order, "comment", "") or ""),
            })
            seen.add(ticket)
        return out

