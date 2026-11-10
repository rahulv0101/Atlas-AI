"""Observe broker dispatches without changing requests, retries or outcomes."""
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import time

import MetaTrader5 as mt5


def _append_row(settings, row):
    folder=Path(settings.storage_dir)/"execution_quality"
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/f"dispatches_{row['started_at'][:10]}.jsonl").open("a",encoding="utf-8") as stream:
        stream.write(json.dumps(row,allow_nan=False)+"\n")


def finite(value):
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError,OverflowError):
        return None


def send_observed(send, request, settings, *, source, strategy="", decision_id="", tick=None, diagnostic=None):
    """One call, identical return/exception. Evidence failure never retries a send."""
    started=datetime.now(timezone.utc).isoformat()
    clock=time.perf_counter()
    result=None
    error=None
    try:
        result=send(request)
        return result
    except BaseException as exc:
        error=type(exc).__name__
        raise
    finally:
        try:
            requested=finite(request.get("price"))
            filled=finite(getattr(result,"price",None))
            accepted=getattr(result,"retcode",None) in {mt5.TRADE_RETCODE_DONE,mt5.TRADE_RETCODE_DONE_PARTIAL}
            side={mt5.ORDER_TYPE_BUY:"buy",mt5.ORDER_TYPE_SELL:"sell"}.get(request.get("type"))
            signed=((filled-requested)*(1 if side=="buy" else -1)
                    if accepted and side and requested and filled and requested>0 and filled>0 else None)
            bid,ask=finite(getattr(tick,"bid",None)),finite(getattr(tick,"ask",None))
            row={"schema":"atlas_execution_cost_v1","started_at":started,
                 "completed_at":datetime.now(timezone.utc).isoformat(),
                 "dispatch_ms":round((time.perf_counter()-clock)*1000,3),"source":source,
                 "strategy":strategy,"decision_id":decision_id,"symbol":request.get("symbol"),
                 "position_id":str(request.get("position","") or ""),"side":side,
                 "requested_price":requested,"fill_price":filled,"fill_qty":finite(getattr(result,"volume",None)),
                 "quote_bid":bid,"quote_ask":ask,"quote_raw_broker_time_msc":getattr(tick,"time_msc",None),
                 "spread_price":ask-bid if bid and ask and ask>=bid else None,
                 "adverse_fill_difference_price":signed,
                 "adverse_fill_difference_bps":signed/requested*10000 if signed is not None else None,
                 "retcode":getattr(result,"retcode",None),"order_id":str(getattr(result,"order","") or ""),
                 "deal_id":str(getattr(result,"deal","") or ""),"error":error,
                 "filled":bool(accepted and filled and filled>0),
                 "diagnostic":bool(diagnostic) if diagnostic is not None else strategy=="manual_broker_test",
                 "policy_note":"Request-to-fill observation, not venue latency or strategy performance. No automatic cost or policy changes."}
            _append_row(settings, row)
        except Exception:
            logging.warning("Execution cost evidence could not be saved",exc_info=True)
