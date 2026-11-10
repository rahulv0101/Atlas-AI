"""Summarize measured dispatch evidence; never infer fills from broker history."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.atomic_files import atomic_json
from atlas_ai.execution.cost_evidence import finite


def distribution(values):
    values=sorted(values)
    if not values:return {"samples":0,"mean":None,"p50":None,"p95":None}
    def quantile(q):
        at=(len(values)-1)*q;lo=int(at);hi=min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(at-lo)
    return {"samples":len(values),"mean":sum(values)/len(values),"p50":quantile(.5),"p95":quantile(.95)}


def summarize(rows):
    measured=[];diagnostics=0;unknown=0;seen=set()
    for row in rows:
        if row.get("schema")!="atlas_execution_cost_v1":continue
        key=tuple(row.get(k) for k in ("started_at","source","order_id","deal_id"))
        if key in seen:continue
        seen.add(key)
        if row.get("diagnostic"):
            diagnostics+=1;continue
        value=finite(row.get("adverse_fill_difference_bps"))
        if row.get("filled") is not True or value is None:
            unknown+=1;continue
        measured.append(row)
    return {"checked_at":datetime.now(timezone.utc).isoformat(),"state":"collecting" if measured else "awaiting_measured_fills",
        "measured_fill_observations":len(measured),"diagnostic_dispatches_excluded":diagnostics,
        "unmeasured_or_unfilled_dispatches":unknown,
        "adverse_request_to_fill_bps":distribution([float(r["adverse_fill_difference_bps"]) for r in measured]),
        "dispatch_ms":distribution([v for r in measured if (v:=finite(r.get("dispatch_ms"))) is not None and v>=0]),
        "entry_observations":sum(r.get("source")=="entry" for r in measured),
        "exit_observations":sum(r.get("source") in {"intraday_close","legacy_close"} for r in measured),
        "strategy_performance_proven":False,"broker_eligible":False,"orders_sent":0,
        "limitations":["Request-to-fill differences are not a measurement of venue-only slippage.",
            "Exit attribution requires lifecycle evidence; entry and exit counts are not complete trades.",
            "No measured costs are substituted automatically into frozen experiments or trading policy."]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--storage-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    rows=[];invalid=0
    for path in sorted((args.storage_dir/"execution_quality").glob("dispatches_*.jsonl"))[-31:]:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError("invalid_row")
                rows.append(row)
            except (ValueError,TypeError):invalid+=1
    result=summarize(rows);result["invalid_journal_rows"]=invalid
    atomic_json(args.output,result)
    print(json.dumps(result))


if __name__=="__main__":main()
