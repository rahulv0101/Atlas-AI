"""Explicit single-entry demo diagnostic. Does not count as a natural strategy trade."""
from datetime import datetime, timedelta, timezone
import argparse
import json
import math
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import utc_query_time
from atlas_ai.data.freshness import execution_freshness
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.execution.execution_gate import ExecutionGate
from atlas_ai.execution.mt5_broker_adapter import MT5BrokerAdapter
from atlas_ai.execution.trade_executor import TradeExecutor
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.risk.risk_manager import RiskManager,RiskSnapshot


def controls_allow(gate,store):
    if not gate.refresh_critical_controls_from_persisted_state().get("ok"):return False
    return bool(store.load_runtime_flags().get("execute_trades") and gate._gate_enabled
        and not gate._sleep_mode_active and not gate._kill_switch.status().active
        and gate._execution_environment=="demo")


def history(settings,start):
    deals=mt5.history_deals_get(utc_query_time(start,settings),utc_query_time(datetime.now(timezone.utc),settings))
    if deals is None:raise RuntimeError("broker_history_unavailable")
    return list(deals)


def linked_position_ids(deals,broker_ref,settings):
    return {int(d.position_id) for d in deals if (str(d.order)==str(broker_ref) or str(d.ticket)==str(broker_ref))
        and d.entry==mt5.DEAL_ENTRY_IN and d.symbol==settings.symbol and d.magic==settings.magic_number}


def own_positions(settings,ids):
    rows=mt5.positions_get(symbol=settings.symbol)
    if rows is None:raise RuntimeError("position_inventory_unavailable")
    return [p for p in rows if int(getattr(p,"identifier",None) or p.ticket) in ids
        and p.magic==settings.magic_number and TradeExecutor._is_atlas_comment(p.comment)]


def protective(pos):
    return all(math.isfinite(float(v)) and float(v)>0 for v in (pos.sl,pos.tp,pos.price_current)) and (
        pos.sl<pos.price_current<pos.tp if pos.type==mt5.POSITION_TYPE_BUY else pos.tp<pos.price_current<pos.sl)


def balanced(deals,ids):
    if not ids:return False
    for pid in ids:
        rows=[d for d in deals if d.position_id==pid and d.type in {mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL}]
        entries=[d for d in rows if d.entry==mt5.DEAL_ENTRY_IN];exits=[d for d in rows if d.entry in {mt5.DEAL_ENTRY_OUT,mt5.DEAL_ENTRY_OUT_BY}]
        if (not entries or not exits or any(d.entry==mt5.DEAL_ENTRY_INOUT for d in rows)
            or len({d.type for d in entries})!=1 or any(d.type==entries[0].type for d in exits)
            or abs(sum(d.volume for d in entries)-sum(d.volume for d in exits))>1e-8):return False
    return True


def run(output,*,execute=False):
    settings=load_settings();store=KnowledgeStore(settings.storage_dir);executor=TradeExecutor(settings)
    started=datetime.now(timezone.utc);clock=time.monotonic();gate=None;broker_ref="";ids=set();close_attempted=set()
    result={"type":"automated_demo_diagnostic","natural_strategy_proof":False,"started_at":started.isoformat(),
        "run_id":uuid4().hex,"entry_dispatches":0,"close_dispatches":0,"volume":.01,"side":"buy",
        "stop_loss_points":150,"take_profit_points":240,"maximum_open_seconds_target":30,"steps":[],"status":"preflight"}
    if output.exists():raise FileExistsError("refusing_to_repeat_existing_diagnostic")
    atomic_json(output,result)
    original_send=mt5.order_send
    def one_send(request):
        nonlocal broker_ref
        field="close_dispatches" if request.get("position") else "entry_dispatches"
        if field=="entry_dispatches" and result[field]>=1:raise RuntimeError("single_entry_dispatch_limit")
        if field=="close_dispatches" and result[field]>=1:raise RuntimeError("single_close_dispatch_limit")
        result[field]+=1;atomic_json(output,result)
        response=original_send(request)
        if field=="entry_dispatches" and response is not None:
            broker_ref=str(getattr(response,"order",0) or getattr(response,"deal",0) or "")
            result["dispatch_receipt"]={"order":getattr(response,"order",0),"deal":getattr(response,"deal",0),"retcode":getattr(response,"retcode",None)}
            result["broker_order_id"]=broker_ref
            atomic_json(output,result)
        return response
    def validate_account():
        reason=executor._account_rejection(mt5.account_info())
        if reason:raise RuntimeError(reason)
    def refresh_ids():
        if broker_ref:ids.update(linked_position_ids(history(settings,started-timedelta(seconds=10)),broker_ref,settings))
    def close_known():
        validate_account();refresh_ids()
        for pos in own_positions(settings,ids):
            if pos.ticket in close_attempted:continue
            if not controls_allow(gate,store):raise RuntimeError("close_blocked_by_operator_controls")
            close_attempted.add(pos.ticket)
            response=adapter.close_position(position_id=str(pos.ticket))
            result["steps"].append({"stage":"position_specific_close","ok":response.ok,"status":response.status,"message":response.message})
    try:
        if not mt5.initialize(path=settings.hfm_terminal_path):raise RuntimeError("terminal_attach_failed")
        validate_account();account=mt5.account_info();terminal=mt5.terminal_info()
        positions=mt5.positions_get();orders=mt5.orders_get()
        if positions is None or orders is None or positions or orders:raise RuntimeError("verified_idle_account_required")
        if terminal is None or not terminal.connected or not terminal.trade_allowed or terminal.tradeapi_disabled:raise RuntimeError("terminal_permissions_required")
        if not settings.execute_trades:raise RuntimeError("execution_setting_disabled")
        info=mt5.symbol_info(settings.symbol);tick=mt5.symbol_info_tick(settings.symbol)
        if info is None or tick is None:raise RuntimeError("quote_unavailable")
        status=store.load_status();stamp=datetime.fromisoformat(status["updated_at"].replace("Z","+00:00"))
        age=(datetime.now(timezone.utc)-stamp).total_seconds()*1000
        if not 0<=age<=120000:raise RuntimeError("fresh_backend_status_required")
        risk=status.get("risk",{});guard=store.load_runtime_flags().get("risk_guard_state",{})
        if guard.get("safety_lock_active"):raise RuntimeError("account_safety_lock_active")
        if guard.get("cooldown_until"):
            until=datetime.fromisoformat(guard["cooldown_until"].replace("Z","+00:00"))
            if until.tzinfo is None or until>datetime.now(timezone.utc):raise RuntimeError("risk_cooldown_active")
        day_start=float(guard.get("start_balance",0));week_start=float(guard.get("week_start_balance",0))
        if day_start<=0 or week_start<=0:raise RuntimeError("risk_balance_anchors_required")
        daily=max(float(risk["daily_loss_pct"]),max(0,(day_start-account.equity)/day_start))
        weekly=max(float(risk["weekly_loss_pct"]),max(0,(week_start-account.equity)/week_start))
        allowed,reason=RiskManager(settings).evaluate(RiskSnapshot(account.equity,account.balance,
            daily,0,abs(tick.ask-tick.bid)/info.point,weekly,int(guard.get("consecutive_losses",0))))
        if not allowed:raise RuntimeError(reason)
        signal=TradeSignal("manual_broker_test","buy",.99,150.,240.)
        request=executor._build_request(signal,tick.ask,.01,info,decision_id="manual_broker_test")
        okay,note=executor._preflight_order_request(request,info)
        if not okay or request["volume"]!=.01:raise RuntimeError(note or "volume_mismatch")
        stop_pnl=mt5.order_calc_profit(request["type"],settings.symbol,.01,request["price"],request["sl"])
        result.update(currency=account.currency,estimated_stop_loss=abs(stop_pnl) if stop_pnl is not None else None,risk_budget=account.equity*settings.max_risk_per_trade)
        if stop_pnl is None or not math.isfinite(stop_pnl) or abs(stop_pnl)>result["risk_budget"]:raise RuntimeError("risk_budget_failed")
        feed=MarketDataFeed(settings);feed.get_rates(120)
        flags=store.load_runtime_flags();flags["freshness_runtime"]=execution_freshness(status_age_ms=age,max_age_ms=120000,market_fetch=feed.last_fetch_meta)
        flags["max_freshness_age_ms"]=120000
        if flags["freshness_runtime"]["is_stale"]:raise RuntimeError("fresh_broker_clock_required")
        result["steps"].append({"stage":"account_risk_quote_preflight","ok":True})
        if not execute:
            result["status"]="preview_passed_no_orders";return result
        gate=ExecutionGate(state_store_path=str(Path(settings.storage_dir)/"automation_state.json"))
        adapter=MT5BrokerAdapter(executor);gate.set_broker_adapter(adapter)
        if not controls_allow(gate,store):raise RuntimeError("operator_controls_block_diagnostic")
        session=gate._session_control._detect_session(datetime.now(timezone.utc))
        if not session.allowed or session.minutes_to_close<12:raise RuntimeError("active_session_with_exit_margin_required")
        mt5.order_send=one_send
        req=gate.create_request(environment="demo",action_type="place_trade",payload_summary=(
            f"instrument={settings.symbol} setup=continuation setup_family=continuation strategy=manual_broker_test side=buy size=0.01 confidence=0.990 "
            "stop_loss_points=150 take_profit_points=240 data_source=broker_runtime environment_mode=demo decision_id=manual_broker_test"),
            requested_by="operator_authorized_automated_diagnostic",dry_run=False,auto_generated=False,
            request_origin="operator_manual_test",strict_runtime_checks=True)
        rid=req.get("id")
        if not rid:raise RuntimeError("gate_request_not_created")
        result["request_id"]=rid;result["status"]="entry_intent_persisted";atomic_json(output,result)
        gate.approve_request(rid,approved_by="operator_authorized_automated_diagnostic",note="one labelled demo lifecycle diagnostic; not autonomous strategy evidence",explicit_live_confirmation=True)
        out=gate.execute(rid,runtime_flags=flags,risk_policy={"daily_loss_cap_pct":settings.max_daily_drawdown*100})
        broker_ref=str(out.get("result",{}).get("broker_order_id") or out.get("request",{}).get("broker_order_id") or broker_ref)
        result.update(broker_order_id=broker_ref,entry_gate_ok=bool(out.get("ok")),entry_gate_reason=out.get("reason"),status="reconciling_entry")
        result["entry_gate_result_status"]=out.get("result",{}).get("status")
        atomic_json(output,result)
        if not out.get("ok") and not result["entry_dispatches"]:raise RuntimeError("gate_blocked:"+str(out.get("reason")))
        protected=False
        for _ in range(8):
            validate_account();refresh_ids()
            rows=own_positions(settings,ids)
            if rows:
                protected=all(protective(p) for p in rows)
                result["protection_observed"]=protected
                result["position_ids"]=sorted(ids)
                result["broker_protection"]=[{"ticket":p.ticket,"sl":p.sl,"tp":p.tp,"price_current":p.price_current,"volume":p.volume} for p in rows]
                break
            time.sleep(.5)
        close_known()
        for _ in range(10):
            validate_account();deals=history(settings,started-timedelta(seconds=10));rows=own_positions(settings,ids)
            if not rows and balanced(deals,ids):
                result.update(broker_flat=True,balanced_entry_exit=True,net_profit=sum(d.profit+d.commission+d.swap+getattr(d,"fee",0) for d in deals if d.position_id in ids),
                    fills=[{"ticket":d.ticket,"order":d.order,"position_id":d.position_id,"entry":d.entry,"type":d.type,"volume":d.volume,"profit":d.profit} for d in deals if d.position_id in ids])
                break
            time.sleep(.5)
        result["status"]="diagnostic_verified" if protected and result.get("broker_flat") and result.get("balanced_entry_exit") else "diagnostic_incomplete_requires_review"
    except Exception as exc:
        result.update(status="diagnostic_incomplete_requires_review" if result["entry_dispatches"] else "blocked_no_order",error=type(exc).__name__+":"+str(exc))
    finally:
        if execute and broker_ref and gate is not None:
            try:close_known()
            except Exception as exc:result["cleanup_error"]=type(exc).__name__+":"+str(exc)
        result.update(finished_at=datetime.now(timezone.utc).isoformat(),duration_seconds=round(time.monotonic()-clock,3))
        mt5.order_send=original_send
        if gate is not None:gate._reconciliation_stop.set()
        atomic_json(output,result);mt5.shutdown()
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true",help="Explicitly send one diagnostic order on the configured demo account")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=run(args.output,execute=args.execute)
    print(json.dumps(result,indent=2))
