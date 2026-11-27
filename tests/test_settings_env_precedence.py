from __future__ import annotations

from atlas_ai.config.settings import load_settings


def test_load_settings_respects_explicit_env_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "isolated_store"))
    monkeypatch.setenv("TIMEFRAME", "M1")
    monkeypatch.setenv("BACKTEST_INITIAL_BALANCE", "100")
    monkeypatch.setenv("HISTORICAL_TRAINING_STAGE_TIMEOUT_SECONDS", "12")

    settings = load_settings()

    assert settings.storage_dir == str((tmp_path / "isolated_store").resolve())
    assert settings.timeframe == "M1"
    assert settings.backtest_initial_balance == 100.0
    assert settings.historical_training_stage_timeout_seconds == 12.0


def test_optional_openai_provider_can_be_disabled_without_altering_gemini_or_trade_controls(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-placeholder')
    monkeypatch.setenv('GEMINI_API_KEY','gemini-test-placeholder')
    monkeypatch.setenv('OPENAI_ENABLED','false')
    disabled=load_settings()
    assert disabled.openai_api_key=='' and disabled.gemini_api_key=='gemini-test-placeholder'
    monkeypatch.setenv('OPENAI_ENABLED','true')
    enabled=load_settings()
    assert enabled.openai_api_key=='test-placeholder'
    assert (enabled.timeframe,enabled.max_risk_per_trade,enabled.max_trades_per_day,enabled.execute_trades)==(
        disabled.timeframe,disabled.max_risk_per_trade,disabled.max_trades_per_day,disabled.execute_trades)
