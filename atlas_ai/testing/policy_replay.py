"""Historical policy adapters shared with Atlas; unavailable evidence is explicit.

This is research, not a historical recreation of visual/macro/broker state.
There are no order dispatches or strategy-promotion functions in this module.
"""
from bisect import bisect_right
from collections import Counter
from dataclasses import asdict
from datetime import timedelta

import pandas as pd

from atlas_ai.data.timeframe_bias import bias_from_closes
from atlas_ai.learning.online_allocator import OnlineAllocator
from atlas_ai.models import TradeSignal
from atlas_ai.risk.risk_manager import RiskManager,RiskSnapshot
from atlas_ai.risk.volume import floor_volume
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.strategies.inventory import base_inventory
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.historical_broker import simulate
from atlas_ai.testing.historical_decision import historical_decision


def higher_timeframe_bias(frame,minutes):
    completed=[];closes=[]
    for at,group in frame.groupby(pd.to_datetime(frame.time,utc=True).dt.floor(f"{minutes}min")):
        if len(group)!=minutes:continue
        expected=pd.date_range(at,periods=minutes,freq="min")
        if list(pd.to_datetime(group.time,utc=True))!=list(expected):continue
        closes.append(float(group.close.iloc[-1]))
        completed.append((at+pd.Timedelta(minutes=minutes),bias_from_closes(closes[-30:])))
    timestamps=[row[0] for row in completed]
    result=[]
    for at in pd.to_datetime(frame.time,utc=True)+pd.Timedelta(minutes=1):
        pos=bisect_right(timestamps,at)-1
        result.append(completed[pos][1] if pos>=0 else "unknown")
    return result


def policy_trader(settings,store):
    # Pure policy methods only: do not construct ExecutionGate or MT5 adapters.
    trader=AtlasTrader.__new__(AtlasTrader)
    trader.settings=settings;trader.store=store;trader.allocator=OnlineAllocator()
    trader.allocator.set_exploration(settings.exploration_epsilon)
    trader._step_event_cache={};trader._last_runtime_flags={}
    return trader


def cache_candidates(frame,settings,store,progress=lambda **kw:None,*,start_index=250):
    trader=policy_trader(settings,store)
    strategies=[s for s in base_inventory(settings.timeframe) if trader._strategy_enabled(s.name)]
    timeframe={"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H4":240}
    tf=settings.m1_htf_alignment_timeframe if settings.timeframe=="M1" else settings.higher_timeframe_confirm
    biases=higher_timeframe_bias(frame,timeframe[tf]);cache=[];counts=Counter()
    for i in range(max(250,start_index),len(frame)-1):
        at=pd.Timestamp(frame.time.iloc[i],tz="UTC") if pd.Timestamp(frame.time.iloc[i]).tzinfo is None else pd.Timestamp(frame.time.iloc[i]).tz_convert("UTC")
        available=at+pd.Timedelta(minutes=1)
        if pd.Timestamp(frame.time.iloc[i+1]).tz_localize(None)!=available.tz_localize(None):
            counts["missing_next_minute"]+=1;continue
        window=frame.iloc[max(0,i-1199):i+1]
        context=trader._signal_generation_context(window,available.to_pydatetime())
        signals=[]
        for strategy in strategies:
            raw=trader._sanitize_signal(strategy.generate_signal(window))
            if raw.side in {"buy","sell"}:counts[strategy.name+":raw_directional"]+=1
            signal=trader._apply_signal_generation_gating(raw,context)
            signals.append(asdict(signal))
            if signal.side in {"buy","sell"}:counts[strategy.name+":gated_directional"]+=1
        if any(s["side"] in {"buy","sell"} and s["confidence"]>0 for s in signals):
            regime=trader._market_regime(list(window.close.tail(60)))
            cache.append({"index":i,"available_at":available.isoformat(),"signals":signals,
                "regime":regime,"higher_tf_bias":biases[i]})
        if i%500==0:progress(stage="cache",bar=i,bars=len(frame),candidate_bars=len(cache))
    return cache,dict(counts),[s.name for s in strategies]


def replay(frame,cache,settings,spec,variant,store,limits,*,strategy=None,strict=False,start=None,end=None,decision_cache=None):
    trader=policy_trader(settings,store);risk=RiskManager(settings)
    calendar=DayTradingSessionControl(max_trades_per_day=min(settings.max_trades_per_day,limits["day_trades"]),
        max_consecutive_losses=min(settings.max_consecutive_losses,limits["loss_streak"]),
        daily_loss_limit=min(settings.max_daily_drawdown*100,limits["daily_loss_percent"]),
        cooldown_minutes_after_loss_cluster=settings.cooldown_minutes_after_loss_streak)
    balance=float(settings.backtest_initial_balance);day_start=week_start=balance
    day=week=None;busy=-1;trades=[];rejections=Counter();equity=[balance]
    for item in cache:
        i=item["index"];entry_index=i+1;at=pd.Timestamp(item["available_at"]).to_pydatetime()
        if start is not None and at<start:continue
        if end is not None and at>=end:continue
        if entry_index<=busy:rejections["open_position"]+=1;continue
        if day!=at.date():
            day=at.date();day_start=balance;calendar.maybe_reset_new_day(now=at)
        week_key=at.date()-timedelta(days=at.weekday())
        if week!=week_key:week=week_key;week_start=balance
        daily=max(0.,(day_start-balance)/day_start);weekly=max(0.,(week_start-balance)/week_start)
        session=calendar.check(now=at,runtime_flags={"daily_loss_pct":daily*100})
        if not session.allowed:rejections[session.reason]+=1;continue
        spread=float(frame.spread.iloc[entry_index])
        snapshot=RiskSnapshot(balance,balance,daily,0,spread,weekly,calendar.consecutive_losses)
        allowed,reason=risk.evaluate(snapshot)
        if not allowed:rejections[reason]+=1;continue
        signals=[TradeSignal(**s) for s in item["signals"] if strategy is None or s["strategy"]==strategy]
        # Simulated outcomes cannot masquerade as verified broker-performance evidence.
        statistics={} if settings.strategy_filter_evidence_source=="confirmed_demo_positions" else trader.allocator.stats()
        signals,_=trader._filter_weak_strategies(signals,statistics=statistics)
        directional=[s for s in signals if s.side in {"buy","sell"} and s.confidence>0]
        if not directional:rejections["no_directional_signal"]+=1;continue
        window=frame.iloc[max(0,i-1199):i+1];regime=item["regime"];bias=item["higher_tf_bias"]
        if len(directional)==1:chosen=directional[0]
        else:
            scores,_=trader._contextual_signal_scores(signals,window,snapshot,regime,bias,{}, {},at)
            chosen=trader.allocator.choose(directional,score_overrides=scores)
        if settings.require_higher_tf_alignment and chosen.side!=bias:
            rejections["higher_timeframe_alignment"]+=1;continue
        support=trader._same_side_support_count(signals,chosen.side)
        if support<settings.min_same_side_signals:rejections["same_side_support"]+=1;continue
        if trader._strategy_to_setup_family(chosen.strategy)!=limits["setup_family"]:
            rejections["pilot_setup_family"]+=1;continue
        decision=historical_decision(trader,chosen,signals,window,regime,bias,snapshot,at,
            cache=decision_cache,namespace=(id(frame),i))
        if not decision["timing_passed"]:rejections["timing_discipline"]+=1;continue
        if decision["safety"]["volatility_action"]=="block_new_entries":
            rejections["volatility_protection"]+=1;continue
        if decision["confidence"]<decision["threshold"]:rejections["atlas_conviction_threshold"]+=1;continue
        chosen.confidence=decision["confidence"]
        if strict:
            rejections["historical_visual_macro_and_execution_evidence_unavailable"]+=1;continue
        minimum=max(spec.trade_stops_level,spec.trade_freeze_level)+max(2,round(spread*.35))
        stop_points=max(chosen.stop_loss_points,minimum)
        volume=risk.lot_size(balance,stop_points,spec.tick_value_loss,point_size=spec.point,
            tick_size=spec.tick_size,volume_step=spec.volume_step,minimum_volume=spec.volume_min)
        tier=float(trader._size_tier_profile(balance)["max_lot"])
        volume=floor_volume(min(volume,limits["lot_cap"],AtlasTrader._GUARDED_DEMO_MAX_LOT,tier,spec.volume_max),spec.volume_step)
        if volume<spec.volume_min:rejections["no_risk_bounded_volume"]+=1;continue
        if volume*spec.margin_per_lot>balance:rejections["insufficient_model_margin"]+=1;continue
        modeled_stop=abs(spec.cash(-stop_points*spec.point,volume))
        friction=spec.roundtrip_fee_per_lot*volume+abs(spec.cash(-2*variant.slippage_points_per_side*spec.point,volume))
        if modeled_stop+friction>balance*settings.max_risk_per_trade:
            rejections["risk_budget_including_fees_slippage"]+=1;continue
        daily_floor=day_start*(1-calendar.daily_loss_limit/100)
        weekly_floor=week_start*(1-settings.max_weekly_drawdown)
        if modeled_stop+friction>balance-max(daily_floor,weekly_floor):
            rejections["remaining_day_week_risk_budget"]+=1;continue
        held=min(settings.backtest_max_hold_bars,session.minutes_to_close-10)
        if held<1:rejections["session_close_buffer"]+=1;continue
        last=entry_index+held-1
        if (last>=len(frame) or (end is not None and
                pd.Timestamp(frame.time.iloc[last]).tz_localize(None)+pd.Timedelta(minutes=1)>pd.Timestamp(end).tz_localize(None))):
            rejections["incomplete_exit_window"]+=1;continue
        times=pd.to_datetime(frame.time.iloc[entry_index:last+1],utc=True)
        if not times.diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            rejections["gap_in_execution_window"]+=1;continue
        trade=simulate(frame,entry_index,chosen,volume,spec,settings,variant,
            last_index=last if held<settings.backtest_max_hold_bars else None)
        busy=trade["exit_bar"];balance+=trade["net_cash"];equity.append(balance)
        trader.allocator.update(chosen.strategy,trade["net_cash"])
        calendar.record_execution(executed=True,dry_run=False,outcome="win" if trade["net_cash"]>0 else "loss")
        trades.append({**trade,"strategy":chosen.strategy,"side":chosen.side,"confidence":chosen.confidence,
            "entry_at":at.isoformat(),"exit_at":pd.Timestamp(frame.time.iloc[busy]).tz_localize("UTC").isoformat()
                if pd.Timestamp(frame.time.iloc[busy]).tzinfo is None else pd.Timestamp(frame.time.iloc[busy]).tz_convert("UTC").isoformat(),
            "session":session.current_session,"balance_after":balance,"confidence_basis":"atlas_conviction",
            "confidence_threshold":decision["threshold"],"signal_confidence_seed":decision["signal_seed"]})
    positive=sum(t["net_cash"] for t in trades if t["net_cash"]>0)
    negative=-sum(t["net_cash"] for t in trades if t["net_cash"]<0)
    peak=equity[0];dd=0.
    for value in equity:peak=max(peak,value);dd=max(dd,(peak-value)/peak)
    cumulative=peak_r=drawdown_r=0.
    for trade in trades:
        cumulative+=trade["net_r"];peak_r=max(peak_r,cumulative);drawdown_r=max(drawdown_r,peak_r-cumulative)
    return {"trades":len(trades),"wins":sum(t["net_cash"]>0 for t in trades),
        "net_cash":balance-equity[0],"return_fraction":balance/equity[0]-1,
        "profit_factor":positive/negative if negative else None,"max_drawdown":dd,"max_drawdown_r":drawdown_r,
        "mean_net_r":sum(t["net_r"] for t in trades)/len(trades) if trades else None,
        "rejections":dict(rejections),"trade_list":trades,"full_live_policy_parity":False,
        "broker_eligible":False,"orders_sent":0,"strict_evidence_mode":strict}
