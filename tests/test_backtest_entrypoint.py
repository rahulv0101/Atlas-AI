from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import atlas_ai.main as main
from tools import guarded_research_audit as audit


def test_default_backtest_cannot_reconcile_live_flags_or_log_into_terminal(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"load_settings",lambda:SimpleNamespace(storage_dir=str(tmp_path)))
    forbidden=Mock(side_effect=AssertionError("Backtesting must not mutate runtime controls or log in"))
    monkeypatch.setattr(main,"reconcile_runtime_flags",forbidden)
    monkeypatch.setattr(main,"KnowledgeStore",forbidden)
    monkeypatch.setattr(main,"HFMConnector",forbidden)
    run=Mock(return_value={"state":"completed_research_only","comparisons":{}})
    monkeypatch.setattr(audit,"run_broker_history",run)
    main.run_backtest(mode_override="paper")
    run.assert_called_once()
    assert run.call_args.args[0].parent==tmp_path/"guarded_research"
    forbidden.assert_not_called()


def test_backtest_rejects_live_override_before_any_broker_read(monkeypatch):
    run=Mock(side_effect=AssertionError("No live override"))
    monkeypatch.setattr(audit,"run_broker_history",run)
    with pytest.raises(ValueError,match="cannot enable live"):main.run_backtest(mode_override="live")
    run.assert_not_called()
