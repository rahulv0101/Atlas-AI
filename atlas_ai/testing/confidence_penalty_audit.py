"""Read-only reconstruction of the existing confidence policy, never a replacement."""
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone

from atlas_ai.learning.evidence_provenance import outcome_source, source_counts
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.trader import AtlasTrader


class SnapshotStore:
    """Expose only the immutable read required by the existing policy methods."""
    def __init__(self, payload):
        self.payload = deepcopy(payload)

    def load_learning_state(self):
        return deepcopy(self.payload)


def make_trader(settings, payload):
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = settings
    trader.store = SnapshotStore(payload)
    return trader


def trace_candidate(settings, payload, context, candidate, *, count_override=None):
    """Call real gating/learning methods on an isolated instance; no execution adapter."""
    trader = make_trader(settings, payload)
    if count_override is not None:
        trader._historical_loss_pattern_counts = lambda: dict(count_override)
    trace = {}
    timing = trader._apply_entry_timing_learning
    lesson = trader._loss_pattern_lesson_adjustment

    def inspect_lesson(signal, ctx):
        before = signal.confidence
        after, metadata = lesson(signal, ctx)
        trace["lesson"] = {key: metadata.get(key) for key in
            ("applied", "reason", "samples", "loss_rate", "match_strength", "match_score", "haircut", "factor")}
        trace["lesson"].update(input_confidence=before, output_confidence=after)
        return after, metadata

    def inspect_timing(signal, ctx):
        trace["timing_input_confidence"] = signal.confidence
        result = timing(signal, ctx)
        trace["timing_output_confidence"] = result.confidence
        return result

    trader._loss_pattern_lesson_adjustment = inspect_lesson
    trader._apply_entry_timing_learning = inspect_timing
    raw = candidate.get("before_filters") or {}
    signal = TradeSignal(str(candidate["strategy"]), str(raw.get("side", "flat")),
                         float(raw.get("confidence", 0)), 0., 0.)
    diagnostics = {}
    result = trader._apply_signal_generation_gating(signal, deepcopy(context), diagnostics=diagnostics)
    trace.update(strategy=candidate["strategy"], side=raw.get("side"),
                 raw_confidence=raw.get("confidence"), replayed_confidence=result.confidence,
                 replayed_side=result.side, reason_codes=diagnostics.get("reason_codes", []))
    if "lesson" in trace:
        heuristic_output = trace["lesson"]["input_confidence"]
        before = trace["timing_input_confidence"]
        trace["heuristic_multiplier"] = heuristic_output / before if before > 0 else None
        trace["heuristic_output_confidence"] = heuristic_output
    return trace


def audit(settings, raw_payload, status, *, now=None):
    now = now or datetime.now(timezone.utc)
    payload = KnowledgeStore._normalize_learning_payload(deepcopy(raw_payload))
    state = payload.get("state") or {}
    history = state.get("historical_loss_analysis") or {}
    memory = state.get("loss_memory") or {}
    counts = make_trader(settings, payload)._historical_loss_pattern_counts()
    historical_rows = history.get("loss_samples") or []
    generated = history.get("generated_at")
    age = None
    try:
        at = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        if at.tzinfo is not None: age = round((now-at).total_seconds()/86400, 2)
    except ValueError: pass
    pipeline = status.get("signal_generation") or {}
    context = pipeline.get("context") or {}
    traces = []
    for candidate in pipeline.get("candidates") or []:
        traced = trace_candidate(settings, payload, context, candidate)
        observed = candidate.get("after_filters") or {}
        traced["published_confidence"] = observed.get("confidence")
        traced["replay_matches_published"] = (traced["replayed_side"] == observed.get("side")
            and isinstance(observed.get("confidence"), (int, float))
            and abs(traced["replayed_confidence"]-observed["confidence"]) < 1e-9)
        # Diagnostic ablations use the same code and all other counts unchanged.
        # They describe score sensitivity, not the profitability of disabling a rule.
        impacts = []
        for name in counts:
            alternate = trace_candidate(settings, payload, context, candidate,
                                         count_override={**counts, name: 0})
            delta = alternate["replayed_confidence"] - traced["replayed_confidence"]
            if abs(delta) > 1e-12:
                impacts.append({"count_removed": name, "stored_count": counts[name],
                                "confidence_difference": delta})
        traced["count_sensitivity_only"] = impacts
        traces.append(traced)
    # Synthetic controls make rule behaviour inspectable even when the current
    # market suppresses candidates before the timing-learning method is reached.
    control = {**context, "allowed_session": True, "regime": "trend", "trend_strength": .2, "volatility_state": "normal",
               "entry_location_state": "consolidation", "entry_momentum_state": "weak",
               "entry_expansion": 0., "entry_position": .5, "entry_wickiness": .6}
    candidate = {"strategy": "ema_crossover", "before_filters": {"side": "buy", "confidence": .5}}
    controls = {"wick_heavy_synthetic": trace_candidate(settings, payload, control, candidate),
                "lower_wick_synthetic": trace_candidate(settings, payload, {**control, "entry_wickiness": .2}, candidate),
                "empty_historical_aggregate_synthetic": trace_candidate(settings, payload, control, candidate, count_override={})}
    raw_memory = (raw_payload.get("state") or {}).get("loss_memory") or {}
    return {
        "schema": "atlas_confidence_penalty_audit_v1", "checked_at": now.isoformat(),
        "publication_at": status.get("updated_at"), "timeframe": settings.timeframe,
        "historical_count_source": {"source": history.get("source"), "generated_at": generated,
            "age_days": age, "total_trades": history.get("total_trades"),
            "sampled_loss_count": history.get("sampled_loss_count"), "classification_counts": counts,
            "sample_sources": dict(Counter(outcome_source(row) for row in historical_rows)),
            "recency_gate_in_existing_count_rule": False,
            "lesson_adjustment_requires_nonempty_historical_counts": True,
            "contextual_win_denominator_available": False,
            "scope": "Global loss-class totals; most heuristic rules are not strategy-specific."},
        "retained_lesson_memory": {"raw_sources": source_counts(raw_memory),
            "effective_sources": source_counts(memory), "pattern_lessons": len(memory.get("pattern_lessons") or {}),
            "broker_ticket_alone_proves_strategy_execution": False,
            "context_link_is_not_protected_lifecycle_proof": True},
        "current_context": {key: context.get(key) for key in
            ("session", "regime", "entry_location_state", "entry_momentum_state", "entry_wickiness", "entry_expansion", "entry_position")},
        "candidates": traces,
        "synthetic_controls_not_trades": controls,
        "limitations": ["Post-publication snapshot; not atomic pre-decision state or resident-code identity.",
                        "Count ablations show score effects, not cost-aware trading performance.",
                        "Tagged diagnostic exclusion cannot identify every ordinary manual broker trade.",
                        "Existing timing-veto backtests do not independently establish benefit of these confidence haircuts."],
        "validation": {"confidence_penalty_benefit_established": False,
                       "finding": "Loss counts and lesson matches alone do not establish improved future net returns.",
                       "required_next_evidence": "Predeclared matched baseline/penalty comparison with costs and untouched future outcomes."},
        "broker_eligible": False, "orders_sent": 0, "policy_changes": [],
    }
