"""Bounded paper-only cost research sidecar, separate from the trading runtime."""
from contextlib import contextmanager
from datetime import datetime,timezone
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.atomic_files import atomic_json
from tools.cost_aware_strategy_audit import forward_once


@contextmanager
def observer_lock(path):
    with path.open("a+b") as handle:
        if not path.stat().st_size:handle.write(b"0");handle.flush()
        handle.seek(0)
        if os.name=="nt":
            import msvcrt
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError("cost_research_observer_already_running")
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            handle.seek(0)
            if os.name=="nt":msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def public_summary(directory, result):
    selection=json.loads((directory/"selection.json").read_text())
    latest_bar=None
    try:
        keys=json.loads((directory/"forward_signals.json").read_text()).keys()
        latest_bar=max(keys) if keys else None
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(latest_bar)).total_seconds() if latest_bar else None
        fresh=age is not None and 0<=age<=180
    except (OSError,ValueError,TypeError):fresh=False
    state=result.get("state")
    if state=="observing_frozen_rules" and not fresh:state="waiting_for_fresh_broker_bars"
    return {"state":state,"checked_at":result.get("checked_at"),"run_id":directory.name,
        "latest_bar_at":latest_bar,"data_fresh":fresh,
        "forward_start":selection["frozen_at"],"observer_pid":os.getpid(),
        "comparisons":len(result.get("lanes",{})),
        "paper_outcomes":sum(len(v.get("paper_outcomes",[])) for v in result.get("lanes",{}).values()),
        "training_qualified":selection["qualified_training_lanes"],"orders_sent":0,"broker_eligible":False,
        "error":result.get("error")}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir",type=Path,required=True)
    p.add_argument("--hours",type=float,default=24)
    p.add_argument("--once",action="store_true")
    args=p.parse_args()
    if not 0<args.hours<=24:p.error("Observation is bounded to at most 24 hours per invocation")
    directory=args.run_dir.resolve();status_path=directory.parent/"latest.json"
    with observer_lock(directory/"observer.lock"):
        deadline=time.monotonic()+args.hours*3600
        while time.monotonic()<deadline:
            fatal=False
            try:result=forward_once(directory)
            except Exception as exc:
                result={"state":"observation_error","checked_at":datetime.now(timezone.utc).isoformat(),
                    "error":type(exc).__name__,"reason":str(exc),"orders_sent":0,"broker_eligible":False}
                atomic_json(directory/"forward.json",result);fatal=isinstance(exc,ValueError)
            atomic_json(status_path,public_summary(directory,result))
            if fatal:raise RuntimeError("frozen_cost_research_failed_closed")
            if args.once:return
            time.sleep(min(60,max(0,deadline-time.monotonic())))
        result={**result,"state":"observation_window_completed","checked_at":datetime.now(timezone.utc).isoformat()}
        atomic_json(directory/"forward.json",result);atomic_json(status_path,public_summary(directory,result))


if __name__=="__main__":main()
