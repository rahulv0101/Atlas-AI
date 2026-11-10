from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import math

import MetaTrader5 as mt5

from atlas_ai.config.settings import Settings
from atlas_ai.data.broker_clock import broker_time_to_utc
from atlas_ai.execution.comment_codec import build_broker_comment
from atlas_ai.models import TradeSignal
from atlas_ai.risk.volume import floor_volume


@dataclass
class ExecutionResult:
    success: bool
    retcode: int
    comment: str
    order_id: int = 0
    deal_id: int = 0
    status: str = ""
    fill_qty: float = 0.0
    avg_fill_price: float = 0.0


class TradeExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _account_rejection(self, account) -> str:
        if account is None:
            return "No account info"
        configured_login = int(getattr(self.settings, "hfm_login", 0) or 0)
        configured_server = str(getattr(self.settings, "hfm_server", "") or "")
        if not configured_login or not configured_server:
            return "Configured broker account is missing"
        if getattr(account, "login", None) != configured_login or getattr(account, "server", None) != configured_server:
            return "Connected broker account does not match configuration"
        if getattr(account, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
            return "Demo account required; real account execution is disabled"
        return ""

    @staticmethod
    def _stop_buffer_points(symbol_info, spread_points: float = 0.0, extra_points: int = 0) -> int:
        stops_level = int(getattr(symbol_info, "trade_stops_level", 0) or 0)
        freeze_level = int(getattr(symbol_info, "trade_freeze_level", 0) or 0)
        spread_buffer = int(max(2, round(float(spread_points or 0.0) * 0.35)))
        return max(stops_level, freeze_level, 0) + spread_buffer + int(max(0, extra_points))

    @staticmethod
    def _normalize_volume(volume: float, symbol_info) -> float:
        return floor_volume(volume, getattr(symbol_info, "volume_step", 0),
                            getattr(symbol_info, "volume_max", 0))

    @staticmethod
    def _safe_comment(raw: str, max_len: int = 31) -> str:
        # Many brokers enforce short ASCII-only comments. Keep it deterministic and compact.
        text = (raw or "AtlasAI").encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^A-Za-z0-9_-]", "_", text).strip("_")
        if not text:
            text = "AtlasAI"
        return text[:max_len]

    @staticmethod
    def _is_atlas_comment(raw: str) -> bool:
        text = str(raw or "").strip()
        compact = "".join(ch for ch in text.lower() if ch.isalnum())
        return compact.startswith("aai") or compact.startswith("atlasai")

    @staticmethod
    def _strategy_comment_tag(
        strategy_name: str,
        decision_id: str = "",
        lane_tag: str = "",
        overlay_tag: str = "",
        regime_tag: str = "",
    ) -> str:
        return build_broker_comment(
            strategy_name=strategy_name,
            decision_id=decision_id,
            lane_tag=lane_tag,
            overlay_tag=overlay_tag,
            regime_tag=regime_tag,
        )

    @staticmethod
    def _round_price(price: float, symbol_info) -> float:
        digits = int(getattr(symbol_info, "digits", 2) or 2)
        return round(float(price or 0.0), max(0, digits))

    @classmethod
    def _normalize_stops(
        cls,
        side: str,
        price: float,
        sl: float,
        tp: float,
        symbol_info,
        spread_points: float = 0.0,
        extra_points: int = 0,
    ) -> tuple[float, float]:
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        if point <= 0:
            return sl, tp
        min_stop_points = cls._stop_buffer_points(symbol_info, spread_points=spread_points, extra_points=extra_points)
        if min_stop_points <= 0:
            return cls._round_price(sl, symbol_info), cls._round_price(tp, symbol_info)

        min_distance = min_stop_points * point
        px = float(price or 0.0)
        sl_v = float(sl or 0.0)
        tp_v = float(tp or 0.0)
        if str(side).lower() == "buy":
            if sl_v > 0 and (px - sl_v) < min_distance:
                sl_v = px - min_distance
            if tp_v > 0 and (tp_v - px) < min_distance:
                tp_v = px + min_distance
        else:
            if sl_v > 0 and (sl_v - px) < min_distance:
                sl_v = px + min_distance
            if tp_v > 0 and (px - tp_v) < min_distance:
                tp_v = px - min_distance
        sl_v = cls._round_price(sl_v, symbol_info)
        tp_v = cls._round_price(tp_v, symbol_info)

        # After price rounding, push once more if needed so the final sent price
        # still clears the broker minimum distance.
        if str(side).lower() == "buy":
            if sl_v > 0 and (px - sl_v) / point < min_stop_points:
                sl_v = cls._round_price(px - ((min_stop_points + 1) * point), symbol_info)
            if tp_v > 0 and (tp_v - px) / point < min_stop_points:
                tp_v = cls._round_price(px + ((min_stop_points + 1) * point), symbol_info)
        else:
            if sl_v > 0 and (sl_v - px) / point < min_stop_points:
                sl_v = cls._round_price(px + ((min_stop_points + 1) * point), symbol_info)
            if tp_v > 0 and (px - tp_v) / point < min_stop_points:
                tp_v = cls._round_price(px - ((min_stop_points + 1) * point), symbol_info)
        return sl_v, tp_v

    def _build_request(self, signal: TradeSignal, price: float, volume: float, symbol_info, decision_id: str = "", extra_stop_points: int = 0) -> dict:
        tick = mt5.symbol_info_tick(self.settings.symbol)
        spread_points = 0.0
        if tick is not None:
            point = float(getattr(symbol_info, "point", 0.0) or 0.0)
            if point > 0:
                spread_points = abs(float(tick.ask) - float(tick.bid)) / point
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        sl = price - signal.stop_loss_points * point if signal.side == "buy" else price + signal.stop_loss_points * point
        tp = price + signal.take_profit_points * point if signal.side == "buy" else price - signal.take_profit_points * point
        sl, tp = self._normalize_stops(
            signal.side,
            sl=sl,
            tp=tp,
            price=price,
            symbol_info=symbol_info,
            spread_points=spread_points,
            extra_points=extra_stop_points,
        )
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.settings.symbol,
            "volume": self._normalize_volume(volume, symbol_info),
            "type": mt5.ORDER_TYPE_BUY if signal.side == "buy" else mt5.ORDER_TYPE_SELL,
            "price": self._round_price(price, symbol_info),
            "sl": sl,
            "tp": tp,
            "deviation": max(1, int(self.settings.max_slippage_points)),
            "magic": self.settings.magic_number,
            "comment": self._safe_comment(self._strategy_comment_tag(signal.strategy, decision_id=decision_id)),
            "type_time": mt5.ORDER_TIME_GTC,
        }

    def execute(self, signal: TradeSignal, volume: float, decision_id: str = "") -> ExecutionResult:
        # Legacy direct-entry path for non-guarded internals/manual harnesses.
        # AtlasTrader demo/live-like entry routing should use ExecutionGate, not this method.
        if signal.side == "flat":
            return ExecutionResult(True, 0, "No trade")

        tick = mt5.symbol_info_tick(self.settings.symbol)
        if tick is None:
            return ExecutionResult(False, -1, "No symbol tick")

        symbol_info = mt5.symbol_info(self.settings.symbol)
        if symbol_info is None:
            return ExecutionResult(False, -3, "No symbol info")

        price = tick.ask if signal.side == "buy" else tick.bid
        request_base = self._build_request(signal, price=price, volume=volume, symbol_info=symbol_info, decision_id=decision_id)

        preflight_ok, preflight_note = self._preflight_order_request(request_base, symbol_info)
        if not preflight_ok:
            return ExecutionResult(False, -4, f"preflight failed: {preflight_note}")

        # Build filling mode candidates from symbol capabilities first.
        fill_modes: list[int] = []
        filling_flags = int(getattr(symbol_info, "filling_mode", 0) or 0)
        symbol_fok = int(getattr(mt5, "SYMBOL_FILLING_FOK", 1))
        symbol_ioc = int(getattr(mt5, "SYMBOL_FILLING_IOC", 2))
        symbol_return = int(getattr(mt5, "SYMBOL_FILLING_RETURN", 4))
        if filling_flags & symbol_fok:
            fill_modes.append(mt5.ORDER_FILLING_FOK)
        if filling_flags & symbol_ioc:
            fill_modes.append(mt5.ORDER_FILLING_IOC)
        if filling_flags & symbol_return:
            fill_modes.append(mt5.ORDER_FILLING_RETURN)
        # Fallback order if broker flags are missing/unexpected.
        if not fill_modes:
            fill_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]

        last_result = None
        last_check_error = ""
        last_send_error = ""
        stop_retry_points = [0, 12]
        for extra_stop_points in stop_retry_points:
            if extra_stop_points > 0:
                latest_tick = mt5.symbol_info_tick(self.settings.symbol)
                if latest_tick is not None:
                    price = latest_tick.ask if signal.side == "buy" else latest_tick.bid
                request_base = self._build_request(
                    signal,
                    price=price,
                    volume=volume,
                    symbol_info=symbol_info,
                    decision_id=decision_id,
                    extra_stop_points=extra_stop_points,
                )
                preflight_ok, preflight_note = self._preflight_order_request(request_base, symbol_info)
                if not preflight_ok:
                    last_check_error = f"preflight retry failed: {preflight_note}"
                    continue
            for fill in fill_modes:
                request = dict(request_base)
                request["type_filling"] = fill

                check = mt5.order_check(request)
                if check is None:
                    last_check_error = f"order_check none: {mt5.last_error()}"
                    continue
                check_retcode = getattr(check, "retcode", 0)
                check_comment = str(getattr(check, "comment", "") or "")
                if check_retcode not in (0, mt5.TRADE_RETCODE_DONE):
                    last_check_error = f"order_check retcode={check_retcode} comment={check_comment}"
                    if extra_stop_points == 0 and "invalid stops" in check_comment.lower():
                        break
                    continue

                try:
                    result = mt5.order_send(request)
                except Exception as exc:
                    # An exception after dispatch is not proof of rejection.
                    return ExecutionResult(False, -2, f"order_send outcome unknown: {exc}", status="unknown")
                if result is None:
                    return ExecutionResult(False, -2, f"order_send outcome unknown: {mt5.last_error()}", status="unknown")
                last_result = result
                accepted_status = {
                    mt5.TRADE_RETCODE_DONE: "filled",
                    mt5.TRADE_RETCODE_DONE_PARTIAL: "partially_filled",
                    mt5.TRADE_RETCODE_PLACED: "submitted",
                }.get(result.retcode)
                if accepted_status:
                    return ExecutionResult(
                        True,
                        result.retcode,
                        getattr(result, "comment", ""),
                        order_id=int(getattr(result, "order", 0) or 0),
                        deal_id=int(getattr(result, "deal", 0) or 0),
                        status=accepted_status,
                        fill_qty=float(getattr(result, "volume", 0.0) or 0.0),
                        avg_fill_price=float(getattr(result, "price", 0.0) or 0.0),
                    )
                if result.retcode in {
                    mt5.TRADE_RETCODE_TIMEOUT, mt5.TRADE_RETCODE_CONNECTION,
                    mt5.TRADE_RETCODE_LOCKED, mt5.TRADE_RETCODE_ERROR,
                } or getattr(result, "order", 0) or getattr(result, "deal", 0):
                    return ExecutionResult(
                        False, result.retcode, str(getattr(result, "comment", "Outcome unknown")),
                        order_id=int(getattr(result, "order", 0) or 0),
                        deal_id=int(getattr(result, "deal", 0) or 0), status="unknown",
                    )
                if extra_stop_points == 0 and str(getattr(result, "comment", "") or "").lower() == "invalid stops":
                    break

        if last_result is None:
            detail = last_send_error or last_check_error or "order_send failed"
            return ExecutionResult(False, -2, detail)
        return ExecutionResult(
            False,
            last_result.retcode,
            getattr(last_result, "comment", ""),
            order_id=int(getattr(last_result, "order", 0) or 0),
            deal_id=int(getattr(last_result, "deal", 0) or 0),
        )

    def _preflight_order_request(self, request: dict, symbol_info) -> tuple[bool, str]:
        tick = mt5.symbol_info_tick(self.settings.symbol)
        if tick is None:
            return False, "No market tick"
        account = mt5.account_info()
        account_rejection = self._account_rejection(account)
        if account_rejection:
            return False, account_rejection
        if not getattr(account, "trade_allowed", True):
            return False, "Account trade not allowed"
        if not getattr(symbol_info, "visible", True):
            return False, "Symbol not visible"
        if getattr(symbol_info, "trade_mode", 0) == 0:
            return False, "Symbol trade mode disabled"
        magic = int(request.get("magic", 0) or 0)
        if magic <= 0:
            return False, "Missing Atlas magic number"
        comment = str(request.get("comment", "") or "")
        if not self._is_atlas_comment(comment):
            return False, "Missing Atlas broker comment"

        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        if point <= 0:
            return False, "Invalid symbol point size"

        spread_points = abs(float(tick.ask) - float(tick.bid)) / point
        if spread_points > float(self.settings.max_spread_points):
            return False, f"Spread too high ({spread_points:.1f} pts)"

        vol = float(request.get("volume", 0.0) or 0.0)
        vol_min = float(getattr(symbol_info, "volume_min", 0.0) or 0.0)
        vol_max = float(getattr(symbol_info, "volume_max", 0.0) or 0.0)
        vol_step = float(getattr(symbol_info, "volume_step", 0.0) or 0.0)
        if not all(math.isfinite(v) for v in (vol, vol_min, vol_max, vol_step)):
            return False, "Invalid nonfinite volume specification"
        if vol_min <= 0 or vol_max < vol_min or vol_step <= 0:
            return False, "Invalid broker volume specification"
        if vol_min and vol < vol_min:
            return False, f"Volume below min ({vol} < {vol_min})"
        if vol_max and vol > vol_max:
            return False, f"Volume above max ({vol} > {vol_max})"
        if vol_step:
            steps = round(vol / vol_step)
            aligned = abs((steps * vol_step) - vol) <= max(1e-6, vol_step * 0.01)
            if not aligned:
                return False, f"Volume not aligned to step ({vol_step})"

        min_stop = self._stop_buffer_points(symbol_info, spread_points=spread_points)
        if min_stop > 0:
            price = float(request.get("price", 0.0) or 0.0)
            sl = float(request.get("sl", 0.0) or 0.0)
            tp = float(request.get("tp", 0.0) or 0.0)
            if sl > 0 and abs(price - sl) / point < min_stop:
                return False, f"SL too close (min {min_stop} pts)"
            if tp > 0 and abs(tp - price) / point < min_stop:
                return False, f"TP too close (min {min_stop} pts)"

        try:
            margin = mt5.order_calc_margin(
                request["type"],
                request["symbol"],
                request["volume"],
                request["price"],
            )
            if margin is None:
                return False, f"order_calc_margin failed: {mt5.last_error()}"
            free_margin = float(getattr(account, "margin_free", 0.0) or 0.0)
            if not math.isfinite(float(margin)) or float(margin) < 0 or not math.isfinite(free_margin) or free_margin < 0:
                return False, "Invalid margin data"
            if float(margin) > free_margin:
                return False, f"Insufficient free margin (need {margin:.2f})"
        except Exception as exc:
            return False, f"Margin precheck failed: {exc}"

        try:
            equity = float(getattr(account, "equity", 0.0))
            risk_fraction = float(self.settings.max_risk_per_trade)
            price, stop = float(request.get("price", 0)), float(request.get("sl", 0))
            if not all(math.isfinite(v) and v > 0 for v in (equity, risk_fraction, price, stop)) or risk_fraction > 1:
                return False, "Invalid account or stop-loss risk data"
            loss = mt5.order_calc_profit(request["type"], request["symbol"], vol, price, stop)
            if loss is None or not math.isfinite(float(loss)) or float(loss) >= 0:
                return False, "Cannot verify stop-loss risk"
            budget = equity * risk_fraction
            if -float(loss) > budget + 1e-8:
                return False, f"Stop-loss risk exceeds per-trade limit ({-float(loss):.2f} > {budget:.2f})"
        except Exception:
            return False, "Cannot verify stop-loss risk"
        return True, "ok"

    def close_stale_positions(self, *, allow_close: bool = False) -> list[ExecutionResult]:
        # Operational housekeeping exception: close pre-existing stale positions directly.
        # This is not an entry-order path and remains isolated from guarded entry execution.
        # Fail closed by default; caller must explicitly allow housekeeping close after
        # upstream guarded safety checks (kill switch/sleep/gate sync).
        if not bool(allow_close):
            return []
        account_rejection = self._account_rejection(mt5.account_info())
        if account_rejection:
            return [ExecutionResult(False, -4, f"Close blocked: {account_rejection}")]
        positions = mt5.positions_get(symbol=self.settings.symbol) or []
        today_utc = datetime.now(timezone.utc).date()
        closed: list[ExecutionResult] = []

        for pos in positions:
            opened = broker_time_to_utc(pos.time, self.settings).date()
            if opened >= today_utc:
                continue

            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                closed.append(ExecutionResult(False, -1, f"No tick for close {pos.ticket}"))
                continue

            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "volume": pos.volume,
                "type": close_type,
                "price": price,
                "deviation": 20,
                "magic": self.settings.magic_number,
                "comment": self._safe_comment("AtlasAI"),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result is None:
                closed.append(ExecutionResult(False, -2, f"Close failed {pos.ticket}"))
                continue
            ok = result.retcode == mt5.TRADE_RETCODE_DONE
            closed.append(
                ExecutionResult(
                    ok,
                    result.retcode,
                    getattr(result, "comment", ""),
                    order_id=int(getattr(result, "order", 0) or 0),
                    deal_id=int(getattr(result, "deal", 0) or 0),
                )
            )

        return closed
