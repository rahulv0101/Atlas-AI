"""One frozen, closed-H1-aligned M15 hypothesis. Read-only demo paper data.

Two successive 30-case stages are required for research review. No broker
eligibility or automatic promotion is provided, even after passing both.
"""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.data.timeframe_bias import bias_from_closes
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.strategies.minute_pack import PullbackTrendM15MidExitStrategy
from atlas_ai.strategies.research_protocol import environment_versions
from tools.closed_timeframe_research import closed_bars,signal_cache,evaluate,clock_settings,sources
from tools.cost_aware_strategy_audit import prepare_frame,stamp,report_lane,qualifies,attach
from tools.observe_cost_research import observer_lock


def fingerprints():
    names=("tools/prospective_pullback.py","atlas_ai/data/timeframe_bias.py",
        "atlas_ai/data/market_data.py","atlas_ai/data/broker_clock.py","atlas_ai/learning/observation_checkpoint.py")
    return {**sources(),**{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}


def filter_h1(frame,candidates):
    quarter=closed_bars(frame,15);hours=[]
    for at,group in quarter.groupby(quarter.time.dt.floor("h")):
        if len(group)==4 and list(group.time)==list(pd.date_range(at,periods=4,freq="15min")):
            hours.append({"available_at":stamp(at)+pd.Timedelta(hours=1),"close":float(group.close.iloc[-1])})
    kept=[]
    for candidate in candidates:
        at=stamp(candidate["available_at"])
        available=[h for h in hours if h["available_at"]<=at]
        bias=bias_from_closes(h["close"] for h in available[-30:])
        if bias==candidate["signal"]["side"]:
            kept.append({**candidate,"h1_bias":bias,"h1_available_at":available[-1]["available_at"].isoformat()})
    return kept


def stage_report(rows):
    stages={}
    for name,part in (("first",rows[:30]),("validation",rows[30:60])):
        stats=report_lane(part)["configured_costs"]
        stages[name]={"stats":stats,"passed":qualifies(stats,minimum_trades=30)}
    return {"stages":stages,"total_paper_outcomes":len(rows),"research_review_ready":all(v["passed"] for v in stages.values()),
        "broker_eligible":False,"orders_sent":0,
        "note":"Stages are sequential nonoverlapping cases under one frozen rule; passing never activates broker trading."}


def start(directory,source):
    original=json.loads((source/"manifest.json").read_text())
    if original["symbol"]!="XAUUSD":raise ValueError("XAUUSD_required")
    settings=load_settings()
    if settings.symbol!=original["symbol"]:raise ValueError("matching_configured_symbol_required")
    directory.mkdir(parents=True,exist_ok=False)
    atomic_json(directory/"manifest.json",{"schema":"atlas_prospective_pullback_v1",
        "frozen_at":datetime.now(timezone.utc).isoformat(),"symbol":"XAUUSD",
        "account_scope":account_scope(settings),"broker_clock_timezone":settings.mt5_server_timezone,
        "hypothesis":"Existing M15 pullback template with corrected ATR points, native-bar stale exit and completed-H1 bias agreement. No parameter search.",
        "source_hashes":fingerprints(),"environment":environment_versions(),
        "rules":{k:v for k,v in original["rules"].items() if k!="hold_bars"},"hold_minutes":60,"exit_clock":"strategy",
        "simulator_settings":original["simulator_settings"],"source_manifest_sha256":hashlib.sha256((source/"manifest.json").read_bytes()).hexdigest(),
        "minimum_cases_per_stage":30,"minimum_days_per_stage":2,"profit_factor_minimum":1.1,"max_drawdown_r":6,
        "broker_eligible":False,"auto_promotion":False,"orders_sent":0,
        "limitations":["New hypothesis motivated by inspected historical work; only subsequent paper data counts.",
            "Modeled costs retain the 1.5-basis-point stress assumption; two diagnostic fills do not calibrate it.",
            "Paper open prices and bar paths do not prove natural broker execution or live-account profitability."]})
    (directory/"manifest.sha256").write_text(hashlib.sha256((directory/"manifest.json").read_bytes()).hexdigest(),encoding="ascii")


def once(directory):
    if hashlib.sha256((directory/"manifest.json").read_bytes()).hexdigest()!=(directory/"manifest.sha256").read_text(encoding="ascii").strip():
        raise ValueError("frozen_paper_manifest_changed")
    m=json.loads((directory/"manifest.json").read_text())
    if m["source_hashes"]!=fingerprints() or m["environment"]!=environment_versions():
        raise ValueError("frozen_paper_protocol_changed")
    integrity_path=directory/"artifacts.json"
    if integrity_path.exists():
        digests=json.loads(integrity_path.read_text())
        if set(digests)!={"observed_candles.csv","signals.json"}:raise ValueError("incomplete_paper_artifact_integrity")
        for name,digest in digests.items():
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:
                raise ValueError("paper_observation_artifact_changed")
    elif any((directory/name).exists() for name in ("observed_candles.csv","signals.json")):
        raise ValueError("unverified_paper_observation_artifacts")
    current=load_settings()
    if account_scope(current)!=m["account_scope"]:raise ValueError("paper_account_scope_changed")
    settings=replace(current,execute_trades=False,symbol=m["symbol"],timeframe="M1",
        mt5_server_timezone=m["broker_clock_timezone"],**m["simulator_settings"])
    attach(settings);now=datetime.now(timezone.utc)
    raw=MarketDataFeed(settings).get_rates(5000)
    raw=raw[pd.to_datetime(raw.time,utc=True)+pd.Timedelta(minutes=1)<=pd.Timestamp(now)].reset_index(drop=True)
    frame=prepare_frame(raw)
    age=(pd.Timestamp(now)-stamp(frame.time.iloc[-1])).total_seconds()
    if not 0<=age<=180:
        result={"state":"waiting_for_fresh_bars","checked_at":now.isoformat(),"broker_eligible":False,"orders_sent":0}
        atomic_json(directory/"status.json",result);return result
    data_path=directory/"observed_candles.csv"
    if data_path.exists():
        old=prepare_frame(pd.read_csv(data_path))
        last=old.time.iloc[-1]
        if frame.time.iloc[0]>last+pd.Timedelta(minutes=1):raise ValueError("paper_history_gap")
        frame=prepare_frame(pd.concat([old,frame[frame.time>last]],ignore_index=True))
    if len(frame)>60000:raise ValueError("paper_history_bound_reached")
    # Only append subsequently closed bars; never replace the frozen past with revisions.
    temporary=data_path.with_suffix(".tmp.csv");frame.drop(columns=["atr_price"]).to_csv(temporary,index=False)
    from atlas_ai.atomic_files import replace_with_retry
    replace_with_retry(temporary,data_path)
    tail=frame.tail(5000).reset_index(drop=True)
    candidates=filter_h1(tail,signal_cache(tail,15,PullbackTrendM15MidExitStrategy(),m["rules"]["point"]))
    cache_path=directory/"signals.json"
    cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for candidate in candidates:
        if stamp(candidate["available_at"])>=stamp(m["frozen_at"]):cache.setdefault(candidate["available_at"],candidate)
    atomic_json(cache_path,cache)
    outcomes=evaluate(frame,[cache[k] for k in sorted(cache)],m["frozen_at"],now.isoformat(),clock_settings(settings,15,"strategy"),m["rules"])
    if m["source_hashes"]!=fingerprints():raise ValueError("paper_source_changed_during_evaluation")
    result={**stage_report(outcomes),"state":"observing_frozen_paper_hypothesis","checked_at":now.isoformat(),
        "latest_closed_bar":stamp(frame.time.iloc[-1]).isoformat(),"frozen_at":m["frozen_at"]}
    atomic_json(directory/"outcomes.json",outcomes);atomic_json(directory/"status.json",result)
    atomic_json(integrity_path,{name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
        for name in ("observed_candles.csv","signals.json")})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("mode",choices=("start","once","watch"))
    p.add_argument("--run-dir",type=Path,required=True);p.add_argument("--source-run",type=Path)
    p.add_argument("--hours",type=float,default=168);a=p.parse_args()
    if not 0<a.hours<=168:p.error("At most seven days per observation invocation")
    if a.mode=="start":
        if a.source_run is None:p.error("--source-run required")
        start(a.run_dir,a.source_run);return
    deadline=time.monotonic()+a.hours*3600
    window_end=(datetime.now(timezone.utc)+timedelta(hours=a.hours)).isoformat()
    with observer_lock(a.run_dir/"observer.lock"):
        while time.monotonic()<deadline:
            try:
                result=once(a.run_dir)
                result["window_ends_at"]=window_end
                atomic_json(a.run_dir/"status.json",result)
            except Exception as exc:
                atomic_json(a.run_dir/"status.json",{"state":"observation_error","checked_at":datetime.now(timezone.utc).isoformat(),
                    "error":type(exc).__name__,"reason":str(exc),"orders_sent":0,"broker_eligible":False})
                if isinstance(exc,ValueError):raise
            if a.mode=="once":return
            time.sleep(min(60,max(0,deadline-time.monotonic())))
    last=json.loads((a.run_dir/"status.json").read_text());last.update(state="observation_window_completed")
    atomic_json(a.run_dir/"status.json",last)


if __name__=="__main__":main()
