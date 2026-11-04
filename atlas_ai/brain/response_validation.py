"""Validate specialist answer adapters with the same Brain v2 evidence and guard."""
from copy import deepcopy
from dataclasses import replace
from typing import Any, Callable

from atlas_ai.brain.debug import build_debug_summary
from atlas_ai.brain.domain import detect_domain_candidates
from atlas_ai.brain.evidence import collect_evidence
from atlas_ai.brain.intent import classify_intent_candidates
from atlas_ai.brain.planner import choose_plan
from atlas_ai.brain.relevance_guard import check_relevance, relevance_failure_response
from atlas_ai.brain.self_model import build_self_model


def finalize_adapter_response(
    question: str, payload: dict[str, Any], context: dict[str, Any], *,
    mode: str, regenerate: Callable,
) -> dict[str, Any]:
    q = " ".join(str(question or "").split())
    out = deepcopy(payload)
    intents = classify_intent_candidates(q)
    domains = detect_domain_candidates(q, intents)
    intent = str(out.get("intent") or intents[0].name)
    domain = str(out.get("selected_domain") or domains[0].name)
    if intent in {"self_knowledge", "self_assessment", "capabilities", "limitations"}:
        domain = "self_model"
    status = dict(context.get("status", {}) or {})
    runtime = dict(context.get("runtime", {}) or {})
    comparison = dict(context.get("comparison", {}) or {})
    evidence = collect_evidence(
        query=q, domain=domain, status=status, runtime=runtime,
        events=list(context.get("events", []) or []), comparison=comparison,
        self_model=build_self_model(status, runtime, comparison),
        knowledge_payload=dict(context.get("knowledge_payload", {}) or {}),
    )
    plan = choose_plan(intent, domain)
    text = str(out.get("result", "") or "")
    # Existing specialist formatters synthesize the schema-specific answer. They
    # are adapters to this validation path, not independent reasoning engines.
    relevance = check_relevance(query=q, domain=domain, answer=text)
    attempts = [{"plan": plan.name, "passed": relevance.passed, "reason": relevance.reason}]
    if not relevance.passed:
        retry = regenerate(q, context, mode=mode)
        attempts.extend(retry.debug_summary.get("answer_trace", {}).get("relevance_attempts", []))
        out["result"] = retry.text if retry.relevance_passed else relevance_failure_response()
        out["intent"] = intent = retry.selected_intent
        domain = retry.selected_domain
        evidence = retry.evidence_used
        plan = replace(plan, name=retry.selected_plan)
        passed = retry.relevance_passed
        reason = retry.debug_summary.get("answer_trace", {}).get("relevance_result", "rejected")
        out["confidence"] = retry.confidence
        # Do not retain a specialist schema whose prose failed validation.
        for key in ("trading_analysis", "trading_response"):
            out.pop(key, None)
    else:
        passed, reason = relevance.passed, relevance.reason
    debug = dict(out.get("debug", {}) or {})
    canonical = build_debug_summary(
        intent_candidates=intents, domain_candidates=domains, selected_plan=plan.name,
        evidence_used=evidence, relevance_result=reason,
    )
    debug.update(canonical)
    trace = canonical["answer_trace"]
    trace.update({
        "normalized_question": q, "selected_intent": intent,
        "selected_domain": domain, "selected_plan": plan.name,
        "relevance_passed": passed, "relevance_attempts": attempts,
        "handler": str(out.get("handled_as", "general")), "adapter_validated": True,
    })
    if out.get("evidence_separation"):
        trace["evidence_separation"] = deepcopy(out["evidence_separation"])
    out.update({"selected_domain": domain, "answer_trace": trace, "debug": debug})
    out.setdefault("confidence", 0.7 if passed else 0.2)
    if mode == "voice":
        out["mode"] = "voice"
        trading = dict(out.get("trading_response", {}) or {})
        if passed and trading:
            text = f"Bias: {trading.get('bias', 'neutral')}. Recommended action: {trading.get('recommended_action', 'hold')}."
            blockers = list(trading.get("blockers", []) or [])
            if blockers:
                text += f" Main blocker: {str(blockers[0]).replace('_', ' ')}."
            if out.get("backend_staleness_warning"):
                text = "Warning: Backend data is stale. Last-known answer: " + text
            out["result"] = text
        elif not out.get("backend_staleness_warning"):
            lines = [line for line in str(out.get("result", "")).splitlines() if line.strip()]
            out["result"] = " ".join(lines[:3])[:360]
    return out
