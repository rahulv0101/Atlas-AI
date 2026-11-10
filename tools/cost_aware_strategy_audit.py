"""Frozen, offline strategy comparisons and read-only prospective paper observation.

No execution adapter, strategy promotion, runtime setting or order API is used.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.learning.trade_labeling import _simulate_trade_path
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.built_in import EMACrossoverStrategy
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.distance_units import ATR_DISTANCE_RULES, corrected_atr_signal
from atlas_ai.strategies.minute_pack import (PullbackTrendStrategy, MomentumContinuationStrategy,
    GoldMicroImpulseStrategy, GoldBreakoutRetestStrategy, GoldLiquiditySweepStrategy)

# Existing formulas' ATR multipliers and point floors. Changed distances remain
# research variants; live strategy classes and their parameters are untouched.
DISTANCES = {key: value for key, value in ATR_DISTANCE_RULES.items() if key != "evolved_rule"}
VARIANTS = ("current_immediate", "atr_points_immediate", "atr_points_confirmed_retest")
SOURCES = ("tools/cost_aware_strategy_audit.py", "atlas_ai/strategies/built_in.py",
    "atlas_ai/strategies/minute_pack.py", "atlas_ai/strategies/indicators.py",
    "atlas_ai/learning/trade_labeling.py", "atlas_ai/execution/session_control.py",
    "atlas_ai/strategies/distance_units.py")


def stamp(value):
    t = pd.Timestamp(value)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}


def strategies():
    return [EMACrossoverStrategy(), PullbackTrendStrategy(), MomentumContinuationStrategy(),
            GoldMicroImpulseStrategy(), GoldBreakoutRetestStrategy(), GoldLiquiditySweepStrategy()]


def corrected(signal, atr_price, point):
    return corrected_atr_signal(signal, atr_price, point)


def confirmation(frame, i, side):
    """Only the next three closed bars may confirm a trigger-close retest."""
    level = float(frame.iloc[i]["close"])
    a = float(frame.iloc[i]["atr_price"])
    for j in range(i + 1, min(i + 4, len(frame))):
        if stamp(frame.iloc[j]["time"]) - stamp(frame.iloc[i]["time"]) != pd.Timedelta(minutes=j-i):
            return None
        r, prev = frame.iloc[j], frame.iloc[j-1]
        touched = float(r["low"]) <= level + .25*a and float(r["high"]) >= level - .25*a
        held = (float(r["close"]) >= level and float(r["close"]) > max(float(r["open"]), float(prev["close"]))
                if side == "buy" else
                float(r["close"]) <= level and float(r["close"]) < min(float(r["open"]), float(prev["close"])))
        if touched and held and abs(float(r["close"]) - level) <= a:
            return j
    return None


def metrics(rows, field="net_r"):
    values = [r[field] for r in rows]
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    equity = peak = drawdown = 0.
    for v in values:
        equity += v; peak = max(peak, equity); drawdown = max(drawdown, peak-equity)
    return {"trades": len(rows), "days": len({r["entry_at"][:10] for r in rows}),
        "wins": sum(v > 0 for v in values), "losses": sum(v < 0 for v in values),
        "mean_r": sum(values)/len(values) if values else None,
        "profit_factor": wins/losses if losses else None, "max_drawdown_r": drawdown}


def qualifies(stats, minimum_trades=30):
    factor_ok = ((stats["profit_factor"] or 0) >= 1.1
                 or stats["losses"] == 0 and stats["wins"] > 0)
    return (stats["trades"] >= minimum_trades and stats["days"] >= 2 and (stats["mean_r"] or 0) > 0
            and factor_ok and stats["max_drawdown_r"] <= 6)


def prepare_frame(frame):
    f = frame.copy().reset_index(drop=True)
    f["time"] = pd.to_datetime(f["time"], utc=True).dt.tz_localize(None)
    if f.empty or not f["time"].is_monotonic_increasing or f["time"].duplicated().any():
        raise ValueError("ordered_unique_closed_bars_required")
    for column in ("open", "high", "low", "close", "spread"):
        if not f[column].map(lambda v: math.isfinite(float(v)) and float(v) >= (0 if column == "spread" else 1e-9)).all():
            raise ValueError("invalid_price_or_spread")
    if ((f["high"] < f[["open", "low", "close"]].max(axis=1)).any()
            or (f["low"] > f[["open", "high", "close"]].min(axis=1)).any()):
        raise ValueError("invalid_ohlc")
    f["atr_price"] = atr(f)
    return f


def cache_signals(frame, start, previous=None):
    cached = dict(previous or {})
    pack = strategies()
    calendar = DayTradingSessionControl()
    for i in range(1200, len(frame)):
        at = stamp(frame.iloc[i]["time"])
        if at < stamp(start) or at.isoformat() in cached:
            continue
        session = calendar._detect_session(at.to_pydatetime())
        if not session.allowed or session.minutes_to_close <= 11:
            cached[at.isoformat()] = []
            continue
        window = frame.iloc[i-1199:i+1]
        cached[at.isoformat()] = [asdict(s.generate_signal(window)) for s in pack]
        if i % 1000 == 0:
            print(json.dumps({"signal_cache_progress": str(at)}), flush=True)
    return cached


def evaluate(frame, cache, strategy, variant, start, end, settings, rules):
    rows = []
    calendar = DayTradingSessionControl()
    day = None; count = streak = 0; day_r = 0.; busy_until = -1
    horizon = int(rules["hold_bars"])
    for i in range(1200, len(frame)-horizon-4):
        at = stamp(frame.iloc[i]["time"])
        if at < stamp(start) or at >= stamp(end) or i <= busy_until:
            continue
        if str(at.date()) != day:
            day = str(at.date()); count = streak = 0; day_r = 0.
        if count >= rules["max_trades_day"] or streak >= rules["max_losses"] or day_r <= -rules["daily_loss_r"]:
            continue
        raw = next((s for s in cache.get(at.isoformat(), []) if s["strategy"] == strategy), None)
        if not raw or raw["side"] not in ("buy", "sell") or raw["confidence"] <= 0:
            continue
        signal = TradeSignal(**raw)
        j = confirmation(frame, i, signal.side) if variant.endswith("confirmed_retest") else i
        if j is None or stamp(frame.iloc[j+1]["time"]) >= stamp(end):
            continue
        session = calendar._detect_session(stamp(frame.iloc[j]["time"]).to_pydatetime())
        original_session = calendar._detect_session(at.to_pydatetime())
        if not session.allowed or session.current_session != original_session.current_session:
            continue
        held = min(horizon, session.minutes_to_close-11)
        if held < 1 or j+held >= len(frame) or stamp(frame.iloc[j+held]["time"]) >= stamp(end):
            continue
        segment = frame.iloc[i:j+held+1]["time"]
        if not segment.diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            continue
        if variant != "current_immediate":
            signal = corrected(signal, float(frame.iloc[j]["atr_price"]), rules["point"])
        entry = frame.iloc[j+1]
        spread = float(entry["spread"])
        if spread > rules["max_spread_points"] or signal.stop_loss_points < 1 or signal.take_profit_points < 1:
            continue
        if variant != "current_immediate" and signal.take_profit_points < 2*(spread+rules["fee_points"]):
            continue
        result = _simulate_trade_path(frame.iloc[:j+held+1], signal, j,
            replace(settings, backtest_max_hold_bars=held), ambiguous_bar_policy="stop_first")
        gross = float(result["r_multiple"])
        spread_fee_r = (spread+rules["fee_points"])/signal.stop_loss_points
        slip_r = float(entry["open"])*rules["slippage_bps"]/10000/(signal.stop_loss_points*rules["point"])
        net = gross-spread_fee_r-slip_r
        busy_until = int(result["exit_idx"])
        rows.append({"entry_at": stamp(entry["time"]).isoformat(),
            "exit_at": stamp(frame.iloc[busy_until]["time"]).isoformat(), "side": signal.side,
            "session": session.current_session, "score": signal.confidence,
            "stop_points": signal.stop_loss_points, "target_points": signal.take_profit_points,
            "gross_r": gross, "spread_fee_r": gross-spread_fee_r, "net_r": net,
            "exit_reason": result["exit_type"]})
        count += 1; day_r += net; streak = streak+1 if net < 0 else 0
    return rows


def report_lane(rows):
    return {"configured_costs": metrics(rows), "spread_and_fee_only": metrics(rows,"spread_fee_r"),
        "gross": metrics(rows,"gross_r"),
        "by_session": {s: metrics([r for r in rows if r["session"] == s]) for s in sorted({r["session"] for r in rows})}}


def attach(settings):
    if not mt5.initialize(path=settings.hfm_terminal_path):
        raise RuntimeError("broker_data_unavailable")
    a = mt5.account_info(); s = mt5.symbol_info(settings.symbol)
    if (a is None or a.login != settings.hfm_login or a.server != settings.hfm_server
            or a.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO):
        raise RuntimeError("matching_demo_account_required_for_data")
    if s is None or abs(s.point-settings.backtest_point_size) > 1e-9:
        raise ValueError("broker_point_mismatch")


def audit(directory, fee_file, *, train_start="2026-11-02T00:00:00Z", train_end="2026-11-05T00:00:00Z",
          holdout_end="2026-11-07T00:00:00Z", recent_start="2026-11-09T00:00:00Z",
          minimum_training=12, minimum_holdout=10):
    directory.mkdir(parents=True, exist_ok=False)
    settings = replace(load_settings(), execute_trades=False, timeframe="M1")
    fee = json.loads(fee_file.read_text())
    if fee.get("roundtrip_fee_points_estimate") is None:
        raise ValueError("fee_evidence_required")
    now = datetime.now(timezone.utc)
    if not (stamp(train_start)<stamp(train_end)<stamp(holdout_end)<=stamp(recent_start)<stamp(now)):
        raise ValueError("disjoint_increasing_research_windows_required")
    if minimum_training<12 or minimum_holdout<10:
        raise ValueError("research_sample_requirements_may_not_be_lowered")
    if settings.symbol != "XAUUSD":
        raise ValueError("research_pack_requires_XAUUSD")
    rules = {"point": settings.backtest_point_size, "hold_bars": settings.backtest_max_hold_bars,
        "slippage_bps": settings.backtest_slippage_cost_bps, "fee_points": fee["roundtrip_fee_points_estimate"],
        "max_spread_points": settings.max_spread_points, "max_trades_day": 6, "max_losses": 2,
        "daily_loss_r": .006/settings.max_risk_per_trade}
    manifest = {"schema": "atlas_frozen_cost_research_v1", "created_at": now.isoformat(),
        "symbol": settings.symbol,
        "simulator_settings": {key:getattr(settings,key) for key in (
            "backtest_point_size", "backtest_break_even_r_trigger", "backtest_break_even_lock_r",
            "backtest_trailing_r_trigger", "backtest_trailing_buffer_r", "backtest_stale_exit_bars",
            "backtest_stale_min_progress_r")},
        "sources": hashes(), "variants": VARIANTS, "distance_rules": DISTANCES, "rules": rules,
        "training": [stamp(train_start).isoformat(), stamp(train_end).isoformat()],
        "holdout": [stamp(train_end).isoformat(), stamp(holdout_end).isoformat()],
        "recent_already_inspected": [stamp(recent_start).isoformat(), now.replace(second=0,microsecond=0).isoformat()],
        "minimum_cases":{"training":minimum_training,"holdout":minimum_holdout,"forward":30},
        "selection_rule": f"Training only: >={minimum_training} trades, >=2 days, positive mean, PF>=1.1 (or all wins), drawdown<=6R; highest mean; otherwise none. Holdout requires >={minimum_holdout} trades; forward evidence requires >=30. Research qualification never authorizes broker trading.",
        "live_eligibility": False, "auto_promotion": False, "orders_sent": 0,
        "limitations": ["Isolated strategy comparisons, not a replay of the entire trading engine.",
            "Strategy raw scores are not Atlas conviction; only nonzero directional signals are compared.",
            "At most six trades/day, two consecutive losses, 0.6% daily loss budget at configured risk; not actual account returns.",
            "Historical holdout is reserved for this run, not guaranteed untouched by prior project research.",
            "Recent period was inspected in an earlier audit; it is not a blind test.",
            "Bar spreads, current-conversion fee estimate and assumed slippage are approximate; no tick fills.",
            "No matching of live macro, HTF, visual, performance, sizing or execution gates is claimed."]}
    atomic_json(directory/"manifest.json", manifest)
    attach(settings)
    raw = MarketDataFeed(settings).get_rates_range((stamp(train_start)-pd.Timedelta(days=4)).to_pydatetime(), now)
    raw = raw[pd.to_datetime(raw.time,utc=True)+pd.Timedelta(minutes=1) <= pd.Timestamp(now)].reset_index(drop=True)
    raw.to_csv(directory/"candles.csv", index=False)
    frame = prepare_frame(raw)
    for phase in ("training", "holdout", "recent_already_inspected"):
        start, end = (stamp(t) for t in manifest[phase])
        n = int(((pd.to_datetime(frame.time,utc=True) >= start) & (pd.to_datetime(frame.time,utc=True) < end)).sum())
        if n < 600:
            raise ValueError("insufficient_broker_history_for_"+phase)
    cache = cache_signals(frame, manifest["training"][0])
    atomic_json(directory/"signals.json",cache)
    atomic_json(directory/"data.json", {"bars":len(frame),"sha256":hashlib.sha256((directory/"candles.csv").read_bytes()).hexdigest(),"fee_evidence":fee})
    results = {}; samples = {}; candidates = []
    for strategy in DISTANCES:
        for variant in VARIANTS:
            key = strategy+"/"+variant
            rows = evaluate(frame,cache,strategy,variant,*manifest["training"],settings,rules)
            results[key] = {"training":report_lane(rows)}; samples[key] = {"training":rows}
            stats = metrics(rows)
            if qualifies(stats, minimum_trades=minimum_training): candidates.append((stats["mean_r"],key))
    winner = max(candidates)[1] if candidates else None
    selection = {"frozen_at": datetime.now(timezone.utc).isoformat(), "selected_from_training_only":winner,
        "qualified_training_lanes": len(candidates), "broker_eligible":False, "auto_promotion":False}
    atomic_json(directory/"selection.json",selection)
    for key in results:
        strategy,variant = key.split("/")
        for phase in ("holdout","recent_already_inspected"):
            rows = evaluate(frame,cache,strategy,variant,*manifest[phase],settings,rules)
            results[key][phase] = report_lane(rows); samples[key][phase] = rows
    winner_passed = bool(winner and qualifies(results[winner]["holdout"]["configured_costs"],minimum_trades=minimum_holdout))
    atomic_json(directory/"results.json", {"lanes":results, "selection":selection,
        "selected_candidate_passed_holdout":winner_passed,"broker_eligible":False,"orders_sent":0})
    atomic_json(directory/"samples.json",samples)
    print(json.dumps({"run_dir":str(directory),"training_winner":winner,"passed_holdout":winner_passed,"bars":len(frame)}),flush=True)


def forward_once(directory):
    manifest = json.loads((directory/"manifest.json").read_text())
    if manifest["sources"] != hashes():
        raise ValueError("frozen_research_source_changed")
    selection = json.loads((directory/"selection.json").read_text())
    settings = replace(load_settings(),execute_trades=False,timeframe="M1",**manifest["simulator_settings"])
    if settings.symbol != manifest["symbol"]:
        raise ValueError("frozen_symbol_changed")
    attach(settings)
    now = datetime.now(timezone.utc)
    raw = MarketDataFeed(settings).get_rates(5000)
    raw = raw[pd.to_datetime(raw.time,utc=True)+pd.Timedelta(minutes=1) <= pd.Timestamp(now)].reset_index(drop=True)
    frame = prepare_frame(raw)
    if stamp(frame.iloc[1200]["time"]) > stamp(selection["frozen_at"]):
        raise RuntimeError("forward_history_gap")
    path = directory/"forward_signals.json"
    cache = cache_signals(frame,selection["frozen_at"],json.loads(path.read_text()) if path.exists() else {})
    atomic_json(path,cache)
    lanes = {}
    for strategy in DISTANCES:
        for variant in VARIANTS:
            key=strategy+"/"+variant
            rows=evaluate(frame,cache,strategy,variant,selection["frozen_at"],now.isoformat(),settings,manifest["rules"])
            lanes[key]={"summary":report_lane(rows),"paper_outcomes":rows}
    payload={"checked_at":now.isoformat(),"state":"observing_frozen_rules","forward_start":selection["frozen_at"],
        "orders_sent":0,"broker_eligible":False,"source_hashes_verified":True,"lanes":lanes}
    atomic_json(directory/"forward.json",payload)
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("audit","forward-once","watch"))
    parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--fee-file",type=Path)
    parser.add_argument("--hours",type=float,default=24)
    parser.add_argument("--train-start",default="2026-11-02T00:00:00Z")
    parser.add_argument("--train-end",default="2026-11-05T00:00:00Z")
    parser.add_argument("--holdout-end",default="2026-11-07T00:00:00Z")
    parser.add_argument("--recent-start",default="2026-11-09T00:00:00Z")
    parser.add_argument("--minimum-training",type=int,default=12)
    parser.add_argument("--minimum-holdout",type=int,default=10)
    args=parser.parse_args()
    if args.mode=="audit":
        if args.fee_file is None:parser.error("--fee-file is required for audit")
        audit(args.run_dir,args.fee_file,train_start=args.train_start,train_end=args.train_end,
            holdout_end=args.holdout_end,recent_start=args.recent_start,
            minimum_training=args.minimum_training,minimum_holdout=args.minimum_holdout)
        return
    if args.mode=="forward-once":forward_once(args.run_dir);return
    deadline=time.monotonic()+args.hours*3600
    while time.monotonic()<deadline:
        try:
            forward_once(args.run_dir)
        except Exception as exc:
            atomic_json(args.run_dir/"forward.json",{"checked_at":datetime.now(timezone.utc).isoformat(),
                "state":"observation_error","error":type(exc).__name__,"reason":str(exc),"orders_sent":0,"broker_eligible":False})
            if isinstance(exc,ValueError):raise
        time.sleep(min(60,max(0,deadline-time.monotonic())))
    path=args.run_dir/"forward.json"
    last=json.loads(path.read_text()) if path.exists() else {}
    atomic_json(path,{**last,"state":"observation_window_completed","completed_at":datetime.now(timezone.utc).isoformat(),"orders_sent":0,"broker_eligible":False})


if __name__=="__main__":main()
