"""Explicit SMC-style sequence detector. Read-only research; no order authority.

OHLC conventions are hypotheses, not evidence of institutional orders.
"""
from dataclasses import asdict
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars,entry_gate,TIMEFRAMES
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.indicators import atr

NAME="smc_composite_v1"
RULES={"sweep_lookback":20,"sweep_max_age_bars":12,"displacement_max_delay":3,
    "swing_confirmation_bars":2,"displacement_atr":1.25,"displacement_body_ratio":.60,
    "rejection_body_ratio":.35,"minimum_target_r":2.,"minimum_gap_atr":.05,
    "quote_max_age_seconds":30,"execution_authority":"none","auto_promotion":False}


def structure(frame):
    """Only pivots whose two right-hand confirmation bars already exist."""
    highs=[];lows=[]
    for i in range(2,len(frame)-2):
        h=float(frame.high.iloc[i]);l=float(frame.low.iloc[i])
        neighbors=frame.iloc[i-2:i+3].drop(frame.index[i])
        if h>float(neighbors.high.max()):highs.append((i,h))
        if l<float(neighbors.low.min()):lows.append((i,l))
    bias="unknown"
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1][1]>highs[-2][1] and lows[-1][1]>lows[-2][1]:bias="buy"
        elif highs[-1][1]<highs[-2][1] and lows[-1][1]<lows[-2][1]:bias="sell"
        else:bias="mixed"
    return {"bias":bias,"last_swing_high":highs[-1][1] if highs else None,
        "last_swing_low":lows[-1][1] if lows else None}


def evaluate(frame,context,quote,now,*,setup_policy=None,retest_policy=None):
    report={"strategy":NAME,"schema":"atlas_smc_composite_v1","mode":"shadow_only",
        "broker_eligible":False,"orders_sent":0,"auto_promotion":False,"rules":dict(RULES),
        "candidate":None,"stage":"input_validation","reason":"inputs_unavailable"}
    def wait(stage,reason,**evidence):
        return {**report,"stage":stage,"reason":reason,**evidence}
    try:
        now=pd.Timestamp(now)
        if now.tzinfo is None:raise ValueError("aware_evaluation_time_required")
        f=closed_bars(frame,"M5",now).tail(80).reset_index(drop=True)
        if len(f)<60:return wait("input_validation","need_60_closed_M5_bars")
        times=pd.to_datetime(f.time,utc=True)
        if not times.diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            return wait("input_validation","M5_input_gap")
        for row in f.itertuples():
            vals=[float(getattr(row,k)) for k in ["open","high","low","close"]]
            if any(not math.isfinite(v) or v<=0 for v in vals) or row.high<max(row.open,row.close,row.low) or row.low>min(row.open,row.close,row.high):
                raise ValueError("invalid_M5_OHLC")
        bid,ask,point=[float(quote[k]) for k in ["bid","ask","point"]]
        at=pd.Timestamp(quote["at"])
        if at.tzinfo is None or not all(math.isfinite(v) and v>0 for v in [bid,ask,point]) or ask<bid:
            raise ValueError("invalid_quote")
        if not -2<=(now-at).total_seconds()<=RULES["quote_max_age_seconds"]:
            return wait("input_validation","stale_or_future_quote")
        captured=pd.Timestamp(context["evaluated_at"])
        if captured.tzinfo is None or not 0<=(now-captured).total_seconds()<=120:
            return wait("higher_timeframe_confluence","stale_context")
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        return wait("input_validation",str(exc))
    setup=setup_policy(context,quote) if setup_policy is not None else None
    if setup is not None and not setup.get("passed"):
        return wait(setup["stage"],setup["reason"],setup_context=setup)
    side=setup["side"] if setup is not None else context.get("bias")
    if setup is None and not entry_gate(context,side)["passed"]:
        return wait("higher_timeframe_confluence","D1_H4_H1_M15_must_agree")
    report["side"]=side;report["trigger_bar_utc"]=times.iloc[-1].isoformat()
    report["evaluated_at"]=now.isoformat();report["quote_at"]=at.isoformat()
    sign=1 if side=="buy" else -1
    entry=ask if sign==1 else bid;spread=ask-bid
    if setup is not None:report["setup_context"]=setup
    try:
        ev=context["evidence"]
        for tf in TIMEFRAMES:
            if ev[tf]["status"]!="available":raise ValueError("higher_timeframe_evidence_unavailable")
            high,low=float(ev[tf]["recent_high"]),float(ev[tf]["recent_low"])
            if not 0<low<high or not math.isfinite(high):raise ValueError("invalid_HTF_range")
        high,low=float(ev["H4"]["recent_high"]),float(ev["H4"]["recent_low"])
        midpoint=(high+low)/2
        if setup is None and (not low<=entry<=high or (entry>=midpoint if sign==1 else entry<=midpoint)):
            return wait("premium_discount","buy_requires_H4_discount_sell_requires_H4_premium",dealing_range={"low":low,"high":high,"midpoint":midpoint})
    except (KeyError,TypeError,ValueError) as exc:return wait("premium_discount",str(exc))
    volatility=atr(f)
    best=wait("liquidity_sweep","no_reclaimed_sweep")
    # Inspect recent sweeps newest first. Every reference uses only data that
    # existed at the sweep/displacement, never pivots confirmed afterwards.
    for s in range(len(f)-4,max(20,len(f)-RULES["sweep_max_age_bars"])-1,-1):
        sweep=f.iloc[s];prior=f.iloc[s-20:s]
        level=float(prior.low.min() if sign==1 else prior.high.max())
        rng=float(sweep.high-sweep.low)
        wick=float(min(sweep.open,sweep.close)-sweep.low if sign==1 else sweep.high-max(sweep.open,sweep.close))
        swept=(sweep.low<level<sweep.close if sign==1 else sweep.high>level>sweep.close)
        if not swept or rng<=0 or wick/rng<.42:continue
        pre=structure(f.iloc[:s].reset_index(drop=True))
        breaking=pre["last_swing_high" if sign==1 else "last_swing_low"]
        if breaking is None or pre["bias"] not in {"buy","sell"}:
            if best["stage"]=="liquidity_sweep":best=wait("structure_shift","no_confirmed_pre_sweep_swing")
            continue
        for d in range(s+1,min(s+4,len(f)-2)):
            bar=f.iloc[d];a=float(volatility.iloc[d-1])
            body=abs(float(bar.close-bar.open));span=float(bar.high-bar.low)
            if not math.isfinite(a) or a<=0 or span<=0:continue
            broken=bar.close>breaking if sign==1 else bar.close<breaking
            impulse=(sign*float(bar.close-bar.open)>0 and body>=1.25*a and body/span>=.6)
            if not (broken and impulse):
                if best["stage"] in {"liquidity_sweep","structure_shift"}:best=wait("displacement_and_structure_shift","await_directional_displacement_through_confirmed_swing")
                continue
            gap_low,gap_high=(float(f.high.iloc[d-1]),float(f.low.iloc[d+1])) if sign==1 else (float(f.high.iloc[d+1]),float(f.low.iloc[d-1]))
            if gap_high-gap_low<max(2*point,.05*a):
                best=wait("fair_value_gap","displacement_has_no_valid_three_candle_FVG");continue
            opposite=[i for i in range(max(s-3,0),d) if sign*float(f.close.iloc[i]-f.open.iloc[i])<0]
            if not opposite:best=wait("order_block","no_pre_displacement_opposite_candle");continue
            ob=f.iloc[opposite[-1]];ob_low,ob_high=float(ob.low),float(ob.high)
            intervening=f.iloc[d+2:-1];last=f.iloc[-1]
            extreme=min(float(sweep.low),ob_low) if sign==1 else max(float(sweep.high),ob_high)
            # First mitigation only. A prior gap touch consumes this setup.
            consumed=not intervening.empty and ((intervening.low<=gap_high).any() if sign==1 else (intervening.high>=gap_low).any())
            invalid=not intervening.empty and ((intervening.close<=ob_low).any() if sign==1 else (intervening.close>=ob_high).any())
            if retest_policy is None and (consumed or invalid):best=wait("mitigation","setup_already_mitigated_or_invalidated");continue
            zones=[("FVG",gap_low,gap_high),("order_block",ob_low,ob_high)]
            touches=[(name,lo,hi) for name,lo,hi in zones if last.low<=hi and last.high>=lo]
            valid=[(name,lo,hi) for name,lo,hi in touches if
                (last.close>=(lo+hi)/2 if sign==1 else last.close<=(lo+hi)/2)]
            rejection=(last.high>last.low and sign*float(last.close-last.open)>0
                and abs(float(last.close-last.open))/float(last.high-last.low)>=.35)
            retest_evidence=None
            if retest_policy is not None:
                retest_evidence=retest_policy(f.iloc[d+2:].copy(),zones,side,extreme)
                valid=[tuple(z) for z in retest_evidence.get("valid_zones",[])]
                rejection=bool(valid)
            if not valid or not rejection:
                best=wait("M5_retest",retest_evidence["reason"] if retest_evidence else "await_first_FVG_or_order_block_retest_with_directional_rejection",
                    **({"retest_evidence":retest_evidence} if retest_evidence else {}));continue
            if (last.low<=extreme if sign==1 else last.high>=extreme):
                best=wait("M5_retest","retest_breaches_setup_invalidation");continue
            if abs(entry-float(last.close))>.25*a:
                best=wait("entry_quote","quote_moved_away_from_rejection_close");continue
            buffer=max(2*point,.1*a)
            stop=extreme-buffer if sign==1 else extreme+buffer+spread
            risk=sign*(entry-stop)
            # Candle liquidity levels are bid prices. Shorts cover at ask.
            levels=[float(ev[tf]["recent_high" if sign==1 else "recent_low"])+(spread if sign==-1 else 0) for tf in TIMEFRAMES]
            targets=sorted([t for t in levels if sign*(t-entry)>0],reverse=sign==-1)
            if risk<=0 or not targets:best=wait("liquidity_target","no_valid_opposing_HTF_liquidity_target");continue
            target=targets[0];reward=sign*(target-entry)
            if reward/risk<2:
                best=wait("liquidity_target","nearest_HTF_target_below_2R_before_fees_slippage",reward_risk=reward/risk);continue
            signal=TradeSignal(NAME,side,.65,risk/point,reward/point)
            return {**report,"stage":"candidate_ready","reason":"complete_sequence_observed",
                "candidate":asdict(signal),"entry_reference":entry,"stop_reference":stop,"target_reference":target,
                "reward_risk_before_fees_slippage":reward/risk,"confidence_basis":"fixed_research_score_not_win_probability",
                "sweep":{"bar_utc":times.iloc[s].isoformat(),"liquidity_level":level},
                "structure_shift":{"type":"BOS" if pre["bias"]==side else "CHOCH" if pre["bias"] in {"buy","sell"} else "structure_break_unclassified",
                    "prior_structure":pre["bias"],"broken_swing":breaking,"bar_utc":times.iloc[d].isoformat()},
                "FVG":{"low":gap_low,"high":gap_high},"order_block":{"low":ob_low,"high":ob_high},
                "retest_zone":valid[0][0],"H4_midpoint":midpoint,
                **({"retest_evidence":retest_evidence} if retest_evidence is not None else {}),
                "limitations":["OHLC proxy definitions; resting liquidity and institutional intent are unobserved.",
                    "Nominal quote-based distances before broker stop adjustment; no fill, fee or slippage calibration.",
                    "No profitability or execution eligibility established; observer cannot place orders."]}
    return best
