"""Isolated historical engine audit, not a claim of complete live-system parity."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.backtest import Backtester
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.learning.trade_labeling import _simulate_trade_path
from atlas_ai.models import TradeSignal
from tools.cost_aware_strategy_audit import attach,prepare_frame
from tools import timing_discipline_matched_backtest as matched


LIMITATIONS=[
    "Historical engine and timing replay are separate lanes, not the complete live AtlasTrader pipeline.",
    "Core uses its research confidence threshold, configured strategy selection, fresh allocator and simulated exits; it does not enforce all live risk/session/sizing gates.",
    "Timing replay uses derived chart features, zero spread in context, gross overlapping hypothetical paths and its research confidence threshold; it is not an executable portfolio return.",
    "Live macro, Gemini, screenshots, historical runtime settings, broker fills, real commissions and MT5 protection acknowledgements are not reconstructed.",
    "Core spread/slippage are fixed account-return basis points, not measured venue execution costs; same-bar stop/target ambiguity uses candle direction.",
    "Current strategy parameters replayed on previously inspected history do not constitute blind out-of-sample evidence.",
    "No result replaces the frozen prospective stages, proves natural broker execution or authorizes strategy activation.",
]


def data_summary(frame,start,end):
    if len(frame)<1000:raise ValueError("insufficient_history_for_system_audit")
    times=pd.to_datetime(frame.time,utc=True)
    if (times.iloc[0]<pd.Timestamp(start) or times.iloc[-1]+pd.Timedelta(minutes=1)>pd.Timestamp(end)):
        raise ValueError("history_outside_closed_requested_window")
    gaps=times.diff().dt.total_seconds().dropna()
    return {"bars":len(frame),"actual_start_utc":times.iloc[0].isoformat(),"actual_last_bar_utc":times.iloc[-1].isoformat(),
        "trading_dates":int(times.dt.date.nunique()),"gaps_over_one_minute":int((gaps>60).sum()),
        "largest_gap_minutes":float(gaps.max()/60),"note":"Gaps include scheduled market closures; requested availability is not assumed."}


def policy(settings,backtester):
    names=("max_risk_per_trade","research_confidence_threshold","backtest_initial_balance",
        "backtest_include_evolved","backtest_evolved_refresh_bars","backtest_evolved_lookback_bars",
        "backtest_spread_cost_bps","backtest_slippage_cost_bps","backtest_max_hold_bars","backtest_point_size",
        "backtest_break_even_r_trigger","backtest_break_even_lock_r","backtest_trailing_r_trigger",
        "backtest_trailing_buffer_r","backtest_stale_exit_bars","backtest_stale_min_progress_r","exploration_epsilon")
    return {**{name:getattr(settings,name) for name in names},
        "base_strategies_available":[s.name for s in backtester.base],
        "base_strategies_enabled":[s.name for s in backtester.base if backtester._strategy_enabled(s.name)],
        "configured_enabled_strategies":list(settings.enabled_strategies),
        "configured_disabled_strategies":list(settings.disabled_strategies)}


def timing_sensitivity(frame,rows,settings):
    """Fixed-stream sensitivity, never an allocator or live-policy replay."""
    cost=(settings.backtest_spread_cost_bps+settings.backtest_slippage_cost_bps)/10000/settings.max_risk_per_trade
    variants={name:[] for name in ("recorded_gross","recorded_fixed_costs","stop_first_fixed_costs","nonoverlap_stop_first_fixed_costs")}
    mismatches=[];previous=-1;overlap=0
    for row in rows:
        signal=TradeSignal(row["strategy"],row["side"],row["confidence"],row["stop_loss_points"],row["take_profit_points"])
        original=_simulate_trade_path(frame,signal,row["signal_bar"],settings,ambiguous_bar_policy="candle_direction")
        conservative=_simulate_trade_path(frame,signal,row["signal_bar"],settings,ambiguous_bar_policy="stop_first")
        if not math.isclose(original["r_multiple"],row["r_multiple"],abs_tol=1e-6):mismatches.append(row["signal_bar"])
        variants["recorded_gross"].append(row["r_multiple"])
        variants["recorded_fixed_costs"].append(row["r_multiple"]-cost)
        variants["stop_first_fixed_costs"].append(conservative["r_multiple"]-cost)
        if row["entry_bar"]<=previous:overlap+=1
        else:
            variants["nonoverlap_stop_first_fixed_costs"].append(conservative["r_multiple"]-cost)
            previous=conservative["exit_idx"]
    def stats(values):
        positive=sum(v for v in values if v>0);negative=-sum(v for v in values if v<0)
        total=peak=drawdown=0.
        for value in values:total+=value;peak=max(peak,total);drawdown=max(drawdown,peak-total)
        return {"trades":len(values),"mean_r":sum(values)/len(values) if values else None,"sum_r":sum(values),
            "profit_factor":positive/negative if negative else None,"max_drawdown_r":drawdown}
    return {"recorded_allowed_candidates":len(rows),"fixed_model_cost_r":cost,
        "candle_direction_reproduction_mismatches":mismatches,
        "overlapping_rows_excluded_in_conservative_greedy_subsample":overlap,
        "variants":{name:stats(values) for name,values in variants.items()},"broker_eligible":False,"orders_sent":0,
        "limitations":["Fixed recorded stream; allocator/candidate choices are not regenerated.",
            "No complete live risk/session replay; fixed costs remain uncalibrated."]}


def run(directory,start,end):
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=False)
    (directory/"executed_runner.py").write_bytes(Path(__file__).read_bytes())
    original=load_settings()
    # Snapshot only source hashes, never environment secrets or whole Settings.
    source_hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in (ROOT/"atlas_ai",ROOT/"tools") for p in folder.rglob("*.py")}
    def blocked_order(*args,**kwargs):raise AssertionError("historical_audit_cannot_dispatch_broker_orders")
    result={"schema":"atlas_historical_system_audit_v1","started_at":datetime.now(timezone.utc).isoformat(),
        "requested_start_utc":start.isoformat(),"requested_end_utc":end.isoformat(),
        "symbol":original.symbol,"timeframe":"M1","source_hashes":source_hashes,
        "orders_sent":0,"broker_eligible":False,"live_system_parity":False,"limitations":LIMITATIONS}
    report=directory/"report.json"
    def progress(stage,**extra):
        atomic_json(directory/"progress.json",{"stage":stage,"checked_at":datetime.now(timezone.utc).isoformat(),**extra})
    progress("fetching_closed_broker_history")
    try:
        with tempfile.TemporaryDirectory(prefix="isolated_",dir=directory) as isolated,patch.object(mt5,"order_send",blocked_order):
            settings=replace(original,execute_trades=False,timeframe="M1",storage_dir=isolated,
                backtest_persist_learning_state=False,backtest_record_loss_analysis=False,
                gemini_api_key="",openai_api_key="")
            attach(settings)
            raw=MarketDataFeed(settings).get_rates_range(start,end)
            raw=raw[pd.to_datetime(raw.time,utc=True)+pd.Timedelta(minutes=1)<=pd.Timestamp(end)].reset_index(drop=True)
            frame=prepare_frame(raw)
            result["data"]=data_summary(frame,start,end)
            frame.to_csv(directory/"candles.csv",index=False)
            result["data"]["sha256"]=hashlib.sha256((directory/"candles.csv").read_bytes()).hexdigest()
            backtester=Backtester(settings=settings)
            result["policy"]=policy(settings,backtester)
            atomic_json(report,result);progress("core_backtest",bars=len(frame))
            simulate=backtester._simulate_trade;count=0
            def tracked(*args,**kwargs):
                nonlocal count
                outcome=simulate(*args,**kwargs);count+=1
                if count%100==0:progress("core_backtest",simulated_trades=count,signal_bar=int(args[-1]))
                return outcome
            backtester._simulate_trade=tracked
            result["core"]=asdict(backtester.run(frame))
            atomic_json(report,result);progress("timing_filter_replay")
            class FrozenFeed:
                last_fetch_meta={"source":"saved_closed_bar_snapshot","timestamp_basis":"UTC"}
                def __init__(self,*args):pass
                def get_rates_range(self,*args):return frame.copy()
            generate=matched._generate_replay_signal;last_bar=-1
            def tracked_generate(strategy,data,index):
                nonlocal last_bar
                if index%1000==0 and index!=last_bar:
                    progress("timing_filter_replay",signal_bar=index,bars=len(data));last_bar=index
                return generate(strategy,data,index)
            with patch.object(matched,"load_settings",return_value=settings),patch.object(matched,"MarketDataFeed",FrozenFeed),patch.object(matched,"BASELINE_DIR",directory),patch.object(matched,"_generate_replay_signal",tracked_generate),patch("atlas_ai.market_context._fresh_external_context_fields",return_value={}):
                path=matched.run_matched_backtest(start,end,"unchanged_timing_rules",sample_limit=100000)
            result["timing"]=json.loads(path.read_text())
            result["timing_sensitivity"]=timing_sensitivity(frame,result["timing"].get("samples",{}).get("allowed",[]),settings)
            result["state"]="completed_research_only"
            result["finished_at"]=datetime.now(timezone.utc).isoformat()
            atomic_json(report,result);progress("completed_research_only")
            return result
    except Exception as exc:
        result.update(state="failed",error=type(exc).__name__,reason=str(exc))
        atomic_json(report,result);progress("failed",error=type(exc).__name__)
        raise
    finally:mt5.shutdown()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--days",type=int,default=30)
    args=parser.parse_args()
    if not 1<=args.days<=90:parser.error("--days must be between 1 and 90")
    if os.name=="nt":
        import ctypes
        kernel=ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        kernel.SetPriorityClass.restype=ctypes.c_int
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000):
            print("Could not lower audit process priority",file=sys.stderr)
    end=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    result=run(args.output,end-timedelta(days=args.days),end)
    print(json.dumps({"state":result["state"],"report":str(args.output/"report.json"),"core_trades":result["core"]["trades"]}))


if __name__=="__main__":main()
