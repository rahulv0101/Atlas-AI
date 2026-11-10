"""Bounded chart-driven research. No broker submission or promotion capability."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import gzip
import json
import math
import logging
import os
import tempfile
from pathlib import Path
import random
import threading

import pandas as pd

from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.execution.automation_state_store import AutomationStateStore
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.learning.trade_labeling import _simulate_trade_path
from atlas_ai.strategies.dna import StrategyChromosome
from atlas_ai.strategies.gold_validator import GoldValidator
from atlas_ai.strategies.strategy_factory import StrategyFactory
from atlas_ai.strategies.strategy_inventor import StrategyInventor


def summary(rows):
    returns = [r["net_r"] for r in rows]
    return {"trades": len(rows), "wins": sum(r > 0 for r in returns),
            "net_r": sum(returns), "mean_r": sum(returns) / len(rows) if rows else None}


def evaluate(chromosome, frame, settings, *, start=120, stop_event=None):
    """Frozen rules, past-only signals, next-open entries, nonoverlapping trades."""
    point = float(settings.backtest_point_size)
    strategy = StrategyFactory.build(chromosome, point_size=point)
    if not math.isfinite(point) or point <= 0:
        raise ValueError("invalid_research_point_size")
    calendar = DayTradingSessionControl()
    horizon = min(60, max(1, int(settings.backtest_max_hold_bars)))
    step_minutes = int(settings.timeframe_minutes)
    rows = []
    i = max(120, start)
    while i + horizon < len(frame):
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("research_stopped")
        at = pd.Timestamp(frame.iloc[i]["time"]).to_pydatetime().replace(tzinfo=timezone.utc)
        session = calendar._detect_session(at)
        if not session.allowed:
            i += 1
            continue
        signal = strategy.generate_signal(frame.iloc[:i + 1])
        if signal.side not in {"buy", "sell"} or signal.confidence < chromosome.gene_value("risk_min_confidence", .55):
            i += 1
            continue
        if not all(math.isfinite(v) and v >= 1 for v in (signal.stop_loss_points, signal.take_profit_points)):
            i += 1
            continue
        available = max(0, (session.minutes_to_close - 11) // step_minutes)
        held = min(horizon, available)
        if held < 1:
            i += 1
            continue
        # Never simulate across a missing candle or a session boundary.
        segment = frame.iloc[i:i + held + 1]["time"]
        if not segment.diff().dropna().eq(pd.Timedelta(minutes=step_minutes)).all():
            i += 1
            continue
        result = _simulate_trade_path(frame.iloc[:i + held + 1], signal, i,
                                     replace(settings, backtest_max_hold_bars=held), ambiguous_bar_policy="stop_first")
        entry = frame.iloc[i + 1]
        spread = float(entry.get("spread", float("nan")))
        if not math.isfinite(spread) or spread < 0:
            raise ValueError("recorded_spread_required")
        slippage = float(entry["open"]) * float(settings.backtest_slippage_cost_bps) / 10000
        gross = float(result["r_multiple"])
        net = gross - (spread * point + slippage) / (signal.stop_loss_points * point)
        if not math.isfinite(net):
            raise ValueError("nonfinite_research_outcome")
        exit_idx = int(result["exit_idx"])
        rows.append({"signal_at": at.isoformat(), "entry_at": pd.Timestamp(frame.iloc[i + 1]["time"]).tz_localize("UTC").isoformat(),
                     "exit_at": pd.Timestamp(frame.iloc[exit_idx]["time"]).tz_localize("UTC").isoformat(), "side": signal.side,
                     "gross_r": gross, "net_r": net, "exit_reason": result["exit_type"]})
        i = max(i + 1, exit_idx + 1)
    return rows, i


class StrategyResearchWorker:
    """Persist frozen candidates separately from the live evolution population."""
    def __init__(self, settings, store, stop_event, *, interval_hours=None, dry_run=False):
        self.settings = replace(settings, execute_trades=False)
        self.store = store
        self.stop_event = stop_event
        self.dry_run = dry_run
        self.interval_seconds = max(300, float(interval_hours or settings.evolution_interval_hours) * 3600)
        self.path = Path(store.base) / "strategy_research" / "state.json"
        self.lock = AutomationStateStore(self.path)
        self.thread = None

    def _load(self):
        if not self.path.exists():
            return {"schema": "atlas_strategy_research_v1", "batches": []}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("schema") != "atlas_strategy_research_v1" or not isinstance(state.get("batches"), list):
            raise ValueError("invalid_research_state")
        return state

    def run_once(self, df=None, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("aware_time_required")
        frame = (MarketDataFeed(self.settings).get_rates(2000) if df is None else df).copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True).dt.tz_localize(None)
        frame = frame[frame["time"] + pd.Timedelta(minutes=self.settings.timeframe_minutes) <= pd.Timestamp(now).tz_convert("UTC").tz_localize(None)].reset_index(drop=True)
        if len(frame) < 600 or not frame["time"].is_monotonic_increasing or frame["time"].duplicated().any():
            raise ValueError("insufficient_or_unordered_closed_bars")
        for column in ("open", "high", "low", "close"):
            if not frame[column].map(lambda v: math.isfinite(float(v)) and float(v) > 0).all():
                raise ValueError("invalid_research_prices")
        if ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any()
                or (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any()):
            raise ValueError("invalid_research_ohlc")
        with self.lock._locked():
            state = self._load()
            asof = frame["time"].iloc[-1].isoformat()
            for batch in state["batches"][-4:]:
                for candidate in batch["candidates"]:
                    cursor = pd.Timestamp(candidate["next_forward_at"])
                    indices = frame.index[frame["time"] >= cursor]
                    if not len(indices):
                        continue
                    start = int(indices[0])
                    if start < 120:
                        candidate["forward_gap"] = True
                        start = 120
                    outcomes, next_idx = evaluate(StrategyChromosome.from_dict(candidate["chromosome"]), frame,
                                                   self.settings, start=start, stop_event=self.stop_event)
                    known = {r["signal_at"] for r in candidate["forward"]}
                    candidate["forward"].extend(r for r in outcomes if r["signal_at"] not in known)
                    candidate["next_forward_at"] = frame.iloc[min(next_idx, len(frame) - 1)]["time"].isoformat()
                    candidate["forward_summary"] = summary(candidate["forward"])
            last_created = state.get("last_created_at")
            due = not last_created or (now - datetime.fromisoformat(last_created)).total_seconds() >= self.interval_seconds
            if due and (not state["batches"] or state["batches"][-1]["asof"] != asof):
                split = int(len(frame) * .7)
                train = frame.iloc[:split].reset_index(drop=True)
                holdout = frame.iloc[split:].reset_index(drop=True)
                # Derive invention context strictly from training bars, never held-out data.
                drift = (float(train["close"].iloc[-1]) / float(train["close"].iloc[-60]) - 1) * 100
                regime = "trend" if abs(drift) >= .12 else "range"
                context = {"context_snapshot": {"regime": regime}, "primary_blocker": ""}
                plans = StrategyInventor().invent(status=context, limit=3)
                candidates = []
                rng = random.Random(int(hashlib.sha256(asof.encode()).hexdigest()[:12], 16))
                chromosomes = [p.chromosome for p in plans]
                chromosomes += [c.mutate(rng, strength=.35) for c in chromosomes[:3]]
                signatures = set()
                for chromosome in chromosomes[:6]:
                    if not GoldValidator().validate_silent(chromosome)[0] or chromosome.signature() in signatures:
                        continue
                    signatures.add(chromosome.signature())
                    training, _ = evaluate(chromosome, train, self.settings, stop_event=self.stop_event)
                    heldout, _ = evaluate(chromosome, holdout, self.settings, stop_event=self.stop_event)
                    candidates.append({"chromosome": chromosome.to_dict(), "training": summary(training),
                                       "holdout": summary(heldout), "forward": [], "forward_summary": summary([]),
                                       "next_forward_at": (frame["time"].iloc[-1] + pd.Timedelta(minutes=self.settings.timeframe_minutes)).isoformat(),
                                       "promotion": "research_only_not_broker_eligible"})
                dataset = frame.to_csv(index=False).encode("utf-8")
                digest = hashlib.sha256(dataset).hexdigest()
                data_path = self.path.parent / "datasets" / (digest + ".csv.gz")
                if not self.dry_run and not data_path.exists():
                    data_path.parent.mkdir(parents=True, exist_ok=True)
                    fd, temporary = tempfile.mkstemp(dir=data_path.parent, suffix=".tmp")
                    try:
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(gzip.compress(dataset, mtime=0))
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary, data_path)
                    finally:
                        Path(temporary).unlink(missing_ok=True)
                state["total_batches"] = int(state.get("total_batches", len(state["batches"]))) + 1
                state["batches"].append({"asof": asof, "created_at": now.isoformat(), "symbol": self.settings.symbol,
                                          "timeframe": self.settings.timeframe, "dataset_sha256": digest, "dataset_file": str(data_path),
                                          "distance_conversion": "factory_broker_points_v1", "training_start": str(train["time"].iloc[0]),
                                          "training_end": str(train["time"].iloc[-1]), "holdout_start": str(holdout["time"].iloc[0]),
                                          "holdout_end": str(holdout["time"].iloc[-1]), "context": context, "candidates": candidates})
                state["last_created_at"] = now.isoformat()
                # Keep only four active batches; archive completed research without
                # allowing old replay history to grow the live worker indefinitely.
                if not self.dry_run:
                    for archived in state["batches"][:-4]:
                        key = hashlib.sha256(archived["created_at"].encode()).hexdigest()[:16]
                        atomic_json(self.path.parent / "archive" / (key + ".json"), archived)
                state["batches"] = state["batches"][-4:]
            state.update(checked_at=now.isoformat(), mode="research_only", timestamp_basis="UTC", orders_sent=0,
                         limitations=["Recorded spread plus hypothetical slippage; commission model not supplied.",
                                      "Historical holdout is not forward trading; repeated research involves multiple comparisons.",
                                      "No promotion into live/demo strategy selection; no arbitrary generated code."])
            if not self.dry_run:
                atomic_json(self.path, state)
                latest = state["batches"][-1] if state["batches"] else {"candidates": []}
                report = {"scheduler_status": "idle", "research_only": True, "orders_sent": 0,
                          "last_evolution_run_at": state.get("last_created_at"), "checked_at": now.isoformat(),
                          "next_evolution_run_at": (datetime.fromisoformat(state["last_created_at"]) + timedelta(seconds=self.interval_seconds)).isoformat(),
                          "total_runs": state.get("total_batches", len(state["batches"])), "active_demo_count": 0, "active_shadow_count": len(latest["candidates"]),
                          "candidate_count": len(latest["candidates"]), "research_state_path": str(self.path),
                          "forward_trades": sum(len(c["forward"]) for b in state["batches"] for c in b["candidates"])}
                atomic_json(Path(self.store.base) / "evolution_scheduler_state.json", report)
            return state

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                try:
                    atomic_json(Path(self.store.base) / "evolution_scheduler_state.json",
                        {"scheduler_status": "failed", "research_only": True, "last_error": type(exc).__name__,
                         "checked_at": datetime.now(timezone.utc).isoformat(), "orders_sent": 0})
                except OSError:
                    logging.getLogger(__name__).exception("Research report publication failed; worker will retry next cycle")
            self.stop_event.wait(60)

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="atlas-strategy-research", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
