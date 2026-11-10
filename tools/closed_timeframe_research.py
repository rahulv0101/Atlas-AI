"""Three predeclared closed-chart hypotheses, M1 fill paths, research only.

Reuses previously inspected historical data; no blind validation or execution
authority is claimed. No parameter search or broker order API is used.
"""
from dataclasses import asdict,replace
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.learning.trade_labeling import _simulate_trade_path
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.built_in import EMACrossoverClosedConfirmMidExitStrategy
from atlas_ai.strategies.minute_pack import PullbackTrendM15MidExitStrategy
from atlas_ai.strategies.distance_units import atr_distance_points
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.research_protocol import environment_versions
from tools.cost_aware_strategy_audit import prepare_frame,stamp,report_lane,qualifies,hashes

RECIPES=(("closed_ema_M5",5,EMACrossoverClosedConfirmMidExitStrategy),
         ("closed_ema_M15",15,EMACrossoverClosedConfirmMidExitStrategy),
         ("pullback_M15",15,PullbackTrendM15MidExitStrategy))
LOOKBACK=120
HOLD_MINUTES=60


def clock_settings(settings,minutes,exit_clock):
    if exit_clock not in {"m1","strategy"}:raise ValueError("predeclared_exit_clock_required")
    return replace(settings,backtest_stale_exit_bars=int(settings.backtest_stale_exit_bars)*(minutes if exit_clock=="strategy" else 1))


def sources():
    names=("tools/closed_timeframe_research.py","atlas_ai/strategies/research_protocol.py")
    return {**hashes(),**{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}


def closed_bars(frame,minutes):
    """Only complete contiguous M1 groups can become a higher-timeframe bar."""
    if minutes not in (5,15):raise ValueError("predeclared_timeframe_required")
    rows=[]
    for start,group in frame.groupby(pd.to_datetime(frame.time,utc=True).dt.floor(f"{minutes}min"),sort=True):
        times=pd.to_datetime(group.time,utc=True)
        expected=pd.date_range(start,periods=minutes,freq="min")
        if len(group)!=minutes or list(times)!=list(expected):continue
        rows.append({"time":start.tz_localize(None),"open":float(group.open.iloc[0]),
            "high":float(group.high.max()),"low":float(group.low.min()),"close":float(group.close.iloc[-1]),
            "tick_volume":float(group.tick_volume.sum()),"spread":float(group.spread.max())})
    return pd.DataFrame(rows,columns=["time","open","high","low","close","tick_volume","spread"])


def signal_cache(frame,minutes,strategy,point):
    coarse=closed_bars(frame,minutes);cache=[]
    calendar=DayTradingSessionControl()
    for i in range(LOOKBACK-1,len(coarse)):
        available=stamp(coarse.time.iloc[i])+pd.Timedelta(minutes=minutes)
        if not calendar._detect_session(available.to_pydatetime()).allowed:continue
        window=coarse.iloc[i-LOOKBACK+1:i+1]
        signal=strategy.generate_signal(window)
        if signal.side not in {"buy","sell"} or signal.confidence<=0:continue
        price_atr=float(atr(window).iloc[-1])
        signal=replace(signal,
            stop_loss_points=atr_distance_points(price_atr,strategy.sl_atr_multiple,point,strategy.sl_floor_points),
            take_profit_points=atr_distance_points(price_atr,strategy.tp_atr_multiple,point,strategy.tp_floor_points))
        cache.append({"bar_utc":stamp(coarse.time.iloc[i]).isoformat(),
            "available_at":available.isoformat(),"timeframe_minutes":minutes,"signal":asdict(signal)})
    return cache


def evaluate(frame,cache,start,end,settings,rules):
    index={stamp(t):i for i,t in enumerate(frame.time)}
    calendar=DayTradingSessionControl();rows=[];busy=-1;day=None;count=streak=0;day_r=0.
    for candidate in cache:
        at=stamp(candidate["available_at"])
        if at!=stamp(candidate["bar_utc"])+pd.Timedelta(minutes=candidate["timeframe_minutes"]):
            raise ValueError("closed_bar_availability_clock_mismatch")
        if at<stamp(start) or at>=stamp(end):continue
        entry_idx=index.get(at)
        if entry_idx is None or entry_idx<1 or entry_idx<=busy:continue
        if day!=str(at.date()):day=str(at.date());count=streak=0;day_r=0.
        if count>=rules["max_trades_day"] or streak>=rules["max_losses"] or day_r<=-rules["daily_loss_r"]:continue
        session=calendar._detect_session(at.to_pydatetime())
        held=min(HOLD_MINUTES,session.minutes_to_close-11)
        if not session.allowed or held<1:continue
        last=entry_idx+held-1
        if last>=len(frame) or stamp(frame.time.iloc[last])>=stamp(end):continue
        if not frame.time.iloc[entry_idx-1:last+1].diff().dropna().eq(pd.Timedelta(minutes=1)).all():continue
        signal=TradeSignal(**candidate["signal"]);entry=frame.iloc[entry_idx];spread=float(entry.spread)
        if spread>rules["max_spread_points"] or signal.take_profit_points<2*(spread+rules["fee_points"]):continue
        result=_simulate_trade_path(frame.iloc[:last+1],signal,entry_idx-1,
            replace(settings,backtest_max_hold_bars=held),ambiguous_bar_policy="stop_first")
        gross=float(result["r_multiple"])
        spread_fee_r=(spread+rules["fee_points"])/signal.stop_loss_points
        slippage_r=float(entry.open)*rules["slippage_bps"]/10000/(signal.stop_loss_points*rules["point"])
        net=gross-spread_fee_r-slippage_r;busy=int(result["exit_idx"])
        rows.append({"signal_bar_utc":candidate["bar_utc"],"signal_available_at":at.isoformat(),
            "entry_at":stamp(entry.time).isoformat(),"exit_at":stamp(frame.time.iloc[busy]).isoformat(),
            "side":signal.side,"session":session.current_session,"score":signal.confidence,
            "stop_points":signal.stop_loss_points,"target_points":signal.take_profit_points,
            "gross_r":gross,"spread_fee_r":gross-spread_fee_r,"net_r":net,"exit_reason":result["exit_type"]})
        count+=1;day_r+=net;streak=streak+1 if net<0 else 0
    return rows


def audit(source,output,exit_clock="m1"):
    original=json.loads((source/"manifest.json").read_text());data=json.loads((source/"data.json").read_text())
    digest=hashlib.sha256((source/"candles.csv").read_bytes()).hexdigest()
    if digest!=data["sha256"] or original["sources"]!=hashes():raise ValueError("source_experiment_changed")
    if original["symbol"]!="XAUUSD":raise ValueError("XAUUSD_source_experiment_required")
    settings=replace(load_settings(),execute_trades=False,symbol=original["symbol"],timeframe="M1",**original["simulator_settings"])
    rules={key:value for key,value in original["rules"].items() if key!="hold_bars"}
    lane_settings={key:clock_settings(settings,minutes,exit_clock) for key,minutes,_ in RECIPES}
    protocol={"created_at":datetime.now(timezone.utc).isoformat(),"source_hashes":sources(),
        "symbol":original["symbol"],"source_manifest_sha256":hashlib.sha256((source/"manifest.json").read_bytes()).hexdigest(),
        "environment":environment_versions(),"dataset_sha256":digest,"source_run":str(source.resolve()),
        "recipes":[{"key":key,"minutes":minutes,"template":asdict(factory()),
            "stale_exit_m1_bars":lane_settings[key].backtest_stale_exit_bars} for key,minutes,factory in RECIPES],
        "exit_clock":exit_clock,
        "lookback_closed_bars":LOOKBACK,"hold_minutes":HOLD_MINUTES,"rules":rules,
        "simulator_settings":original["simulator_settings"],
        "periods":{p:original[p] for p in ("training","holdout","recent_already_inspected")},
        "minimum_cases":{"training":30,"holdout":30,"future":30},
        "selection_rule":"Training only: >=30 cases, >=2 days, positive modeled mean, PF>=1.1 (or all wins), DD<=6R; highest mean or none. Future evidence required even if historical checks pass.",
        "historical_periods_already_inspected":True,"broker_eligible":False,"auto_promotion":False,"orders_sent":0,
        "limitations":["Exploratory isolated strategies, not complete-engine replay or blind holdout.",
            "Existing entry templates, corrected ATR-point distances and one fixed 60-minute maximum; no parameter search.",
            "No entry before signal-bar close; M1 next-open paths with stop-first ambiguity. Stale-exit clock is explicit per recipe; all holds remain capped at 60 minutes.",
            "Spread and estimated fees plus hypothetical slippage; not measured fills."]}
    output.mkdir(parents=True,exist_ok=False);atomic_json(output/"manifest.json",protocol)
    frame=prepare_frame(pd.read_csv(source/"candles.csv"));caches={};results={};samples={};candidates=[]
    for key,minutes,factory in RECIPES:
        cache=signal_cache(frame,minutes,factory(),rules["point"]);caches[key]=cache
        rows=evaluate(frame,cache,*original["training"],lane_settings[key],rules)
        results[key]={"training":report_lane(rows)};samples[key]={"training":rows}
        stats=results[key]["training"]["configured_costs"]
        if qualifies(stats,minimum_trades=30):candidates.append((stats["mean_r"],key))
        print(json.dumps({"training_complete":key,"cases":len(rows)}),flush=True)
    winner=max(candidates)[1] if candidates else None
    selection={"selected_from_training_only":winner,"qualified_training_comparisons":len(candidates),
        "frozen_at":datetime.now(timezone.utc).isoformat(),"broker_eligible":False}
    atomic_json(output/"selection.json",selection)
    for key,cache in caches.items():
        for phase in ("holdout","recent_already_inspected"):
            rows=evaluate(frame,cache,*original[phase],lane_settings[key],rules)
            results[key][phase]=report_lane(rows);samples[key][phase]=rows
    if protocol["source_hashes"]!=sources():raise ValueError("research_source_changed_during_run")
    passed=bool(winner and qualifies(results[winner]["holdout"]["configured_costs"],minimum_trades=30))
    atomic_json(output/"signals.json",caches);atomic_json(output/"samples.json",samples)
    atomic_json(output/"results.json",{"lanes":results,"selection":selection,"selected_candidate_passed_historical_check":passed,
        "broker_eligible":False,"orders_sent":0})
    print(json.dumps({"training_selection":winner,"passed_historical_check":passed,"orders_sent":0}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--source-run",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--exit-clock",choices=("m1","strategy"),default="m1")
    args=parser.parse_args();audit(args.source_run,args.output_dir,args.exit_clock)
