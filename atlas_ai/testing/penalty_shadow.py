"""Matched, paper-only score study; does not reproduce broker execution policy."""
from copy import deepcopy
import math

from atlas_ai.analysis.decision_analysis import build_structured_decision_analysis
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.confidence_penalty_audit import make_trader, trace_candidate


def paired_candidate(settings, payload, status, runtime=None):
    payload = KnowledgeStore._normalize_learning_payload(deepcopy(payload))
    if status.get("symbol") != settings.symbol or str(status.get("timeframe","")).upper() != settings.timeframe.upper():
        return None, "market_scope_changed"
    chosen = status.get("chosen") or {}
    if chosen.get("side") not in {"buy", "sell"}: return None, "no_chosen_direction"
    generation = status.get("signal_generation") or {}; context = generation.get("context") or {}
    candidates = [row for row in generation.get("candidates", []) if row.get("strategy") == chosen.get("strategy")]
    if len(candidates) != 1: return None, "raw_candidate_unavailable"
    raw = candidates[0]; published = raw.get("after_filters") or {}
    if published.get("side") != chosen["side"]: return None, "chosen_side_does_not_match_pipeline"
    counts = make_trader(settings, payload)._historical_loss_pattern_counts()
    baseline = trace_candidate(settings, payload, context, raw)
    alternative = trace_candidate(settings, payload, context, raw, count_override={key: 0 for key in counts})
    observed_seed = chosen.get("signal_confidence_seed")
    if (not isinstance(observed_seed, (float, int)) or not math.isfinite(observed_seed)
            or not isinstance(published.get("confidence"), (float, int)) or not math.isfinite(published["confidence"])
            or abs(baseline["replayed_confidence"] - published["confidence"]) > 1e-9
            or abs(observed_seed - published["confidence"]) > 1e-9):
        return None, "baseline_seed_not_reproduced"
    if baseline["replayed_side"] != chosen["side"] or alternative["replayed_side"] != chosen["side"]:
        return None, "direction_changed_outside_penalty_scope"
    threshold = status.get("min_confidence_threshold")
    if not isinstance(threshold, (float, int)) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        return None, "effective_conviction_threshold_unavailable"
    scores = {}
    for name, trace in (("baseline", baseline), ("alternative", alternative)):
        copy = deepcopy(status)
        copy["chosen"] = {**chosen, "confidence": trace["replayed_confidence"],
                          "signal_confidence_seed": trace["replayed_confidence"]}
        view = build_structured_decision_analysis(status=copy, runtime={**(runtime or {}),"execute_trades": False,"gemini_influence_enabled": False})
        scores[name] = float(view["confidence_score"]) / 100
    captured_analysis = (status.get("decision_analysis") or {}).get("confidence_score")
    if not isinstance(captured_analysis, (float, int)) or not math.isfinite(captured_analysis) or abs(scores["baseline"]*100-captured_analysis) > .01:
        return None, "baseline_analysis_not_reproduced"
    timing = (status.get("timing_discipline") or {}).get("passed")
    if not isinstance(timing, bool): return None, "recorded_timing_unavailable"
    protection = [chosen.get("stop_loss_points"), chosen.get("take_profit_points")]
    if not all(isinstance(value, (float, int)) and math.isfinite(value) and value > 0 for value in protection):
        return None, "protection_unavailable"
    return {"strategy": chosen["strategy"], "side": chosen["side"],
            "stop_loss_points": protection[0], "take_profit_points": protection[1],
            "seed_baseline": baseline["replayed_confidence"], "seed_alternative": alternative["replayed_confidence"],
            "conviction_baseline": scores["baseline"], "conviction_alternative": scores["alternative"],
            "effective_conviction_threshold": threshold, "recorded_timing_passed": timing,
            "admit_baseline": timing and scores["baseline"] >= threshold,
            "admit_alternative": timing and scores["alternative"] >= threshold,
            "other_execution_gates_verified": False}, None


def stage(rows):
    result = {"resolved_pairs": len(rows),
              "score_changed_pairs": sum(abs(row["seed_baseline"]-row["seed_alternative"]) > 1e-9 for row in rows),
              "admission_difference_pairs": sum(row["admit_baseline"] != row["admit_alternative"] for row in rows)}
    for name in ("baseline", "alternative"):
        selected = [row for row in rows if row["admit_"+name]]
        positive = sum(max(0., row["net_r"]) for row in selected)
        negative = sum(max(0., -row["net_r"]) for row in selected)
        result[name] = {"paper_admissions": len(selected), "net_r": positive-negative,
                        "mean_net_r": (positive-negative)/len(selected) if selected else None,
                        "net_cash": sum(row["net_cash"] for row in selected),
                        "profit_factor": positive/negative if negative else None}
    result["alternative_minus_baseline_r"] = result["alternative"]["net_r"] - result["baseline"]["net_r"]
    result["contrast_sufficient_for_review"] = (len(rows) >= 30 and result["score_changed_pairs"] >= 10
                                              and result["admission_difference_pairs"] >= 5)
    return result
