from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pandas as pd
import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.research_worker import StrategyResearchWorker, evaluate
from atlas_ai.strategies.strategy_inventor import StrategyInventor


def frame(n=800):
    return pd.DataFrame({"time":pd.date_range("2026-11-09T08:00",periods=n,freq="min"),
        "open":[2000.]*n,"high":[2000.8]*n,"low":[1999.2]*n,"close":[2000.]*n,"spread":[20.]*n,"tick_volume":[100.]*n})


def settings(tmp_path):
    return Settings(hfm_login=1,hfm_password="test",hfm_server="Demo",storage_dir=str(tmp_path),timeframe="M1",
        backtest_max_hold_bars=3,backtest_slippage_cost_bps=0,evolution_enabled=True)


def candidate():
    return StrategyInventor().invent(status={"context_snapshot":{"regime":"range"}})[0].chromosome


@pytest.fixture
def fixed_strategy(monkeypatch):
    monkeypatch.setattr("atlas_ai.strategies.research_worker.StrategyFactory.build",lambda c,**kwargs:NS(generate_signal=lambda df:TradeSignal("generated","buy",.9,100.,200.)))


def test_research_uses_points_costs_and_nonoverlapping_next_bar_entries(tmp_path,fixed_strategy):
    s=settings(tmp_path);df=frame(150)
    rows,_=evaluate(candidate(),df,s)
    assert rows and all(r["net_r"]==pytest.approx(-.2) for r in rows)
    assert all(pd.Timestamp(r["entry_at"])>pd.Timestamp(r["signal_at"]) for r in rows)
    assert all(pd.Timestamp(a["exit_at"])<pd.Timestamp(b["entry_at"]) for a,b in zip(rows,rows[1:]))


def test_conservative_intrabar_exit_and_missing_spread(tmp_path,fixed_strategy):
    df=frame(150);df["high"]=2003.;df["low"]=1998.
    rows,_=evaluate(candidate(),df,settings(tmp_path))
    assert rows and rows[0]["gross_r"]==-1 and rows[0]["net_r"]==pytest.approx(-1.2)
    df["spread"]=float("nan")
    with pytest.raises(ValueError,match="spread"):evaluate(candidate(),df,settings(tmp_path))


def test_chart_proposals_are_isolated_frozen_and_restart_safe(tmp_path,fixed_strategy,monkeypatch):
    import MetaTrader5 as mt5
    sender=Mock(side_effect=AssertionError("Research cannot submit orders"));monkeypatch.setattr(mt5,"order_send",sender)
    live=tmp_path/"evolution_population.json";live.write_text('{"existing":"unchanged"}')
    s=settings(tmp_path);store=KnowledgeStore(str(tmp_path));worker=StrategyResearchWorker(s,store,threading.Event())
    now=datetime(2026,11,9,23,tzinfo=timezone.utc)
    state=worker.run_once(frame(),now)
    assert state["batches"] and state["batches"][0]["candidates"]
    batch=state["batches"][0]
    assert pd.Timestamp(batch["training_end"])<pd.Timestamp(batch["holdout_start"])
    assert all(c["promotion"]=="research_only_not_broker_eligible" for c in batch["candidates"])
    restored=StrategyResearchWorker(s,store,threading.Event()).run_once(frame(),now)
    assert restored["batches"]==state["batches"]
    assert live.read_text()=='{"existing":"unchanged"}' and state["orders_sent"]==0
    sender.assert_not_called()


def test_forward_results_are_new_bars_only_and_not_counted_twice(tmp_path,fixed_strategy):
    worker=StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event())
    now=datetime(2026,11,9,23,tzinfo=timezone.utc)
    worker.run_once(frame(650),now)
    updated=worker.run_once(frame(680),now)
    before=json.dumps(updated["batches"],sort_keys=True)
    repeated=worker.run_once(frame(680),now)
    assert before==json.dumps(repeated["batches"],sort_keys=True)
    for c in updated["batches"][0]["candidates"]:
        assert len(c["forward"])>0
        assert all(pd.Timestamp(r["signal_at"]).tz_localize(None)>pd.Timestamp(updated["batches"][0]["asof"]) for r in c["forward"])


def test_invalid_or_corrupt_evidence_cannot_reset_research(tmp_path,fixed_strategy):
    worker=StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event())
    now=datetime(2026,11,9,23,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match="insufficient"):worker.run_once(frame(200),now)
    worker.path.write_text("corrupt")
    with pytest.raises(ValueError):worker.run_once(frame(),now)
    assert worker.path.read_text()=="corrupt"


def test_open_future_bars_excluded_and_dry_run_does_not_persist(tmp_path,fixed_strategy):
    worker=StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event(),dry_run=True)
    now=datetime(2026,11,9,18,tzinfo=timezone.utc)
    state=worker.run_once(frame(),now)
    assert pd.Timestamp(state["batches"][0]["asof"])<pd.Timestamp("2026-11-09T18:00")
    assert not worker.path.exists()


def test_changing_holdout_cannot_change_generated_rules(tmp_path,fixed_strategy):
    now=datetime(2026,11,9,23,tzinfo=timezone.utc)
    first=StrategyResearchWorker(settings(tmp_path/"a"),KnowledgeStore(str(tmp_path/"a")),threading.Event()).run_once(frame(),now)
    changed=frame();changed.loc[560:,["open","high","low","close"]]+=50
    other=StrategyResearchWorker(settings(tmp_path/"b"),KnowledgeStore(str(tmp_path/"b")),threading.Event()).run_once(changed,now)
    a=first["batches"][0];b=other["batches"][0]
    assert [c["chromosome"]["genes"] for c in a["candidates"]]==[c["chromosome"]["genes"] for c in b["candidates"]]
    assert [c["training"] for c in a["candidates"]]==[c["training"] for c in b["candidates"]]
    import gzip,hashlib
    assert hashlib.sha256(gzip.decompress(Path(a["dataset_file"]).read_bytes())).hexdigest()==a["dataset_sha256"]


def test_enabled_research_scheduler_cannot_invoke_legacy_promotion_path(tmp_path,monkeypatch):
    from atlas_ai.strategies import evolution_scheduler as module
    created=[]
    monkeypatch.setattr(StrategyResearchWorker,"start",lambda self:created.append(self))
    monkeypatch.setattr(module,"EvolutionScheduler",Mock(side_effect=AssertionError("legacy promotion path forbidden")))
    s=settings(tmp_path)
    worker=module.start_evolution_scheduler(s,KnowledgeStore(str(tmp_path)),threading.Event())
    try:
        assert isinstance(worker,StrategyResearchWorker) and created==[worker]
        assert worker.settings.execute_trades is False
    finally:module.stop_evolution_scheduler(worker)


def test_generated_atr_distances_are_broker_points_and_preserve_price_distance():
    from atlas_ai.strategies.strategy_factory import StrategyFactory
    c=candidate();c.set_gene("risk_min_confidence",.1);df=frame(150);df["open"]=1999.5
    a=StrategyFactory.build(c,point_size=.01).generate_signal(df)
    b=StrategyFactory.build(c,point_size=.1).generate_signal(df)
    assert a.stop_loss_points*.01==pytest.approx(b.stop_loss_points*.1)
    assert a.stop_loss_points>50 and a.take_profit_points>a.stop_loss_points
    assert a.stop_loss_points*.01==pytest.approx(1.6*c.gene_value("exit_sl_atr_multiple"))
    with pytest.raises(ValueError):StrategyFactory.build(c,point_size=0)
