"""Versioned pullback context for the shared, unchanged M5 sequence detector."""
import math
from atlas_ai.data.top_down import TIMEFRAMES,POLICY
from atlas_ai.strategies.smc_composite import evaluate as sequence

NAME="smc_pullback_v2"
CONTEXT_RULES={"direction_timeframes":["D1","H4"],"setup_timeframes":["H1","M15"],
    "location":"direction_appropriate_half_of_H1_or_M15_recent_20_bar_range",
    "pullback":"at_least_one_opposing_close_change_in_last_six_H1_or_M15_closes",
    "H4_range":"entry_inside_range_no_H4_midpoint_veto","entry_timeframe":"M5"}


def setup_context(context,quote,*,reaction_reference=None):
    result={"passed":False,"stage":"higher_timeframe_confluence","reason":"D1_H4_direction_must_agree",
        "context_policy":NAME,"direction_timeframes":["D1","H4"],"setup_timeframes":["H1","M15"]}
    details=context.get("details",{});side=details.get("D1")
    if (context.get("policy")!=POLICY or context.get("entry_timeframe")!="M5"
        or context.get("closed_candles_only") is not True or side not in {"buy","sell"} or details.get("H4")!=side):return result
    result["side"]=side
    try:
        evidence=context["evidence"]
        for tf in TIMEFRAMES:
            row=evidence[tf];hi=float(row["recent_high"]);lo=float(row["recent_low"])
            if row["status"]!="available" or not all(math.isfinite(v) and v>0 for v in [hi,lo]) or lo>=hi:
                raise ValueError("valid_closed_evidence_required:"+tf)
            if details.get(tf) not in {"buy","sell","flat"}:raise ValueError("unknown_timeframe_evidence:"+tf)
        entry=float(quote["ask"] if side=="buy" else quote["bid"])
        location=entry if reaction_reference is None else float(reaction_reference['price'])
        if not math.isfinite(location) or location<=0:raise ValueError('invalid_reaction_reference')
        if not float(evidence["H4"]["recent_low"])<=entry<=float(evidence["H4"]["recent_high"]):
            return {**result,"stage":"setup_location","reason":"entry_outside_H4_reference_range"}
        zones=[];retracements=[]
        for tf in ["H1","M15"]:
            row=evidence[tf];values=[float(v) for v in row["recent_closes"]]
            if len(values)!=6 or any(not math.isfinite(v) or v<=0 for v in values):raise ValueError("six_closed_setup_closes_required:"+tf)
            sign=1 if side=="buy" else -1
            if any(sign*(b-a)<0 for a,b in zip(values,values[1:])):retracements.append(tf)
            lo,hi=float(row["recent_low"]),float(row["recent_high"]);mid=(lo+hi)/2
            if lo<=location<=hi and (location<mid if side=="buy" else location>mid):
                zones.append({"timeframe":tf,"low":lo,"high":hi,"midpoint":mid,
                    "side":"discount" if side=="buy" else "premium"})
        if not retracements:return {**result,"stage":"pullback_context","reason":"no_observed_H1_or_M15_countertrend_pullback"}
        if not zones:return {**result,"stage":"setup_location","reason":"await_H1_or_M15_reaction_zone","pullback_timeframes":retracements}
        return {**result,"passed":True,"stage":"setup_context_ready","reason":"direction_pullback_and_local_reaction_zone_present",
            **({'reaction_reference':dict(reaction_reference)} if reaction_reference is not None else {}),
            "pullback_timeframes":retracements,"reaction_zones":zones,"lower_timeframe_biases":{tf:details[tf] for tf in ["H1","M15"]}}
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        return {**result,"stage":"input_validation","reason":str(exc)}


def evaluate(frame,context,quote,now):
    result=sequence(frame,context,quote,now,setup_policy=setup_context)
    result["strategy"]=NAME;result["schema"]="atlas_smc_pullback_v2"
    result["rules"]={**result["rules"],"context":dict(CONTEXT_RULES)}
    if result.get("candidate"):result["candidate"]["strategy"]=NAME
    return result
