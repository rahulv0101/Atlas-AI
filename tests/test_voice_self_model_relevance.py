import pytest

from atlas_ai.ui.ask_atlas import AskAtlasService


class Source:
    def load_status(self):
        return {"action": "hold", "message": "No directional trade signal selected.", "chosen": {"side": "flat", "confidence": .45}}
    def load_runtime_flags(self):
        return {"execute_trades": False}
    def load_events(self, limit=160):
        return []
    def load_comparison(self):
        return {}


@pytest.mark.parametrize("query,intent", [
    ("What can you do?", "capabilities"),
    ("What are your limitations?", "limitations"),
    ("How much do you know about the markets?", "self_knowledge"),
])
def test_voice_self_model_passes_same_relevance_guard_as_typed(query, intent):
    typed = AskAtlasService(Source()).answer(query)
    voice = AskAtlasService(Source()).answer(query, mode="voice")
    for reply in [typed, voice]:
        assert reply["intent"] == intent
        assert reply["selected_domain"] == "self_model"
        assert reply["answer_trace"]["relevance_passed"] is True
        assert "couldn't ground" not in reply["result"]
        assert "Status: hold" not in reply["result"]
    assert len(voice["result"]) < len(typed["result"])
