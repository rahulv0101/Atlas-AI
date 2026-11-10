"""Freeze research methods; never authorize trading or infer missing provenance."""
from dataclasses import replace
import hashlib
import json
from importlib import metadata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "atlas_ai/strategies/research_protocol.py", "atlas_ai/strategies/research_worker.py",
    "atlas_ai/strategies/strategy_factory.py", "atlas_ai/strategies/strategy_inventor.py",
    "atlas_ai/strategies/dna.py", "atlas_ai/strategies/gold_validator.py",
    "atlas_ai/learning/trade_labeling.py", "atlas_ai/execution/session_control.py",
)
SIMULATOR_FIELDS = (
    "symbol", "timeframe", "backtest_point_size", "backtest_max_hold_bars",
    "backtest_slippage_cost_bps", "backtest_break_even_r_trigger", "backtest_break_even_lock_r",
    "backtest_trailing_r_trigger", "backtest_trailing_buffer_r", "backtest_stale_exit_bars",
    "backtest_stale_min_progress_r",
)


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def gene_hash(chromosome):
    return hashlib.sha256(json.dumps(chromosome["genes"], sort_keys=True, allow_nan=False).encode()).hexdigest()


def environment_versions():
    versions = {"python": sys.version}
    for name in ("numpy", "pandas", "MetaTrader5"):
        versions[name] = metadata.version(name)
    return versions


def freeze(settings):
    return {"schema": "atlas_chart_research_protocol_v1", "source_hashes": source_hashes(),
            "simulator": {name: getattr(settings, name) for name in SIMULATOR_FIELDS},
            "environment": environment_versions(),
            "broker_eligible": False, "orders_sent": 0}


def validate(batch, settings, current_hashes):
    protocol = batch.get("protocol") or {}
    if protocol.get("schema") != "atlas_chart_research_protocol_v1":
        return "legacy_protocol_unverified"
    if protocol.get("source_hashes") != current_hashes:
        return "source_changed"
    if protocol.get("environment") != environment_versions():
        return "research_environment_changed"
    simulator = protocol.get("simulator") or {}
    if set(simulator) != set(SIMULATOR_FIELDS):
        return "simulator_protocol_incomplete"
    if simulator["symbol"] != settings.symbol or simulator["timeframe"] != settings.timeframe:
        return "market_scope_changed"
    if protocol.get("broker_eligible") is not False or protocol.get("orders_sent") != 0:
        return "invalid_research_boundary"
    try:
        for candidate in batch["candidates"]:
            if candidate.get("frozen_gene_sha256") != gene_hash(candidate["chromosome"]):
                return "candidate_rules_changed"
    except (KeyError,TypeError,ValueError):
        return "candidate_rules_invalid"
    return "verified_frozen_protocol"


def frozen_settings(settings, batch):
    return replace(settings, execute_trades=False, **batch["protocol"]["simulator"])
