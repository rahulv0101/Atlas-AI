import pytest

from atlas_ai.llm.gemini_helper import GeminiAdvisor


@pytest.mark.parametrize("message,kind", [
    ("401 Incorrect API key provided: secret-value", "authentication_failed"),
    ("404 model not found; request private context", "model_or_endpoint_unavailable"),
])
def test_configuration_failure_is_sanitized_and_not_retried_each_cycle(message,kind):
    advisor=GeminiAdvisor()
    advisor._providers=["openai"];advisor.enabled=True
    advisor._enter_cooldown("openai",RuntimeError(message))
    provider=advisor.health_summary()["providers"][0]
    assert provider["last_error_kind"]==kind
    assert provider["cooldown_seconds_left"]>3600
    assert "secret-value" not in str(advisor.health_summary())
    assert "private context" not in str(advisor.health_summary())
    advisor._summarize_via_openai=lambda prompt:pytest.fail("Do not retry a configuration fault during cooldown")
    assert kind in advisor.summarize_market_context({})


def test_gemini_model_is_explicitly_configurable(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL","gemini-2.5-flash")
    assert GeminiAdvisor()._gemini_model=="gemini-2.5-flash"
    assert GeminiAdvisor(gemini_model="explicit-model")._gemini_model=="explicit-model"
    monkeypatch.delenv("GEMINI_MODEL")
    assert GeminiAdvisor()._gemini_model=="gemini-2.5-flash"
