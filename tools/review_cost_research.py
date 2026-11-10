"""Review frozen research evidence per comparison; never promote or place orders."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.atomic_files import atomic_json


def stage_requirements(stats, minimum):
    try:
        values=[float(stats[key]) for key in ("trades","days","mean_r","max_drawdown_r","wins","losses")]
        if not all(math.isfinite(v) for v in values):raise ValueError("nonfinite")
        if any(float(stats[key])<0 for key in ("trades","days","max_drawdown_r","wins","losses")):raise ValueError("negative_counts")
        factor=stats.get("profit_factor")
        if factor is not None and (not math.isfinite(float(factor)) or float(factor)<0):
            raise ValueError("invalid_profit_factor")
    except (KeyError,TypeError,ValueError,OverflowError):return ["missing_or_invalid_stats"]
    reasons=[]
    if stats.get("trades",0)<minimum:reasons.append("insufficient_trades")
    if stats.get("days",0)<2:reasons.append("insufficient_days")
    if (stats.get("mean_r") or 0)<=0:reasons.append("nonpositive_cost_adjusted_mean")
    if not ((stats.get("profit_factor") or 0)>=1.1 or stats.get("losses")==0 and stats.get("wins",0)>0):
        reasons.append("profit_factor_requirement")
    if stats.get("max_drawdown_r",float("inf"))>6:reasons.append("drawdown_requirement")
    return reasons


def review_lanes(historical, forward, source_valid=True, evidence_current=True, minimum_cases=None, eligible_keys=None):
    minimum_cases=minimum_cases or {"training":12,"holdout":10,"forward":30}
    lanes={}
    for key,history in historical.items():
        paper=forward.get(key,{}).get("summary",{}).get("configured_costs",{})
        pending={phase:stage_requirements(stats,minimum) for phase,stats,minimum in (
            ("training",history.get("training",{}).get("configured_costs",{}),minimum_cases["training"]),
            ("holdout",history.get("holdout",{}).get("configured_costs",{}),minimum_cases["holdout"]),
            ("forward",paper,minimum_cases["forward"]))}
        ready=source_valid and evidence_current and not any(pending.values()) and (eligible_keys is None or key in eligible_keys)
        lanes[key]={"operator_review_ready":ready,"pending":pending,
            "forward_trades":paper.get("trades",0),"forward_days":paper.get("days",0),
            "broker_eligible":False}
    return {"comparisons":len(lanes),"operator_review_ready_count":sum(v["operator_review_ready"] for v in lanes.values()),
        "source_integrity_verified":source_valid,"observation_evidence_current":evidence_current,
        "lanes":lanes,"broker_eligible":False,"orders_sent":0,
        "policy_note":"Requirements apply per comparison, not to summed overlapping paper outcomes. Review readiness never authorizes broker promotion."}


def review(directory):
    manifest=json.loads((directory/"manifest.json").read_text())
    base=directory/"frozen_source" if (directory/"frozen_source").is_dir() else ROOT
    valid=True
    for path,digest in manifest["sources"].items():
        source=(base/path).resolve()
        try:source.relative_to(base.resolve())
        except ValueError:valid=False;continue
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:valid=False
    historical=json.loads((directory/"results.json").read_text())["lanes"]
    forward_path=directory/"forward.json"
    forward=json.loads(forward_path.read_text()) if forward_path.exists() else {}
    try:
        checked=datetime.fromisoformat(forward.get("checked_at","").replace("Z","+00:00"))
        fresh=checked.tzinfo is not None and 0<=(datetime.now(timezone.utc)-checked).total_seconds()<=180
    except (ValueError,TypeError,AttributeError):
        fresh=False
    selection=json.loads((directory/"selection.json").read_text()).get("selected_from_training_only")
    result=review_lanes(historical,forward.get("lanes",{}),source_valid=valid,
        evidence_current=fresh and forward.get("state")=="observing_frozen_rules",
        minimum_cases=manifest.get("minimum_cases"),eligible_keys={selection} if selection else set())
    result.update(checked_at=datetime.now(timezone.utc).isoformat(),forward_asof=forward.get("checked_at"))
    atomic_json(directory/"qualification_review.json",result)
    print(json.dumps({k:result[k] for k in ("comparisons","operator_review_ready_count","source_integrity_verified","forward_asof","broker_eligible")}))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run-dir",type=Path,required=True)
    review(p.parse_args().run_dir.resolve())
