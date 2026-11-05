from unittest.mock import Mock

import pytest

from atlas_ai.ui.ask_atlas import AskAtlasService


class Source:
    def load_status(self):
        return {"action": "hold", "message": "No directional trade signal selected.", "chosen": {"side": "flat", "confidence": 0}, "signal_generation": {"directional_before_filters": 1, "directional_after_filters": 0, "candidates": [{"strategy": "ema_crossover", "suppressed": True, "reason_codes": ["low_energy_directional_suppression"]}]}}

    def load_events(self, limit=160): return []
    def load_runtime_flags(self): return {"execute_trades": False}
    def load_comparison(self): return {}


@pytest.mark.parametrize("mode", ["standard", "voice"])
def test_current_blocker_uses_shared_brain_instead_of_old_execution_reason(monkeypatch, mode):
    service = AskAtlasService(Source())
    monkeypatch.setattr(service.execution, "snapshot", lambda **kwargs: {"auto_trade_reason": "runtime_context_required", "tiny_live_pilot_last_block_reason": "historical_rejection", "last_execution_result": {"reason": "another_old_failure"}})
    response = service.answer("What is blocking trading right now?", mode=mode)
    assert response["intent"] == "blocker"
    assert response["answer_trace"]["relevance_passed"]
    assert "runtime_context_required" not in response["result"]
    assert "historical_rejection" not in response["result"]
    assert any(word in response["result"].lower() for word in ("signal", "directional", "generation"))


def test_current_safety_veto_remains_visible(monkeypatch):
    service = AskAtlasService(Source())
    monkeypatch.setattr(service.execution, "snapshot", lambda **kwargs: {"kill_switch_active": True, "auto_trade_reason": "runtime_context_required"})
    response = service.answer("Why is execution blocked?")
    assert "kill_switch" in response["result"]
