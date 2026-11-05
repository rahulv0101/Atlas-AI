import pytest

from atlas_ai.backtest import Backtester


@pytest.mark.parametrize("timestamp,session", [
    ("2026-11-04T06:59:00Z", "other"),
    ("2026-11-04T07:00:00Z", "london"),
    ("2026-11-04T11:59:00Z", "london"),
    ("2026-11-04T12:00:00Z", "new_york"),
    ("2026-11-04T16:59:00Z", "new_york"),
    ("2026-11-04T17:00:00Z", "late_us"),
    ("2026-11-04T20:59:00Z", "late_us"),
    ("2026-11-04T21:00:00Z", "other"),
    ("2026-11-04T14:30:00+02:00", "new_york"),
    ("2026-11-04T08:30:00-04:00", "new_york"),
    ("2026-11-04 08:00:00", "london"),
    ("invalid", "other"),
])
def test_backtest_session_uses_utc_hour(timestamp, session):
    assert Backtester()._session_label(timestamp) == session
