"""Baseline-only offline review of the operator's retained evolved strategies."""
from __future__ import annotations
import argparse
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.strategies.strategy_lab import EvolvedRuleStrategy
from atlas_ai.strategies.strategy_factory import StrategyFactory
from atlas_ai.strategies.evolution_integration import load_demo_chromosome_pool
from tools.cost_aware_strategy_audit import prepare_frame, stamp, evaluate, report_lane


def main(directory):
    manifest=json.loads((directory/"manifest.json").read_text())
    settings=replace(load_settings(),execute_trades=False,timeframe="M1",**manifest["simulator_settings"])
    raw=json.loads((Path(settings.storage_dir)/"learning_state.json").read_text()).get("state",{})
    specs=list(raw.get("evolved_strategy_pool",{}).get("candidates",[]))
    if raw.get("best_evolved_strategy"):specs.insert(0,raw["best_evolved_strategy"])
    if not specs:specs=[{"fast":20,"slow":50,"rsi_buy":45.,"rsi_sell":55.}]
    pack=[];seen=set();snapshot=[]
    for spec in specs[:settings.evolved_strategy_survivors]:
        parameters={k:spec[k] for k in ("fast","slow","rsi_buy","rsi_sell")}
        key=json.dumps(parameters,sort_keys=True)
        if key in seen:continue
        seen.add(key)
        s=EvolvedRuleStrategy(**parameters)
        s.name="evolved_rule("+",".join(f"{k}={v}" for k,v in parameters.items())+")"
        pack.append(s);snapshot.append({"name":s.name,"parameters":parameters})
    chromosomes,_=load_demo_chromosome_pool(settings.storage_dir)
    for c in chromosomes:
        s=StrategyFactory.build(c,point_size=manifest["rules"]["point"])
        pack.append(s);snapshot.append({"name":s.name,"chromosome":c.to_dict()})
    atomic_json(directory/"legacy_manifest.json",{"strategies":snapshot,"mode":"offline_baseline_only",
        "source_hashes":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ("tools/legacy_strategy_cost_audit.py","atlas_ai/strategies/strategy_factory.py","atlas_ai/strategies/strategy_lab.py")},
        "broker_eligible":False,"orders_sent":0})
    frame=prepare_frame(pd.read_csv(directory/"candles.csv"))
    cache={}
    for i in range(1200,len(frame)):
        at=stamp(frame.time.iloc[i])
        if at<stamp(manifest["training"][0]):continue
        cache[at.isoformat()]=[asdict(s.generate_signal(frame.iloc[i-1199:i+1])) for s in pack]
        if i%2000==0:print(json.dumps({"legacy_progress":str(at)}),flush=True)
    results={}
    for s in pack:
        results[s.name]={}
        for phase in ("training","holdout","recent_already_inspected"):
            rows=evaluate(frame,cache,s.name,"current_immediate",*manifest[phase],settings,manifest["rules"])
            results[s.name][phase]=report_lane(rows)
    atomic_json(directory/"legacy_results.json",{"lanes":results,"orders_sent":0,"broker_eligible":False,
        "limitations":["Baseline only; six built-in entry/distance variants are evaluated separately.",
            "Current frozen parameters are replayed historically; this is not a claim that these parameters existed then."]})
    print(json.dumps({"legacy_strategies":list(results)}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run-dir",type=Path,required=True)
    main(p.parse_args().run_dir)
