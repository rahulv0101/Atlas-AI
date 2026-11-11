"""Collect new paper evidence from the existing candle journal, without broker I/O."""
import argparse
from dataclasses import replace
from datetime import datetime,timezone
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import Settings
from atlas_ai.learning.observation_checkpoint import observation_lock
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.strategies.research_protocol import environment_versions
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import cache_candidates,replay
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import digest,qualified


def validate(directory):
    for name in ("manifest","selection"):
        if digest(directory/f"{name}.json")!=(directory/f"{name}.sha256").read_text().strip():
            raise ValueError("frozen_research_protocol_changed")
    manifest=json.loads((directory/"manifest.json").read_text())
    if manifest["schema"]!="atlas_guarded_research_v2":raise ValueError("unsupported_research_confidence_protocol")
    if manifest["broker_eligible"] is not False or manifest["auto_promotion"] is not False:
        raise ValueError("paper_only_boundary_required")
    if manifest["environment"]!=environment_versions():raise ValueError("frozen_environment_changed")
    snapshot=directory/"frozen_source"
    for name,expected in manifest["source_hashes"].items():
        path=(snapshot/name).resolve();path.relative_to(snapshot.resolve())
        if digest(path)!=expected:raise ValueError("frozen_research_source_changed")
    return manifest,json.loads((directory/"selection.json").read_text())


def stage_stats(trades):
    wins=sum(t["net_cash"]>0 for t in trades)
    positive=sum(t["net_cash"] for t in trades if t["net_cash"]>0)
    negative=-sum(t["net_cash"] for t in trades if t["net_cash"]<0)
    total=peak=drawdown=0.
    for trade in trades:total+=trade["net_r"];peak=max(peak,total);drawdown=max(drawdown,peak-total)
    return {"trades":len(trades),"wins":wins,"profit_factor":positive/negative if negative else None,
        "mean_net_r":sum(t["net_r"] for t in trades)/len(trades) if trades else None,
        "max_drawdown_r":drawdown,"trade_list":trades}


def once(directory):
    manifest,selection=validate(directory)
    if not selection["selected_for_forward"]:
        return {"state":"no_training_candidate","broker_eligible":False,"orders_sent":0}
    if datetime.now(timezone.utc)>=datetime.fromisoformat(manifest["deadline"]):
        return {"state":"deadline_reached","broker_eligible":False,"orders_sent":0}
    source=Path(manifest["forward_source_run"])
    artifacts=json.loads((source/"artifacts.json").read_text());data=(source/"observed_candles.csv").read_bytes()
    import hashlib
    if hashlib.sha256(data).hexdigest()!=artifacts.get("observed_candles.csv"):
        return {"state":"waiting_for_consistent_source_snapshot","broker_eligible":False,"orders_sent":0}
    frame=prepare_frame(pd.read_csv(StringIO(data.decode("utf-8"))))
    freeze=pd.Timestamp(manifest["future_holdout_start"])
    first=int(pd.to_datetime(frame.time,utc=True).searchsorted(freeze))
    frame=frame.iloc[max(0,first-1200):].reset_index(drop=True)
    records=json.loads(frame.to_json(orient="records",date_format="iso",double_precision=15))
    integrity=directory/"forward_integrity.json"
    if integrity.exists():
        hashes=json.loads(integrity.read_text())
        if set(hashes)!={"forward_candles.json","forward_candidates.json","forward_state.json"}:
            raise ValueError("incomplete_forward_integrity")
        for name,expected in hashes.items():
            if digest(directory/name)!=expected:raise ValueError("forward_evidence_changed")
        old=json.loads((directory/"forward_candles.json").read_text())
        if records[:len(old)]!=old:raise ValueError("previously_observed_candles_revised")
        candidates=json.loads((directory/"forward_candidates.json").read_text())
        state=json.loads((directory/"forward_state.json").read_text())
    else:
        if any((directory/name).exists() for name in ("forward_candles.json","forward_candidates.json","forward_state.json")):
            raise ValueError("unverified_forward_evidence")
        candidates=[];state={"last_processed_index":249}
    cfg=dict(manifest["settings"]);cfg.update(execute_trades=False,gemini_api_key="",openai_api_key="")
    chosen,variant_name,slip=selection["selected_for_forward"].split("/")
    variant=next(ExitVariant(**v) for v in manifest["variants"] if v["name"]==variant_name
        and v["slippage_points_per_side"]==float(slip.removeprefix("slip_")))
    def deny(*args,**kwargs):raise AssertionError("paper_observer_cannot_access_broker")
    with tempfile.TemporaryDirectory(prefix="atlas_new_forward_") as folder,patch.object(mt5,"order_send",deny),patch.object(mt5,"initialize",deny):
        settings=Settings(0,"","",**{**cfg,"storage_dir":folder})
        store=KnowledgeStore(folder)
        additional,_,_=cache_candidates(frame,settings,store,start_index=state["last_processed_index"]+1)
        candidates.extend(additional);state["last_processed_index"]=max(249,len(frame)-2)
        result=replay(frame,candidates,settings,BrokerSpec(**manifest["spec"]),variant,store,
            manifest["limits"],strategy=None if chosen=="combined" else chosen,start=freeze.to_pydatetime())
    first_stage=stage_stats(result["trade_list"][:30]);second_stage=stage_stats(result["trade_list"][30:60])
    summary={"state":"completed_evidence_requires_review" if result["trades"]>=60 else "collecting_new_paper_outcomes",
        "checked_at":datetime.now(timezone.utc).isoformat(),"future_holdout_start":manifest["future_holdout_start"],
        "first_stage":first_stage,"first_stage_passed":qualified(first_stage),
        "validation_stage":second_stage,"validation_stage_passed":qualified(second_stage),
        "new_paper_outcomes":result["trades"],"rejections":result["rejections"],"broker_eligible":False,
        "orders_sent":0,"full_live_policy_parity":False,
        "note":"New data for one frozen research hypothesis; no real fills, historical visual/macro parity or automatic promotion."}
    atomic_json(directory/"forward_candles.json",records)
    atomic_json(directory/"forward_candidates.json",candidates)
    atomic_json(directory/"forward_state.json",state)
    atomic_json(integrity,{name:digest(directory/name) for name in ("forward_candles.json","forward_candidates.json","forward_state.json")})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--watch",action="store_true");args=parser.parse_args()
    with observation_lock(args.run_dir/"forward.lock"):
        while True:
            try:result=once(args.run_dir)
            except Exception as exc:
                result={"state":"blocked_evidence_review_required","error":type(exc).__name__,"reason":str(exc),"orders_sent":0,"broker_eligible":False}
            atomic_json(args.run_dir/"forward_status.json",result)
            if not args.watch or result["state"] not in {"collecting_new_paper_outcomes","waiting_for_consistent_source_snapshot"}:return
            time.sleep(600)


if __name__=="__main__":main()
