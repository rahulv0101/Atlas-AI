from copy import deepcopy
import pytest
from tools.align_effective_restrictions import aligned_bytes

RAW=(b'TIMEFRAME=M5\r\nTOP_DOWN_CONFLUENCE_ENABLED=true\r\nHIGHER_TIMEFRAME_CONFIRM=M15 # fallback\r\n'
     b'MAX_TRADES_PER_DAY=12\r\nMAX_CONSECUTIVE_LOSSES=3\r\nHFM_PASSWORD="test secret # quoted"\r\nGEMINI_API_KEY=\r\n')
STATUS={'timeframe':'M5','higher_timeframe':{'confirm_tf':'H1','policy':'top_down_h1_direction_m5_entry_v3'}}
SESSION={'daily_trade_limit':6,'consecutive_loss_limit':2}


def test_alignment_preserves_credentials_and_current_stricter_controls():
    updated,changes=aligned_bytes(RAW,SESSION,STATUS)
    assert b'MAX_TRADES_PER_DAY=6\r\n' in updated
    assert b'MAX_CONSECUTIVE_LOSSES=2\r\n' in updated
    assert b'HIGHER_TIMEFRAME_CONFIRM=H1 # fallback\r\n' in updated
    assert b'HFM_PASSWORD="test secret # quoted"\r\nGEMINI_API_KEY=\r\n' in updated
    assert len(changes)==3
    assert aligned_bytes(updated,SESSION,STATUS)[1]=={}


def test_alignment_cannot_raise_caps_or_change_active_timeframe_policy():
    with pytest.raises(ValueError):aligned_bytes(RAW,{**SESSION,'daily_trade_limit':20},STATUS)
    wrong=deepcopy(STATUS);wrong['higher_timeframe']['confirm_tf']='M15'
    with pytest.raises(ValueError):aligned_bytes(RAW,SESSION,wrong)
    with pytest.raises(ValueError):aligned_bytes(RAW,{**SESSION,'consecutive_loss_limit':0},STATUS)


def test_duplicate_config_lines_cannot_be_silently_rewritten():
    with pytest.raises(ValueError,match='unique_existing_setting'):
        aligned_bytes(RAW+b'MAX_TRADES_PER_DAY=12\r\n',SESSION,STATUS)


def test_existing_doubled_carriage_returns_are_preserved():
    legacy=RAW.replace(b'\r\n',b'\r\r\n')
    updated,changes=aligned_bytes(legacy,SESSION,STATUS)
    assert b'MAX_TRADES_PER_DAY=6\r\r\n' in updated and len(changes)==3
    assert updated.count(b'\r')==legacy.count(b'\r')
