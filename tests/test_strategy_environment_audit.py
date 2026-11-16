import json
from tools.audit_strategy_environment import inspect_env


def test_environment_audit_never_echoes_secrets_even_for_parse_errors(tmp_path):
    env = tmp_path / '.env'
    env.write_text('GEMINI_API_KEY=private-key\nHFM_PASSWORD=private-password\n'
                   'BROKEN="private-malformed\n', encoding='utf-8')
    result = inspect_env(env, {})
    serialized = json.dumps(result)
    assert 'private' not in serialized
    assert result['api_key_configured']['GEMINI_API_KEY'] is True
    assert result['malformed_line_numbers'] == [3]
    assert result['api_authentication'] == 'not_tested'


def test_environment_audit_detects_duplicate_keys_and_empty_process_override(tmp_path):
    env = tmp_path / '.env'
    env.write_text('GEMINI_API_KEY=secret\nTIMEFRAME=M1\nTIMEFRAME=M5\nMAX_RISK_PER_TRADE=nan\n')
    result = inspect_env(env, {'GEMINI_API_KEY': ''})
    assert result['duplicate_keys'] == ['TIMEFRAME']
    assert result['process_override_keys'] == ['GEMINI_API_KEY']
    assert result['api_key_configured']['GEMINI_API_KEY'] is False
    assert result['invalid_positive_numeric_keys'] == ['MAX_RISK_PER_TRADE']


def test_environment_audit_checks_paths_without_revealing_them(tmp_path):
    terminal = tmp_path / 'terminal.exe'
    terminal.write_bytes(b'')
    env = tmp_path / '.env'
    env.write_text('HFM_TERMINAL_PATH=' + terminal.as_posix() + '\n'
                   'OLD_PATH=C:/Users/User/private/terminal.exe\n')
    result = inspect_env(env, {})
    assert result['terminal_path_exists'] is True
    assert result['old_account_path_keys'] == ['OLD_PATH']
    assert 'private' not in json.dumps(result)
    assert terminal.as_posix() not in json.dumps(result)


def test_environment_audit_honors_expansion_and_explicit_empty_override(tmp_path):
    env = tmp_path / '.env'
    env.write_text('GEMINI_API_KEY=${PROVIDER_KEY}\nOPENAI_API_KEY=private-file-key\n')
    result = inspect_env(env, {'PROVIDER_KEY': 'private-expanded', 'OPENAI_API_KEY': ''})
    assert result['api_key_configured'] == {'GEMINI_API_KEY': True, 'OPENAI_API_KEY': False}
    assert result['dotenv_api_key_configured']['OPENAI_API_KEY'] is True
    assert result['process_override_keys'] == ['OPENAI_API_KEY']
    assert 'private' not in json.dumps(result)


def test_rejection_trace_refuses_changed_prediction_receipt_before_broker_calls(tmp_path, monkeypatch):
    import pytest
    import MetaTrader5 as mt5
    from tools.audit_strategy_environment import trace_structural
    from tools.learn_candidate_ranker import save_signed, digest
    source = tmp_path / 'source'
    source.mkdir()
    save_signed(source, 'protocol', {'fixture': True})
    protocol_hash = digest(source / 'protocol.json')
    save_signed(source, 'source_receipt', {'protocol_sha256': protocol_hash})
    save_signed(source, 'prediction_receipt', {'protocol_sha256': protocol_hash})
    save_signed(source, 'report', {'state': 'completed_research_only',
                                 'protocol_sha256': protocol_hash,
                                 'prediction_receipt_sha256': 'tampered'})
    def forbidden(*args, **kwargs):
        pytest.fail('diagnostic must not contact or initialize broker')
    monkeypatch.setattr(mt5, 'initialize', forbidden)
    monkeypatch.setattr(mt5, 'order_send', forbidden)
    with pytest.raises(ValueError, match='structural_predictions_changed'):
        trace_structural(source, tmp_path / 'baseline')
