"""Predeclared offline score-filter experiment on an existing frozen dataset.

Earlier historical periods have been inspected: results are exploratory and
cannot qualify a candidate for broker promotion or substitute for future tests.
"""
from copy import deepcopy
from dataclasses import replace
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
from tools.cost_aware_strategy_audit import prepare_frame,evaluate,report_lane,hashes,DISTANCES

MINIMUM_RAW_SCORE=.55
VARIANTS=("atr_points_immediate","atr_points_confirmed_retest")


def filtered_cache(cache):
    result=deepcopy(cache)
    for signals in result.values():
        for signal in signals:
            if signal["confidence"]<MINIMUM_RAW_SCORE:
                signal.update(side="flat",confidence=0.)
    return result


def run(source,output):
    manifest=json.loads((source/"manifest.json").read_text())
    if manifest["sources"]!=hashes():raise ValueError("source_experiment_changed")
    data=json.loads((source/"data.json").read_text())
    if hashlib.sha256((source/"candles.csv").read_bytes()).hexdigest()!=data["sha256"]:
        raise ValueError("source_data_changed")
    output.mkdir(parents=True,exist_ok=False)
    atomic_json(output/"manifest.json",{"created_at":datetime.now(timezone.utc).isoformat(),
        "minimum_raw_score":MINIMUM_RAW_SCORE,"variants":VARIANTS,"strategies":list(DISTANCES),
        "input_manifest_sha256":hashlib.sha256((source/"manifest.json").read_bytes()).hexdigest(),
        "signals_sha256":hashlib.sha256((source/"signals.json").read_bytes()).hexdigest(),
        "source_hashes":{**hashes(),"tools/candidate_score_audit.py":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "hypothesis":"A fixed raw candidate score floor of 0.55 may exclude weak entry triggers; no threshold search.",
        "periods_already_inspected":True,"broker_eligible":False,"auto_promotion":False,"orders_sent":0})
    frame=prepare_frame(pd.read_csv(source/"candles.csv"))
    cache=filtered_cache(json.loads((source/"signals.json").read_text()))
    settings=replace(load_settings(),execute_trades=False,timeframe="M1",**manifest["simulator_settings"])
    results={}
    for strategy in DISTANCES:
        for variant in VARIANTS:
            key=f"{strategy}/{variant}";results[key]={}
            for phase in ("training","holdout","recent_already_inspected"):
                rows=evaluate(frame,cache,strategy,variant,*manifest[phase],settings,manifest["rules"])
                results[key][phase]=report_lane(rows)
            print(json.dumps({"comparison_completed":key}),flush=True)
    atomic_json(output/"results.json",{"lanes":results,"broker_eligible":False,"orders_sent":0,
        "conclusion_boundary":"Exploratory comparison only. Future evidence is required; no broker selection is made."})


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--source-run",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True);args=p.parse_args();run(args.source_run,args.output_dir)
