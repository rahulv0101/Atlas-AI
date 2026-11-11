"""Validate recorded diagnostic fill arithmetic; never relabel it as natural proof."""
import math


def crosscheck(diagnostic,dispatches,spec):
    if (diagnostic.get("type")!="automated_demo_diagnostic" or diagnostic.get("natural_strategy_proof") is not False
            or not diagnostic.get("balanced_entry_exit") or not diagnostic.get("broker_flat")):
        raise ValueError("labelled_balanced_diagnostic_required")
    ids={str(row["ticket"]) for row in diagnostic["fills"]}
    rows=[row for row in dispatches if str(row.get("deal_id")) in ids and row.get("filled")]
    if len(rows)!=2 or not all(row.get("diagnostic") for row in rows):raise ValueError("two_measured_diagnostic_fills_required")
    entries=[row for row in rows if row.get("source")=="entry"]
    exits=[row for row in rows if row.get("source") in {"intraday_close","legacy_close"}]
    if len(entries)!=1 or len(exits)!=1:raise ValueError("entry_and_exit_dispatches_required")
    entry,exit=entries[0],exits[0]
    volume=float(entry["fill_qty"])
    if (not math.isfinite(volume) or volume<=0 or volume!=float(exit["fill_qty"])
            or {entry["side"],exit["side"]}!={"buy","sell"}):
        raise ValueError("balanced_opposite_fill_volume_required")
    arithmetic=[]
    for row in rows:
        values=[float(row[key]) for key in ("fill_price","requested_price","quote_ask","quote_bid")]
        if not all(math.isfinite(v) and v>0 for v in values):raise ValueError("valid_quote_prices_required")
        sign=1 if row["side"]=="buy" else -1
        difference=(float(row["fill_price"])-float(row["requested_price"]))*sign
        quoted=float(row["quote_ask"])-float(row["quote_bid"])
        if quoted<0:raise ValueError("crossed_quote_invalid")
        arithmetic.append({"source":row["source"],"volume":row["fill_qty"],
            "quote_spread_points":quoted/spec.point,"signed_request_to_fill_points":difference/spec.point,
            "recorded_spread_matches":math.isclose(quoted,row["spread_price"],abs_tol=1e-8),
            "recorded_difference_matches":math.isclose(difference,row["adverse_fill_difference_price"],abs_tol=1e-8)})
    sign=1 if entry["side"]=="buy" else -1
    move=sign*(float(exit["fill_price"])-float(entry["fill_price"]))
    actual=float(diagnostic["net_profit"])
    charges=sum(float(row["profit"]) for row in diagnostic["fills"])-actual
    reconstructed=spec.cash(move,volume)-charges
    return {"state":"diagnostic_arithmetic_checked","fills":len(rows),"arithmetic":arithmetic,
        "recorded_price_arithmetic_valid":all(row["recorded_spread_matches"] and row["recorded_difference_matches"] for row in arithmetic),
        "broker_recorded_net_cash":actual,"recorded_net_fee_cash":charges,
        "reconstructed_net_cash_current_conversion":reconstructed,"current_conversion_difference_cash":reconstructed-actual,
        "natural_strategy_proof":False,"cost_calibration_ready":False,"broker_eligible":False,"orders_sent":0,
        "limitations":["Exactly one labelled diagnostic lifecycle; not representative natural slippage evidence.",
            "Current tick-value conversion differs from historical conversion; cash residual is reported, not forced to zero."]}
