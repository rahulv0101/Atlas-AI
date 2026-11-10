"""Observe demo execution and cutoff truth without sending any broker orders."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import utc_query_time
from atlas_ai.execution.trade_executor import TradeExecutor
from atlas_ai.learning.decision_index import GuardedDecisionIndex
from atlas_ai.learning.closed_position_ledger import _decisions
from atlas_ai.learning.evidence_provenance import is_manual_broker_test
from atlas_ai.learning.observation_checkpoint import observation_lock,load_checkpoint,save_checkpoint


def broker_snapshot(settings, api=mt5, now=None):
    now=now or datetime.now(timezone.utc)
    account=api.account_info()
    if (account is None or account.login!=settings.hfm_login or account.server!=settings.hfm_server
            or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO):
        raise ValueError("matching_demo_account_required")
    positions=api.positions_get();orders=api.orders_get()
    if positions is None or orders is None:
        raise ValueError("broker_inventory_unavailable")
    def owned(row):
        return (row.symbol==settings.symbol and row.magic==settings.magic_number
            and TradeExecutor._is_atlas_comment(getattr(row,"comment",""))
            and not is_manual_broker_test({"comment":getattr(row,"comment","")}))
    positions=[r for r in positions if owned(r)];orders=[r for r in orders if owned(r)]
    deals=api.history_deals_get(utc_query_time(now-timedelta(days=1),settings),utc_query_time(now,settings))
    owned_ids={str(getattr(r,"identifier",None) or r.ticket) for r in positions}
    if deals is not None:
        owned_ids.update(str(d.position_id) for d in deals if owned(d) and d.entry==mt5.DEAL_ENTRY_IN)
    rows=[]
    for d in deals or []:
        if d.symbol!=settings.symbol or str(d.position_id) not in owned_ids or d.type not in {mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL}:
            continue
        rows.append({"ticket":str(d.ticket),"position_id":str(d.position_id),"order_id":str(d.order),
            "entry":int(d.entry),"deal_type":int(d.type),
            "broker_time_msc":int(getattr(d,"time_msc",0) or d.time*1000),
            "volume":float(d.volume),"net":sum(float(getattr(d,k,0) or 0) for k in ("profit","commission","swap","fee"))})
    current=api.account_info()
    if current is None or current.login!=settings.hfm_login or current.server!=settings.hfm_server or current.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise ValueError("account_changed_during_snapshot")
    return {"broker_ok":True,"history_ok":deals is not None,"currency":account.currency,
        "positions":[{"position_id":str(getattr(r,"identifier",None) or r.ticket),"volume":float(r.volume),
            "side":"buy" if r.type==mt5.POSITION_TYPE_BUY else "sell", "sl":float(r.sl),"tp":float(r.tp),
            "current_price":float(r.price_current)} for r in positions],
        "pending_orders":[str(r.ticket) for r in orders],"deals":rows}


def lifecycle_summary(deals, decisions, open_ids):
    proven=[event for event in decisions if not is_manual_broker_test(event.get("meta",{}))
            and not event.get("meta",{}).get("forced_demo_entry")
            and not event.get("meta",{}).get("forced_learning_probe")]
    raw_refs,_=_decisions(proven)
    refs={key:{(m["decision_id"],m["strategy"]) for m in values} for key,values in raw_refs.items()}
    groups={}
    for d in deals.values():groups.setdefault(d["position_id"],[]).append(d)
    completed=[]
    for pos,rows in groups.items():
        entries=[r for r in rows if r["entry"]==mt5.DEAL_ENTRY_IN]
        exits=[r for r in rows if r["entry"] in {mt5.DEAL_ENTRY_OUT,mt5.DEAL_ENTRY_OUT_BY}]
        links=[refs.get(r["order_id"],set()) for r in entries]
        if (pos in open_ids or not entries or not exits
                or any(not math.isfinite(float(r["volume"])) or r["volume"]<=0 or not math.isfinite(float(r["net"])) for r in rows)
                or any(r["entry"]==mt5.DEAL_ENTRY_INOUT for r in rows)
                or abs(sum(r["volume"] for r in entries)-sum(r["volume"] for r in exits))>1e-8
                or not all(len(link)==1 for link in links)):
            continue
        if (any(r.get("deal_type") not in {mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL} or not r.get("broker_time_msc") for r in rows)
                or len({r["deal_type"] for r in entries})!=1
                or any(r["deal_type"]==entries[0]["deal_type"] for r in exits)):
            continue
        balance=0.;sequence_ok=True
        for r in sorted(rows,key=lambda row:(row["broker_time_msc"],int(row.get("ticket",0)))):
            balance+=r["volume"] if r["entry"]==mt5.DEAL_ENTRY_IN else -r["volume"]
            if balance < -1e-8:sequence_ok=False
        if not sequence_ok:continue
        unique=set().union(*links)
        if len(unique)!=1:continue
        decision,strategy=next(iter(unique))
        completed.append({"position_id":pos,"decision_id":decision,"strategy":strategy,"net":sum(r["net"] for r in rows)})
    return completed


def protected_positions(positions):
    protected=set()
    for position in positions:
        try:
            sl,tp,price=(float(position[k]) for k in ("sl","tp","current_price"))
            if (not all(math.isfinite(v) and v>0 for v in (sl,tp,price))
                    or not (sl<price<tp if position["side"]=="buy" else tp<price<sl)):
                continue
            protected.add(position["position_id"])
        except (KeyError,ValueError,TypeError):
            continue
    return protected


def acceptance_summary(cycles, management_ids):
    verified=[{**cycle,"management_evidence":"broker_open_position_with_protective_sl_tp"}
              for cycle in cycles if cycle["position_id"] in management_ids]
    return {"state":"verified" if verified else "management_evidence_missing" if cycles else "awaiting_autonomous_broker_cycle",
            "verified_end_to_end_cycles":verified,
            "requires":["fresh guarded autonomous decision", "matching broker entry fill", "observed broker protection", "balanced exit fills", "broker-flat position"],
            "manual_and_forced_tests_count_as_acceptance":False}


def publish_json(path, data, diagnostics):
    try:
        atomic_json(path, data)
        return True
    except OSError as exc:
        diagnostics["persistence_error_count"] = diagnostics.get("persistence_error_count", 0) + 1
        diagnostics["last_persistence_error"] = type(exc).__name__
        return False

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes",type=float,default=1440)
    parser.add_argument("--interval-seconds",type=int,default=60)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--resume",action="store_true",help="Resume the same journal using its matching account-scoped checkpoint")
    args=parser.parse_args()
    if not 0<args.minutes<=10080 or not 10<=args.interval_seconds<=300:parser.error("Invalid observation interval")
    settings=load_settings();args.output.parent.mkdir(parents=True,exist_ok=True)
    summary_path=args.output.with_suffix(".summary.json");started=datetime.now(timezone.utc).isoformat()
    summary={"pid":os.getpid(),"started_at":started,"samples":0,"broker_unavailable_samples":0,
        "stale_status_samples":0,"verified_natural_cycles":[],"orders_sent":0,"status":"running"}
    deadline=time.monotonic()+args.minutes*60;baseline=None;seen={};known_decisions={};management_ids=set()
    checkpoint_path=args.output.with_suffix(".checkpoint.json")
    with observation_lock(Path(settings.storage_dir)/"lifecycle_observer.lock"):
        if args.resume:
            if not args.output.is_file():raise ValueError("resume_journal_missing")
            baseline,seen,management_ids,summary=load_checkpoint(checkpoint_path,settings,journal=args.output)
            summary.update(pid=os.getpid(),resumed_at=started,status="running")
        elif checkpoint_path.exists():
            raise FileExistsError("checkpoint_already_exists_use_resume")
        summary["window_ends_at"]=(datetime.now(timezone.utc)+timedelta(minutes=args.minutes)).isoformat()
        _observe(args,settings,summary,summary_path,checkpoint_path,deadline,baseline,seen,known_decisions,management_ids)


def _observe(args,settings,summary,summary_path,checkpoint_path,deadline,baseline,seen,known_decisions,management_ids):
    with args.output.open("a" if args.resume else "x",encoding="utf-8",buffering=1) as stream:
        while time.monotonic()<deadline:
            now=datetime.now(timezone.utc);row={"observed_at":now.isoformat()}
            try:
                raw=json.loads((Path(settings.storage_dir)/"status.json").read_text(encoding="utf-8-sig"))
                exit_file=Path(settings.storage_dir)/"automation_state.intraday_exit.json"
                if exit_file.exists():
                    exit_state=json.loads(exit_file.read_text(encoding="utf-8"))
                    raw["intraday_exit"]={k:v for k,v in exit_state.items() if k!="attempts"}
                stamp=datetime.fromisoformat(str(raw.get("updated_at","")).replace("Z","+00:00"))
                age=(now-stamp).total_seconds()
                row.update(decision_at=raw.get("updated_at"),action=raw.get("action"),message=raw.get("message"),
                    chosen=raw.get("chosen"),intraday_exit=raw.get("intraday_exit"),status_age_seconds=age)
                if not 0<=age<=180:summary["stale_status_samples"]+=1
            except Exception as exc:
                row["status_error"]=type(exc).__name__;summary["stale_status_samples"]+=1
            try:
                terminal=mt5.terminal_info()
                if terminal is None:
                    attached=mt5.initialize(path=settings.hfm_terminal_path) if settings.hfm_terminal_path else mt5.initialize()
                    if not attached:raise RuntimeError("terminal_unavailable")
                broker=broker_snapshot(settings,now=now)
                deals=broker.pop("deals")
                if baseline is None and broker["history_ok"]:baseline={d["ticket"] for d in deals}
                fresh=[] if baseline is None else [d for d in deals if d["ticket"] not in baseline and d["ticket"] not in seen]
                seen.update({d["ticket"]:d for d in fresh})
                for event in GuardedDecisionIndex(settings).events():
                    known_decisions[json.dumps(event["meta"],sort_keys=True)]=event
                row.update(broker,new_deals=fresh)
                summary["verified_natural_cycles"]=lifecycle_summary(seen,list(known_decisions.values()),{r["position_id"] for r in broker["positions"]})
                management_ids.update(protected_positions(broker["positions"]))
                row["observed_protected_positions"]=sorted(protected_positions(broker["positions"]))
                summary["lifecycle_acceptance"]=(acceptance_summary(summary["verified_natural_cycles"],management_ids)
                    if broker["history_ok"] else {"state":"broker_history_unavailable","verified_end_to_end_cycles":[]})
                publish_json(Path(settings.storage_dir)/"lifecycle_acceptance.json",{
                    **summary["lifecycle_acceptance"],"checked_at":now.isoformat(),"observer_pid":os.getpid(),
                    "observer_state":"running","window_ends_at":summary["window_ends_at"],
                    "broker_ok":True,"history_ok":broker["history_ok"],"orders_sent":0},summary)
            except Exception as exc:
                row.update(broker_ok=False,broker_error=type(exc).__name__);summary["broker_unavailable_samples"]+=1
                publish_json(Path(settings.storage_dir)/"lifecycle_acceptance.json",{
                    "state":"broker_evidence_unavailable","checked_at":now.isoformat(),"broker_ok":False,"orders_sent":0,
                    "observer_pid":os.getpid(),"observer_state":"running","window_ends_at":summary["window_ends_at"]},summary)
            stream.write(json.dumps(row)+"\n")
            summary.update(baseline_history_ready=baseline is not None,samples=summary["samples"]+1,last_observed_at=now.isoformat(),last_broker_ok=row.get("broker_ok"),
                last_positions=len(row.get("positions",[])) if row.get("broker_ok") else None,
                last_pending_orders=len(row.get("pending_orders",[])) if row.get("broker_ok") else None)
            publish_json(summary_path,summary,summary)
            try:
                save_checkpoint(checkpoint_path,settings,baseline,seen,management_ids,summary,journal=args.output)
            except OSError as exc:
                summary["persistence_error_count"]=summary.get("persistence_error_count",0)+1
                summary["last_checkpoint_error"]=type(exc).__name__
            if args.once:break
            time.sleep(min(args.interval_seconds,max(0,deadline-time.monotonic())))
    summary["status"]="completed";publish_json(summary_path,summary,summary)
    final=dict(summary.get("lifecycle_acceptance") or {"state":"broker_evidence_unavailable","verified_end_to_end_cycles":[]})
    if not summary.get("last_broker_ok"):
        final={"state":"broker_evidence_unavailable","verified_end_to_end_cycles":[]}
    publish_json(Path(settings.storage_dir)/"lifecycle_acceptance.json",{
        **final,"checked_at":summary.get("last_observed_at"),"broker_ok":bool(summary.get("last_broker_ok")),
        "observer_pid":os.getpid(),"observer_state":"completed","window_ends_at":summary["window_ends_at"],
        "completed_at":datetime.now(timezone.utc).isoformat(),"orders_sent":0},summary)
    mt5.shutdown()


if __name__=="__main__":main()
