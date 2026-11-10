from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.strategies import research_worker as module
from atlas_ai.strategies.research_protocol import freeze, validate, source_hashes, frozen_settings, gene_hash
from atlas_ai.strategies.strategy_inventor import StrategyInventor
from tests.test_strategy_research_worker import frame


def settings(path):
    return Settings(hfm_login=1,hfm_password="test",hfm_server="Demo",storage_dir=str(path),timeframe="M1",
        backtest_max_hold_bars=3,backtest_slippage_cost_bps=0,evolution_enabled=True)


def batch(s):
    c=StrategyInventor().invent()[0].chromosome.to_dict()
    return {"protocol":freeze(s),"candidates":[{"chromosome":c,"frozen_gene_sha256":gene_hash(c)}]}


def test_forward_reuses_saved_cost_and_exit_parameters_instead_of_current_settings(tmp_path):
    original=settings(tmp_path);saved=batch(original)
    changed=replace(original,backtest_slippage_cost_bps=99,backtest_max_hold_bars=60)
    assert validate(saved,changed,source_hashes())=="verified_frozen_protocol"
    restored=frozen_settings(changed,saved)
    assert restored.backtest_slippage_cost_bps==0 and restored.backtest_max_hold_bars==3
    assert restored.execute_trades is False
    assert "hfm_password" not in saved["protocol"]["simulator"]


def test_legacy_source_changed_and_market_changed_batches_cannot_mix_forward_results(tmp_path):
    s=settings(tmp_path);saved=batch(s)
    assert validate({},s,source_hashes())=="legacy_protocol_unverified"
    assert validate(saved,s,{})=="source_changed"
    assert validate(saved,replace(s,timeframe="M5"),source_hashes())=="market_scope_changed"
    saved["candidates"][0]["chromosome"]["genes"][0]["value"]+=1
    assert validate(saved,s,source_hashes())=="candidate_rules_changed"


def test_incomplete_simulator_cannot_silently_use_runtime_defaults(tmp_path):
    s=settings(tmp_path);saved=batch(s)
    del saved["protocol"]["simulator"]["backtest_point_size"]
    assert validate(saved,s,source_hashes())=="simulator_protocol_incomplete"


def test_dependency_upgrade_cannot_silently_continue_an_old_experiment(tmp_path):
    s=settings(tmp_path);saved=batch(s)
    saved["protocol"]["environment"]["pandas"]="different-version"
    assert validate(saved,s,source_hashes())=="research_environment_changed"


def test_worker_keeps_legacy_observations_without_appending_unverified_forward_results(tmp_path,monkeypatch):
    monkeypatch.setattr(module.StrategyFactory,"build",lambda *a,**kw:NS(generate_signal=lambda df:TradeSignal("test","buy",.9,100,200)))
    worker=module.StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event())
    now=datetime(2026,11,9,23,tzinfo=timezone.utc)
    old=worker.run_once(frame(650),now)
    old["batches"][0].pop("protocol")
    before=deepcopy(old["batches"][0]["candidates"])
    worker.path.write_text(json.dumps(old))
    result=worker.run_once(frame(680),now)
    assert result["batches"][0]["forward_integrity"]=="legacy_protocol_unverified"
    assert result["batches"][0]["candidates"]==before
    assert result["batches"][-1]["forward_integrity"]=="verified_frozen_protocol"
    assert len(result["batches"])==2 and result["orders_sent"]==0


def test_loaded_worker_refuses_source_changes_until_restart(tmp_path,monkeypatch):
    worker=module.StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event())
    monkeypatch.setattr(module,"source_hashes",lambda:{"changed":"hash"})
    with pytest.raises(RuntimeError,match="restart_required"):
        worker.run_once(frame(),datetime(2026,11,9,23,tzinfo=timezone.utc))
    assert not worker.path.exists()


def test_actual_forward_evaluation_keeps_original_costs_after_runtime_changes(tmp_path,monkeypatch):
    monkeypatch.setattr(module.StrategyFactory,"build",lambda *a,**kw:NS(generate_signal=lambda df:TradeSignal("test","buy",.9,100,200)))
    worker=module.StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event())
    now=datetime(2026,11,9,23,tzinfo=timezone.utc)
    worker.run_once(frame(650),now)
    worker.settings=replace(worker.settings,backtest_slippage_cost_bps=99)
    result=worker.run_once(frame(680),now)
    assert len(result["batches"])==1
    for candidate in result["batches"][0]["candidates"]:
        assert candidate["forward"]
        assert all(row["net_r"]==pytest.approx(-.2) for row in candidate["forward"])


def test_source_change_during_backtest_prevents_result_publication(tmp_path,monkeypatch):
    monkeypatch.setattr(module.StrategyFactory,"build",lambda *a,**kw:NS(generate_signal=lambda df:TradeSignal("test","buy",.9,100,200)))
    worker=module.StrategyResearchWorker(settings(tmp_path),KnowledgeStore(str(tmp_path)),threading.Event())
    monkeypatch.setattr(module,"source_hashes",Mock(side_effect=[worker._loaded_source_hashes,{"changed":"hash"}]))
    with pytest.raises(RuntimeError,match="during_evaluation"):
        worker.run_once(frame(650),datetime(2026,11,9,23,tzinfo=timezone.utc))
    assert not worker.path.exists()
