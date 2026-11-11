"""Use Atlas conviction and active-profile thresholds with historical inputs.

Unknown visual/macro/learned state remains unknown. This does not assert live
pipeline parity and cannot approve an order.
"""
from dataclasses import asdict
from unittest.mock import patch

from atlas_ai.analysis.decision_analysis import build_structured_decision_analysis
from atlas_ai.config.settings import get_active_thresholds
from atlas_ai.market_context import build_context_snapshot
from atlas_ai.strategies.inventory import base_inventory


def historical_decision(trader,chosen,signals,window,regime,bias,snapshot,now,*,cache=None,namespace=None):
    cache={} if cache is None else cache
    seed=float(chosen.confidence)
    key=("chart",id(trader.settings),namespace,chosen.strategy,chosen.side,seed)
    if key not in cache:
        cache[key]=trader._derive_runtime_chart_features(df=window,chosen=chosen,regime=regime)
    chart=cache[key]
    profile=get_active_thresholds(trader.settings)
    status={"symbol":trader.settings.symbol,"timeframe":trader.settings.timeframe,
        "updated_at":now.isoformat(),"session":trader._session_label(now),"regime":regime,
        "chosen":{**asdict(chosen),"signal_confidence_seed":seed},"signals":[asdict(s) for s in signals],
        "higher_timeframe":{"bias":bias},"chart_features":chart,"risk":asdict(snapshot),
        "setup_family":trader._strategy_to_setup_family(chosen.strategy),
        "learning_mode":trader.settings.learning_mode,"mode_label":profile["mode_label"],"thresholds":profile,
        "visual_chart_read":{"status":"unavailable_historical","visual_watch_used_for_decision":False},
        "market":{"last_close":float(window.close.iloc[-1]),"recent_close":[float(v) for v in window.close.tail(20)]}}
    with patch("atlas_ai.market_context._fresh_external_context_fields",return_value={}):
        context=build_context_snapshot(status)
    status["context_snapshot"]=context
    timing_key=("timing",*key[1:])
    if timing_key not in cache:
        cache[timing_key]=trader._timing_discipline_snapshot(chosen,context,status)
    timing=cache[timing_key]
    safety=trader._volatility_safety_state(context_snapshot=context,regime=regime)
    adaptive,_=trader._dynamic_min_confidence(trader._min_conf_threshold(regime),{})
    if safety["volatility_state"]=="elevated":adaptive=min(1.,adaptive+.05)
    threshold=min(float(adaptive),float(profile["confidence"]))
    status["safety_layer"]=safety
    if not timing["passed"] or safety["volatility_action"]=="block_new_entries":
        return {"timing_passed":bool(timing["passed"]),"safety":safety,"confidence":None,"threshold":threshold}
    support_key=("raw_support",id(trader.settings),namespace)
    if support_key not in cache:
        raw=[s.generate_signal(window) for s in base_inventory(trader.settings.timeframe) if trader._strategy_enabled(s.name)]
        cache[support_key]={side:sum(s.side==side and s.confidence>0 for s in raw) for side in ("buy","sell")}
    support=max(trader._same_side_support_count(signals,chosen.side),cache[support_key][chosen.side])
    status["same_side_support"]={"count":support}
    conviction_key=("conviction",*key[1:],tuple((s.strategy,s.side,s.confidence) for s in signals),
        tuple(asdict(snapshot).values()),support)
    if conviction_key not in cache:
        analysis=build_structured_decision_analysis(status=status,runtime={"execute_trades":False,"gemini_influence_enabled":False})
        cache[conviction_key]=float(analysis["confidence_score"])/100
    return {"timing_passed":True,"safety":safety,"confidence":cache[conviction_key],"threshold":threshold,
        "basis":"atlas_conviction","signal_seed":seed,"same_side_support":support}
