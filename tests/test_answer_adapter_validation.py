import pytest

from atlas_ai.ui.ask_atlas import AskAtlasService


class Source:
    def load_status(self):
        return {"action": "hold", "message": "No directional signal.", "chosen": {"side": "flat", "confidence": 0.3}}

    def load_runtime_flags(self):
        return {"execute_trades": False}

    def load_events(self, limit=160):
        return []


@pytest.mark.parametrize("question", [
    "buy or sell", "market bias", "What is your status?",
    "Why are you not trading?", "What can you do?", "What are your limitations?",
])
def test_all_informational_answers_have_a_real_relevance_result(question):
    reply = AskAtlasService(Source()).answer(question)
    trace = reply["answer_trace"]
    assert trace["normalized_question"] == question
    assert trace["relevance_passed"] is True
    assert trace["relevance_result"] != "direct_handler"
    assert trace["selected_intent"] == reply["intent"]
    assert trace["evidence"]


def test_rejected_direct_draft_never_enters_memory(monkeypatch):
    service = AskAtlasService(Source())
    monkeypatch.setattr(service, "_build_structured_trading_analysis_reply", lambda q: {
        "intent": "capabilities", "selected_domain": "self_model", "result": "Status: HOLD | Mode: Paper",
    })
    reply = service.answer("buy or sell")
    # Domain validation rejects a state dump lacking the claimed self-model.
    assert reply["result"] != "Status: HOLD | Mode: Paper"
    latest = service.memory.latest()
    assert latest is None or latest.main_conclusion != "Status: HOLD | Mode: Paper"


def test_structured_voice_answer_preserves_analysis_and_shortens_text():
    standard = AskAtlasService(Source()).answer("buy or sell")
    voice = AskAtlasService(Source()).answer("buy or sell", mode="voice")
    for key in ("market_bias", "signal_bias", "chart_structure_bias", "higher_timeframe_bias", "final_trade_bias", "entry_quality", "recommended_action", "evidence_separation"):
        assert voice["trading_analysis"][key] == standard["trading_analysis"][key]
    assert voice["intent"] == standard["intent"]
    assert len(voice["result"]) < len(standard["result"])
    assert "Recommended action" in voice["result"]
