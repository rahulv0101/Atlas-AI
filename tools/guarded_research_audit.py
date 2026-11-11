"""Freeze and compare broker-unit historical research; never activate or trade."""
import argparse
import ast
from dataclasses import asdict,fields,replace
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import cache_candidates,replay
from tools.broker_fee_profile import build_profile
from tools.cost_aware_strategy_audit import attach,prepare_frame
from atlas_ai.data.broker_clock import utc_query_time
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.strategies.research_protocol import environment_versions


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def broker_snapshot(settings):
    attach(settings)
    info=mt5.symbol_info(settings.symbol);account=mt5.account_info();tick=mt5.symbol_info_tick(settings.symbol)
    now=datetime.now(timezone.utc)
    from datetime import timedelta
    deals=mt5.history_deals_get(utc_query_time(now-timedelta(days=30),settings),utc_query_time(now,settings))
    fees=build_profile(deals,info,account.currency,now)
    if fees["roundtrip_fee_per_lot_observed"] is None:raise ValueError("observed_fee_evidence_required")
    margins=[mt5.order_calc_margin(side,settings.symbol,1.,price) for side,price in
        ((mt5.ORDER_TYPE_BUY,tick.ask),(mt5.ORDER_TYPE_SELL,tick.bid))]
    if any(v is None or v<=0 for v in margins):raise ValueError("broker_margin_evidence_required")
    spec=BrokerSpec(point=info.point,tick_size=info.trade_tick_size,
        tick_value_profit=info.trade_tick_value_profit,tick_value_loss=info.trade_tick_value_loss,
        volume_min=info.volume_min,volume_max=info.volume_max,volume_step=info.volume_step,digits=info.digits,
        trade_stops_level=info.trade_stops_level,trade_freeze_level=info.trade_freeze_level,
        margin_per_lot=max(margins),roundtrip_fee_per_lot=fees["roundtrip_fee_per_lot_observed"])
    checks=[]
    for side,sign,price in ((mt5.ORDER_TYPE_BUY,1,tick.ask),(mt5.ORDER_TYPE_SELL,-1,tick.bid)):
        for move in (-1.,1.):
            actual=mt5.order_calc_profit(side,settings.symbol,.01,price,price+sign*move)
            modeled=spec.cash(move,.01)
            checks.append({"side":"buy" if sign==1 else "sell","price_move":move,"volume":.01,
                "broker_cash":actual,"modeled_cash":modeled,"matches":actual is not None and abs(actual-modeled)<=.02})
    if not all(c["matches"] for c in checks):raise ValueError("current_broker_unit_conversion_mismatch")
    raw=json.loads((Path(settings.storage_dir)/"automation_state.json").read_text())["payload"]
    session=raw["session_control"];pilot=raw["tiny_live_pilot"]
    limits={"day_trades":min(session["daily_trade_limit"],pilot["max_trades_per_day"]),
        "loss_streak":min(session["consecutive_loss_limit"],pilot["max_consecutive_losses"]),
        "daily_loss_percent":min(1.5,pilot["daily_loss_cap"]),"lot_cap":pilot["size_cap"],
        "setup_family":pilot["allowed_setup_family"]}
    return spec,{"currency":account.currency,"broker_units_checks":checks,"fee_evidence":fees,
        "historical_currency_and_margin_conversion":"frozen_current_specification_approximation",
        "natural_execution_cost_calibration_ready":False},limits


def safe_settings(settings):
    excluded={"hfm_login","hfm_password","hfm_server","hfm_terminal_path","storage_dir","gemini_api_key","openai_api_key"}
    return {f.name:getattr(settings,f.name) for f in fields(settings) if f.name not in excluded}


def qualified(stats):
    days={t["entry_at"][:10] for t in stats["trade_list"]}
    return (stats["trades"]>=30 and len(days)>=2 and (stats["mean_net_r"] or 0)>0
        and ((stats["profit_factor"] or 0)>=1.1 or stats["wins"]==stats["trades"])
        and stats["max_drawdown_r"]<=6)


def select_training(comparisons):
    candidates=[key for key,value in comparisons.items() if qualified(value["training_reused"])]
    candidates.sort(key=lambda key:(-comparisons[key]["training_reused"]["mean_net_r"],key))
    return {"selected_for_forward":candidates[0] if candidates else None,"training_qualified":candidates,
        "selected_for_live":None,"broker_eligible":False,
        "reason":"Training-only selection for new prospective paper evidence; never broker activation."}


def reused_candidates(directory,source,settings):
    old=json.loads((directory/"manifest.json").read_text())
    if digest(directory/"manifest.json")!=(directory/"manifest.sha256").read_text().strip():
        raise ValueError("reuse_manifest_changed")
    if old["input_sha256"]!=digest(source) or old["settings"]!=json.loads(json.dumps(safe_settings(settings))):
        raise ValueError("reuse_data_or_settings_mismatch")
    exception="atlas_ai/testing/policy_replay.py"
    for name,expected in old["source_hashes"].items():
        frozen=directory/"frozen_source"/name
        if digest(frozen)!=expected:raise ValueError("reuse_frozen_source_changed")
        if name.startswith("atlas_ai/") and name!=exception and digest(ROOT/name)!=expected:
            raise ValueError("signal_dependency_changed_requires_new_cache:"+name)
    def functions(path):
        names={"higher_timeframe_bias","policy_trader","cache_candidates"}
        return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node,ast.FunctionDef) and node.name in names}
    if functions(ROOT/exception)!=functions(directory/"frozen_source"/exception):
        raise ValueError("signal_cache_logic_changed")
    if digest(ROOT/"tools/cost_aware_strategy_audit.py")!=old["source_hashes"]["tools/cost_aware_strategy_audit.py"]:
        raise ValueError("input_preparation_changed")
    cache=json.loads((directory/"candidates.json").read_text())
    indices=[row["index"] for row in cache]
    if indices!=sorted(set(indices)):raise ValueError("invalid_reused_candidate_order")
    from atlas_ai.strategies.inventory import base_inventory
    from atlas_ai.testing.policy_replay import policy_trader
    trader=policy_trader(settings,None)
    names=[s.name for s in base_inventory(settings.timeframe) if trader._strategy_enabled(s.name)]
    if any({s["strategy"] for s in row["signals"]}!=set(names) for row in cache):
        raise ValueError("reused_strategy_inventory_mismatch")
    lineage={"manifest_sha256":digest(directory/"manifest.json"),"candidate_sha256":digest(directory/"candidates.json"),
        "scope":"Signals only; retired raw-confidence decisions and outcomes are not reused.",
        "verification":"Input/settings identical; signal-generation AST and all Atlas dependencies unchanged."}
    return cache,{"reused_candidate_bars":len(cache)},names,lineage


def run(source,output,reuse=None):
    output.mkdir(parents=True,exist_ok=False)
    original=load_settings();spec,evidence,limits=broker_snapshot(original)
    if original.timeframe.upper()!="M1":raise ValueError("guarded_research_requires_configured_M1")
    variants=[ExitVariant("current",original.backtest_break_even_lock_r,slip) for slip in (0.,3.)]
    variants += [ExitVariant("cost_aware_lock",original.backtest_break_even_lock_r,slip,True) for slip in (0.,3.)]
    frozen=datetime.now(timezone.utc).isoformat()
    acceptance=json.loads((Path(original.storage_dir)/"acceptance_plan.json").read_text())
    manifest={"schema":"atlas_guarded_research_v2","frozen_at":frozen,"symbol":original.symbol,
        "settings":safe_settings(original),"spec":asdict(spec),"broker_evidence":evidence,"limits":limits,
        "variants":[asdict(v) for v in variants],"input_sha256":digest(source),
        "historical_data_status":"previously_inspected_not_blind","future_holdout_start":frozen,
        "environment":environment_versions(),"training_fraction":.7,
        "selection_rule":"Training only: >=30 cases, >=2 days, mean net R>0, PF>=1.1 or all wins, drawdown<=6R; highest mean net R; stable lexical tie break.",
        "replay_execute_trades":False,"forward_source_run":acceptance["paper_run"],"deadline":acceptance["deadline"],
        "confidence_basis":"Atlas structured conviction with active-profile effective threshold; no raw-confidence gate substitution.",
        "future_rule":"Only new post-freeze outcomes count as forward evidence. Existing frozen experiment is separate.",
        "broker_eligible":False,"auto_promotion":False,"orders_sent":0,
        "missing_parity":["Historical screenshots/visual approvals and macro state are unavailable.",
            "Meta-model, adaptive reward/lesson history, promoted evolved/chromosome versions and execution clusters are not reconstructed.",
            "One position at a time; no tick-level fills or historical FX/margin specifications.",
            "Exit rules model completed M1 bars, not all live position-management events.",
            "Observed fees include manual/diagnostic deals for costs only; natural slippage calibration remains pending."]}
    snapshot=output/"frozen_source";hashes={}
    for name in ("atlas_ai","tools"):
        for path in (ROOT/name).rglob("*.py"):
            relative=path.relative_to(ROOT);target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target);hashes[str(relative).replace('\\','/')]=digest(path)
    manifest["source_hashes"]=hashes
    prepared=None
    if reuse is not None:
        prepared=reused_candidates(reuse,source,original)
        manifest["reused_candidate_cache"]=prepared[3]
    atomic_json(output/"manifest.json",manifest);(output/"manifest.sha256").write_text(digest(output/"manifest.json"))
    shutil.copyfile(source,output/"candles.csv");frame=prepare_frame(pd.read_csv(output/"candles.csv"))
    def progress(**row):atomic_json(output/"progress.json",{**row,"checked_at":datetime.now(timezone.utc).isoformat()})
    def deny(*args,**kwargs):raise AssertionError("research_order_dispatch_forbidden")
    with tempfile.TemporaryDirectory(prefix="atlas_guarded_research_") as temporary,patch.object(mt5,"order_send",deny):
        settings=replace(original,execute_trades=False,storage_dir=temporary,gemini_api_key="",openai_api_key="",
            backtest_persist_learning_state=False)
        store=KnowledgeStore(temporary)
        candidates,counts,names=prepared[:3] if prepared is not None else cache_candidates(frame,settings,store,progress)
        atomic_json(output/"candidates.json",candidates)
        decision_cache={}
        times=pd.to_datetime(frame.time,utc=True)
        # Dates declared before result inspection. This history was already seen;
        # chronological separation here is diagnostic, never a blind-test claim.
        split=times.iloc[int(len(frame)*.7)].to_pydatetime()
        windows={"training_reused":(None,split),"validation_reused":(split,None)}
        result={"state":"running","strategies":names,"generation_counts":counts,"comparisons":{},
            "split_utc":split.isoformat(),"full_live_policy_parity":False,"broker_eligible":False,"orders_sent":0}
        for variant in variants:
            for name in [None,*names]:
                key=f"{name or 'combined'}/{variant.name}/slip_{variant.slippage_points_per_side}"
                result["comparisons"][key]={}
                start,end=windows["training_reused"]
                progress(stage="compare",comparison=key,window="training_reused")
                result["comparisons"][key]["training_reused"]=replay(frame,candidates,settings,spec,variant,
                    store,limits,strategy=name,start=start,end=end,decision_cache=decision_cache)
                atomic_json(output/"report.json",result)
        selection=select_training(result["comparisons"])
        atomic_json(output/"selection.json",selection)
        (output/"selection.sha256").write_text(digest(output/"selection.json"))
        for variant in variants:
            for name in [None,*names]:
                key=f"{name or 'combined'}/{variant.name}/slip_{variant.slippage_points_per_side}"
                start,end=windows["validation_reused"]
                progress(stage="compare",comparison=key,window="validation_reused")
                result["comparisons"][key]["validation_reused"]=replay(frame,candidates,settings,spec,variant,
                    store,limits,strategy=name,start=start,end=end,decision_cache=decision_cache)
                atomic_json(output/"report.json",result)
        result["strict_evidence_replay"]=replay(frame,candidates,settings,spec,variants[0],store,limits,strict=True,decision_cache=decision_cache)
        result["selection"]=selection
        result["state"]="completed_research_only"
        atomic_json(output/"report.json",result);progress(stage="completed_research_only")
        atomic_json(Path(original.storage_dir)/"guarded_research_active.json",{"run_dir":str(output.resolve())})
    mt5.shutdown()
    return result


def run_broker_history(output,days=30):
    if output.exists():raise FileExistsError("new_research_directory_required")
    if not 1<=days<=90:raise ValueError("bounded_history_days_required")
    from datetime import timedelta
    settings=replace(load_settings(),execute_trades=False,timeframe="M1")
    attach(settings)
    end=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    with tempfile.TemporaryDirectory(prefix="atlas_history_input_") as folder:
        frame=MarketDataFeed(settings).get_rates_range(end-timedelta(days=days),end)
        frame=frame[pd.to_datetime(frame.time,utc=True)+pd.Timedelta(minutes=1)<=pd.Timestamp(end)]
        source=Path(folder)/"candles.csv";frame.to_csv(source,index=False)
        return run(source,output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reuse-candidates",type=Path)
    args=parser.parse_args()
    existed=args.output.exists()
    try:result=run(args.source,args.output,args.reuse_candidates)
    except Exception as exc:
        if not existed and args.output.is_dir():
            atomic_json(args.output/"progress.json",{"state":"failed","error":type(exc).__name__,"reason":str(exc),"orders_sent":0})
        raise
    print(json.dumps({"state":result["state"],"comparisons":len(result["comparisons"]),"orders_sent":0}))


if __name__=="__main__":main()
