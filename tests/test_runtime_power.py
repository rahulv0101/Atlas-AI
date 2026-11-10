import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from atlas_ai.runtime_power import live_power_guard, ES_CONTINUOUS, ES_SYSTEM_REQUIRED


def test_acquisition_is_scoped_and_restores_prior_thread_state_on_exception(tmp_path):
    setter=Mock(side_effect=[ES_CONTINUOUS, ES_CONTINUOUS | ES_SYSTEM_REQUIRED])
    with pytest.raises(RuntimeError):
        with live_power_guard(tmp_path,native=SimpleNamespace(SetThreadExecutionState=setter)) as state:
            assert state["active"] and not state["display_required"]
            assert json.loads((tmp_path/"runtime_power"/f"power_{os.getpid()}.json").read_text())["active"]
            raise RuntimeError("worker stopped")
    assert [c.args[0] for c in setter.call_args_list]==[ES_CONTINUOUS | ES_SYSTEM_REQUIRED,ES_CONTINUOUS]
    assert json.loads((tmp_path/"runtime_power"/f"power_{os.getpid()}.json").read_text())["state"]=="released"


def test_disabled_request_does_not_call_windows(tmp_path):
    setter=Mock()
    with live_power_guard(tmp_path,native=SimpleNamespace(SetThreadExecutionState=setter),enabled=False) as state:
        assert state["state"]=="disabled"
    setter.assert_not_called()


def test_failed_native_request_is_visible_and_does_not_prevent_cleanup(tmp_path):
    setter=Mock(return_value=0)
    with live_power_guard(tmp_path,native=SimpleNamespace(SetThreadExecutionState=setter)) as state:
        assert state["state"]=="power_request_failed" and not state["active"]
    assert setter.call_count==1
