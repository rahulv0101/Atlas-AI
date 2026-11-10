from __future__ import annotations

from typing import Any
import math
from atlas_ai.data.broker_clock import broker_time_to_utc
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

    def intraday_inventory(self) -> list[dict[str, Any]]:
        terminal = mt5.terminal_info()
        if terminal is None or not bool(getattr(terminal, "connected", False)):
            raise RuntimeError("terminal_not_connected")
        rejection = self._executor._account_rejection(mt5.account_info())
        if rejection:
            raise RuntimeError(rejection)
        rows = self.list_open_orders()
        if self._executor._account_rejection(mt5.account_info()):
            raise RuntimeError("account_changed_during_inventory")
        for row in rows:
            row["owned_by_atlas"] = (row.get("instrument") == self._executor.settings.symbol
                and row.get("magic") == self._executor.settings.magic_number
                and self._executor._is_atlas_comment(row.get("comment", "")))
            row["status"] = "open" if row["status"] == "open" else "pending"
        return rows

    def close_position(self, *, position_id: str) -> BrokerOrderResponse:
        dispatched = False
        def response(ok, status, message):
            return BrokerOrderResponse(ok=ok, status=status, broker_order_id=position_id,
                message=message, payload={"dispatch_attempted": dispatched})
        try:
            ticket = int(position_id)
            if ticket <= 0 or not self._executor.settings.execute_trades:
                return response(False, "rejected", "execution_disabled_or_invalid_ticket")
            terminal = mt5.terminal_info()
            rejection = self._executor._account_rejection(mt5.account_info())
            if rejection or terminal is None or not getattr(terminal, "connected", False):
                return response(False, "rejected", rejection or "terminal_not_connected")
            if not getattr(terminal, "trade_allowed", False) or getattr(terminal, "tradeapi_disabled", True):
                return response(False, "rejected", "terminal_trading_not_allowed")
            rows = mt5.positions_get(ticket=ticket)
            if rows is None:
                return response(False, "rejected", "position_inventory_unavailable")
            position = next((r for r in rows if int(r.ticket) == ticket), None)
            if position is None:
                return response(True, "closed", "position_absent_confirmed")
            if position.symbol != self._executor.settings.symbol or position.magic != self._executor.settings.magic_number or not self._executor._is_atlas_comment(getattr(position, "comment", "")):
                return response(False, "rejected", "position_not_owned_by_atlas")
            if position.type not in {mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL}:
                return response(False, "rejected", "invalid_position_side")
            tick = mt5.symbol_info_tick(position.symbol)
            info = mt5.symbol_info(position.symbol)
            if tick is None or info is None:
                return response(False, "rejected", "quote_unavailable")
            side = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if side == mt5.ORDER_TYPE_SELL else tick.ask
            if not all(math.isfinite(float(v)) and float(v) > 0 for v in (price, position.volume)):
                return response(False, "rejected", "invalid_close_price_or_volume")
            flags = int(getattr(info, "filling_mode", 0))
            filling = mt5.ORDER_FILLING_IOC if flags & getattr(mt5, "SYMBOL_FILLING_IOC", 2) else mt5.ORDER_FILLING_FOK if flags & getattr(mt5, "SYMBOL_FILLING_FOK", 1) else mt5.ORDER_FILLING_RETURN
            request = {"action": mt5.TRADE_ACTION_DEAL, "symbol": position.symbol, "position": ticket,
                "volume": position.volume, "type": side, "price": price,
                "deviation": self._executor.settings.max_slippage_points,
                "magic": self._executor.settings.magic_number, "comment": "AtlasAI_DayExit",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling}
            check = mt5.order_check(request)
            if check is None or check.retcode not in {0, mt5.TRADE_RETCODE_DONE}:
                return response(False, "rejected", "close_precheck_failed")
            if self._executor._account_rejection(mt5.account_info()):
                return response(False, "rejected", "account_changed_before_close")
            dispatched = True
            result = mt5.order_send(request)  # A single position-specific close; never blind retry.
            if result is None:
                return response(False, "unknown", "close_result_unknown")
            remaining = mt5.positions_get(ticket=ticket)
            if self._executor._account_rejection(mt5.account_info()):
                return response(False, "unknown", "account_changed_during_close")
            if remaining is not None and not any(int(r.ticket) == ticket for r in remaining):
                return response(True, "closed", "broker_confirmed_position_closed")
            if result.retcode == mt5.TRADE_RETCODE_DONE_PARTIAL:
                return response(False, "partially_closed", "partial_close_requires_fresh_inventory")
            ambiguous = {mt5.TRADE_RETCODE_TIMEOUT, mt5.TRADE_RETCODE_CONNECTION, mt5.TRADE_RETCODE_LOCKED, mt5.TRADE_RETCODE_ERROR, mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}
            return response(False, "unknown" if result.retcode in ambiguous else "rejected", "close_not_confirmed")
        except Exception as exc:
            return response(False, "unknown" if dispatched else "rejected", type(exc).__name__)

    def cancel_order(self, *, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel only an explicitly requested, Atlas-owned demo pending order.

        Never turn cancellation into a position close or retry an ambiguous send.
        The gate calls this only for a tracked request with a broker ticket.
        """
        dispatched = False
        def failed(message: str, status: str = "cancel_failed") -> BrokerOrderResponse:
            return BrokerOrderResponse(ok=False, status=status, broker_order_id=broker_order_id, message=message, payload={"dispatch_attempted": dispatched})

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
            if not self._executor._is_atlas_comment(getattr(order, "comment", "")):
                return failed("pending_order_not_owned_by_atlas")
            pending_types = {mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP, mt5.ORDER_TYPE_BUY_STOP_LIMIT, mt5.ORDER_TYPE_SELL_STOP_LIMIT}
            if int(order.type) not in pending_types:
                return failed("not_a_pending_order")
            if self._executor._account_rejection(mt5.account_info()):
                return failed("account_changed_before_cancel")
            dispatched = True
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
            rejection = self._executor._account_rejection(mt5.account_info())
            if rejection:
                return unknown(rejection)
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
                    "opened_at_utc": broker_time_to_utc(pos.time, self._executor.settings).isoformat() if getattr(pos, "time", None) else None,
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
                "opened_at_utc": broker_time_to_utc(order.time_setup, self._executor.settings).isoformat() if getattr(order, "time_setup", None) else None,
            })
            seen.add(ticket)
        return [{k:v for k,v in row.items() if k != "opened_at_utc" or v is not None} for row in out]

