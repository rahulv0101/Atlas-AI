"""Isolated low-energy-veto diagnostics. No execution or policy activation."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
import math

import pandas as pd

from atlas_ai.testing.confidence_penalty_audit import make_trader
from atlas_ai.testing.historical_broker import ExitVariant, simulate
from atlas_ai.strategies.inventory import base_inventory
from tools.cost_aware_strategy_audit import metrics


RANGE_STRATEGIES = frozenset({"rsi_mean_reversion", "bollinger_mean_reversion",
    "stochastic_reversal", "vwap_proxy_reversion", "gold_micro_structure_reversion"})
METHOD = {"sample_minutes": 15, "warmup_bars": 1200,
    "alternative": "bypass_only_low_energy_predicate_keep_remaining_signal_filters",
    "history": "empty_identical_learning_state_no_future_outcome_learning",
    "scope": "rejected_candidates_only_not_full_system_or_portfolio_backtest",
    "label": "next_minute_entry_full_contiguous_horizon_same_session",
    "slippage_points_each_side": 3., "automatic_promotion": False}


def summarize_publications(records):
    """Unique publication times, not capture frequency or trade counts."""
    seen=set(); counts=Counter(); blockers=Counter(); rejected=Counter(); times=[]
    for record in records:
        d=record.get("publication",{});g=d.get("signal_generation",{})
        at=d.get("updated_at")
        if not at or not g or at in seen:continue
        seen.add(at);times.append(at);counts["publications"]+=1
        if d.get("chosen",{}).get("side") in {"buy","sell"}:counts["directional_chosen"]+=1
        vetoed=[c for c in g.get("candidates",[]) if "low_energy_directional_suppression" in c.get("reason_codes",[])]
        if vetoed:counts["publications_with_low_energy_veto"]+=1
        rejected.update(c["strategy"] for c in vetoed)
        reason=str(d.get("primary_blocker") or "unknown")
        if reason.startswith("Timing discipline blocked trade"):reason="timing_discipline"
        elif reason.startswith("Higher-timeframe alignment required"):reason="higher_timeframe_alignment"
        blockers[reason]+=1
    return {"scope":"unique_publications_in_bounded_archive_sample_not_independent_trades",
        "first":min(times) if times else None,"last":max(times) if times else None,
        "counts":dict(counts),"primary_blockers":dict(blockers),"vetoed_candidates":dict(rejected),
        "broker_eligible":False,"orders_sent":0}


def traders(settings):
    if settings.learning_mode:
        raise ValueError("hard_veto_baseline_requires_learning_mode_false")
    if settings.signal_regime_gate_min_trend_strength_pct <= 0:
        raise ValueError("positive_baseline_threshold_required")
    # Negative research-only threshold makes this single predicate false. It
    # does not enable learning_mode, which also changes other early returns.
    alternative = replace(settings, signal_regime_gate_min_trend_strength_pct=-1.)
    return (make_trader(settings, {"state": {}}),
            make_trader(alternative, {"state": {}}))


def trace_pair(baseline, alternative, signal, context):
    before = asdict(signal)
    left, right = {}, {}
    a = baseline._apply_signal_generation_gating(deepcopy(signal), deepcopy(context), diagnostics=left)
    b = alternative._apply_signal_generation_gating(deepcopy(signal), deepcopy(context), diagnostics=right)
    return {"raw": before, "baseline": asdict(a), "alternative": asdict(b),
        "baseline_reasons": left["reason_codes"], "alternative_reasons": right["reason_codes"]}


def current_audit(settings, status):
    baseline, alternative = traders(settings)
    ctx = status.get("signal_generation", {}).get("context", {})
    strength = ctx.get("trend_strength")
    vol = ctx.get("volatility_pct")
    threshold = settings.signal_regime_gate_min_trend_strength_pct
    return {"publication_at": status.get("updated_at"), "context": ctx,
        "configured_thresholds": {"trend_strength_pct": threshold,
            "low_volatility_pct": settings.signal_regime_gate_low_volatility_max_pct},
        "predicate_from_published_context": (isinstance(strength, (int,float)) and strength < threshold
            and ctx.get("volatility_state") == "low" and ctx.get("regime") in {"range","unknown","high_volatility_range"}),
        "classification_note": "Gate trend strength is absolute first-to-last close drift over 60 closes, not regression slope or ATR.",
        "redundancy_note": "With default low-volatility cutoff .03%, a known low-volatility range has drift below .12%; changing .18% to .12% cannot release it.",
        "volatility_state_matches_formula": (baseline._signal_volatility_state(vol) == ctx.get("volatility_state")) if isinstance(vol,(int,float)) else None,
        "trend_and_range_labels_can_differ": True,
        "baseline_learning_mode": settings.learning_mode,
        "broker_eligible": False}


def evaluate(frame, settings, spec, *, progress=lambda **kw: None, pack=None):
    baseline, alternative = traders(settings)
    pack = list(pack if pack is not None else base_inventory(settings.timeframe))
    rows = []; counts = Counter(); busy = {}; sessions = Counter()
    times = pd.to_datetime(frame.time, utc=True)
    horizon = settings.backtest_max_hold_bars
    if horizon < 1: raise ValueError("positive_horizon_required")
    enabled = {s.name: baseline._strategy_enabled(s.name) for s in pack}
    for i in range(METHOD["warmup_bars"]-1, len(frame)-horizon):
        available = times.iloc[i] + pd.Timedelta(minutes=1)
        if available.minute % METHOD["sample_minutes"]: continue
        window = frame.iloc[i-1199:i+1]
        # Do not classify across missing historical input bars.
        if not times.iloc[i-1199:i+1].diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            counts["input_window_gap"] += 1; continue
        context = baseline._signal_generation_context(window, available.to_pydatetime())
        counts["sampled_windows"] += 1
        if not context["allowed_session"]: counts["outside_allowed_session"] += 1; continue
        low = (context["trend_strength"] < settings.signal_regime_gate_min_trend_strength_pct
            and context["volatility_state"] == "low" and context["regime"] in {"range","unknown","high_volatility_range"})
        if not low: continue
        counts["low_energy_windows"] += 1; sessions[context["session"]] += 1
        # Decisions use only fully closed bars; entry and outcome are later.
        if times.iloc[i+1] != available or not times.iloc[i+1:i+1+horizon].diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            counts["execution_horizon_gap"] += 1; continue
        end = times.iloc[i+horizon] + pd.Timedelta(minutes=1)
        if (end.date()!=available.date() or baseline._session_label((end-pd.Timedelta(microseconds=1)).to_pydatetime()) != context["session"]):
            counts["session_boundary"] += 1; continue
        for strategy in pack:
            if i+1 <= busy.get(strategy.name,-1): continue
            signal = baseline._sanitize_signal(strategy.generate_signal(window))
            if signal.side not in {"buy","sell"}: continue
            if not all(math.isfinite(float(v)) and float(v)>0 for v in
                       [signal.confidence,signal.stop_loss_points,signal.take_profit_points]):
                counts["invalid_signal"] += 1; continue
            pair = trace_pair(baseline, alternative, signal, context)
            if "low_energy_directional_suppression" not in pair["baseline_reasons"]:
                raise ValueError("low_energy_baseline_not_reproduced")
            retained = pair["alternative"]["side"] in {"buy","sell"} and pair["alternative"]["confidence"]>0
            outcome = simulate(frame,i+1,signal,spec.volume_min,spec,settings,
                ExitVariant("current",settings.backtest_break_even_lock_r,3.))
            busy[strategy.name]=i+horizon
            rows.append({**pair,"entry_at":available.isoformat(),"horizon_end":end.isoformat(),
                "strategy":strategy.name,"enabled_in_current_inventory":enabled[strategy.name],
                "range_strategy":strategy.name in RANGE_STRATEGIES,
                "session":context["session"],"context":context,"retained_by_remaining_signal_filters":retained,
                "net_r":outcome["net_r"],"net_cash":outcome["net_cash"],"exit_reason":outcome["exit_reason"],
                "hypothetical_outcome_only":True,"full_execution_eligibility_verified":False})
        progress(sampled_windows=counts["sampled_windows"],cases=len(rows),available_at=available.isoformat())
    grouped = {}
    for strategy in pack:
        cases=[r for r in rows if r["strategy"]==strategy.name]
        retained=[r for r in cases if r["retained_by_remaining_signal_filters"]]
        grouped[strategy.name]={"enabled":enabled[strategy.name],"range_strategy":strategy.name in RANGE_STRATEGIES,
            "rejected_cases":len(cases),"retained_after_single_veto_bypass":len(retained),
            "all_rejected_hypothetical_outcomes":metrics(cases),
            "retained_hypothetical_outcomes":metrics(retained)}
    return {"counts":dict(counts),"low_energy_sessions":dict(sessions),"strategies":grouped,"cases":rows,
        "broker_eligible":False,"orders_sent":0,"policy_changes":[],"profitability_proven":False,
        "limitations":["Reused historical data, exploratory diagnostic only; no untouched validation.",
            "15-minute fixed grid misses intra-bar and unsampled opportunities; closed-bar research differs from forming-bar runtime.",
            "Empty identical learning snapshots prevent future-learning leakage but do not reconstruct historical or current learning.",
            "Signal retention is not final conviction, timing, risk, ranking, margin or execution approval.",
            "Per-strategy hypothetical labels overlap across strategies and cannot be added as portfolio returns.",
            "Current reference broker conversion and assumed costs are not calibrated historical natural fills.",
            "Disabled range strategies are research comparisons, not newly enabled strategies."]}
