"""Shared bias arithmetic with an explicit complete 30-close slow window."""
import math


def bias_from_closes(values):
    try:
        closes=[float(v) for v in list(values)[-30:]]
    except (TypeError,ValueError,OverflowError):return "unknown"
    if len(closes)<30 or any(not math.isfinite(v) or v<=0 for v in closes):return "unknown"
    fast=sum(closes[-10:])/10.0;slow=sum(closes)/30.0
    if fast>slow*1.0002:return "buy"
    if fast<slow*.9998:return "sell"
    return "flat"
