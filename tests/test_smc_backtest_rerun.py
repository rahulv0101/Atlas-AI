from types import SimpleNamespace
import pytest
from tools import rerun_smc_backtest as tool
from tools.learn_candidate_ranker import save_signed, signed


def test_fresh_comparison_reuses_one_input_cost_snapshot_and_cannot_activate(tmp_path, monkeypatch):
    storage = tmp_path / 'storage'
    storage.mkdir()
    active = storage / 'smc_validation_active.json'
    active.write_text('{"run_dir":"unchanged"}')
    from atlas_ai.config import settings
    monkeypatch.setattr(settings, 'load_settings', lambda: SimpleNamespace(storage_dir=str(storage)))
    calls = []

    def initialize(directory, model, reuse=None, *, activate, reuse_costs=False):
        calls.append((directory, model, reuse, activate, reuse_costs))
        with pytest.raises(AssertionError):
            tool.mt5.order_send({})
        directory.mkdir()
        save_signed(directory, 'manifest', {'history_start': '2026-05-20T00:00:00Z',
                                           'history_end': '2026-11-16T00:00:00Z'})

    monkeypatch.setattr(tool, 'initialize', initialize)
    run_dir = storage / 'rerun'
    frozen = tool.prepare(run_dir)
    assert len(calls) == 2
    assert all(not row[3] for row in calls)
    assert calls[1][2] == calls[0][0] and calls[1][4] is True
    assert active.read_text() == '{"run_dir":"unchanged"}'
    assert frozen == run_dir / tool.MODELS[0] / 'frozen_source/tools/rerun_smc_backtest.py'
    protocol = signed(run_dir, 'protocol')
    assert protocol['broker_eligible'] is False
    assert protocol['automatic_broker_activation'] is False
    assert protocol['orders_sent'] == 0
    assert protocol['parameter_search'] is False


def test_comparison_refuses_overwriting_a_previous_experiment(tmp_path, monkeypatch):
    from atlas_ai.config import settings
    monkeypatch.setattr(settings, 'load_settings', lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    with pytest.raises(FileExistsError):
        tool.prepare(tmp_path)
