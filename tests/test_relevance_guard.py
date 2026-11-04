from __future__ import annotations

from atlas_ai.brain.relevance_guard import check_relevance
from atlas_ai.brain.answer_engine import AnswerEngine
from atlas_ai.brain.types import AnswerPlan, EvidenceItem, RelevanceCheckResult


def test_self_question_rejects_status_dump_without_self_shape() -> None:
    result = check_relevance(
        query="What can you do?",
        domain="self_model",
        answer="Status: HOLD | Reason: No high-confidence trade found. | Mode: PAPER | Run: atlas_wake_latest",
    )

    assert result.passed is False
    assert result.reason == "irrelevant_state_leakage"


def test_limitation_question_rejects_trade_blocker_answer_without_self_shape() -> None:
    result = check_relevance(
        query="What are your limitations?",
        domain="self_model",
        answer="No high-confidence trade found. Conservative pre-trade filter blocked trade.",
    )

    assert result.passed is False
    assert result.reason == "irrelevant_trade_state_answer"


def test_self_question_allows_grounded_self_model_even_when_role_mentions_paper() -> None:
    result = check_relevance(
        query="What can you do?",
        domain="self_model",
        answer="Capabilities:\n- explain status\n\nCurrent role:\n- Paper-mode operator assistant with read-only Ask Atlas answers.",
    )

    assert result.passed is True


def test_liquidity_question_rejects_runtime_state_leakage() -> None:
    result = check_relevance(
        query="What is liquidity?",
        domain="market_knowledge",
        answer="Status: HOLD\nReason: No high-confidence trade found.\nMode: Paper",
    )

    assert result.passed is False
    assert result.reason == "knowledge_query_state_leakage"


def test_answer_engine_does_not_return_a_draft_rejected_twice(monkeypatch):
    checks = []

    def reject(**kwargs):
        checks.append(kwargs["answer"])
        return RelevanceCheckResult(False, "irrelevant_state_leakage")

    monkeypatch.setattr("atlas_ai.brain.answer_engine.synthesize", lambda **kwargs: "Status: HOLD | Mode: PAPER")
    monkeypatch.setattr("atlas_ai.brain.answer_engine.check_relevance", reject)
    result = AnswerEngine().answer("What can you do?", {})

    assert len(checks) == 2
    assert result.relevance_passed is False
    assert "Status: HOLD" not in result.text
    assert "available evidence" in result.text
    assert result.confidence == 0.2
    assert result.debug_summary["answer_trace"]["relevance_passed"] is False


def test_retry_reports_the_plan_and_evidence_actually_used(monkeypatch):
    evidence = [
        EvidenceItem("runtime", "current_system_state", "blocked", 1, 1, "fact", 1),
        EvidenceItem("knowledge.market", "market_knowledge", "liquidity facts", 1, 1, "fact", 1),
    ]
    checks = iter([RelevanceCheckResult(False, "irrelevant"), RelevanceCheckResult(True, "ok")])
    monkeypatch.setattr("atlas_ai.brain.answer_engine.collect_evidence", lambda **kwargs: evidence)
    monkeypatch.setattr("atlas_ai.brain.answer_engine.choose_plan", lambda intent, domain: AnswerPlan(intent, []))
    monkeypatch.setattr("atlas_ai.brain.answer_engine.check_relevance", lambda **kwargs: next(checks))
    monkeypatch.setattr("atlas_ai.brain.answer_engine.synthesize", lambda **kwargs: kwargs["plan"].name)

    result = AnswerEngine().answer("What is liquidity?", {})

    assert result.relevance_passed is True
    assert result.selected_plan == "unknown_operator_query"
    assert result.evidence_used == [evidence[1]]
    trace = result.debug_summary["answer_trace"]
    assert trace["selected_plan"] == result.selected_plan
    assert [item["source"] for item in trace["evidence"]] == ["knowledge.market"]


def test_ask_service_rejects_failed_engine_text_without_remembering_it(monkeypatch):
    from dataclasses import replace
    from atlas_ai.ui.ask_atlas import AskAtlasService

    class Source:
        def load_status(self):
            return {}

        def load_events(self, limit=160):
            return []

        def load_runtime_flags(self):
            return {"execute_trades": False}

    service = AskAtlasService(Source())
    rejected = replace(
        AnswerEngine().answer("What can you do?", {}),
        text="Status: HOLD | Mode: PAPER", relevance_passed=False,
    )
    monkeypatch.setattr(service.answer_engine, "answer", lambda *args, **kwargs: rejected)
    response = service.answer("What can you do?")

    assert "Status: HOLD" not in response["result"]
    assert "available evidence" in response["result"]
    assert service.memory.latest() is None
    assert response["control_items_created"] == []
    assert service.decision_journal.recent() == []
