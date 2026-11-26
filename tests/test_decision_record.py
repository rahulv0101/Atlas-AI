from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pandas as pd
import pytest

from atlas_ai.decision_record import bind_record, candle_manifest, cycle_failure, validate_record


def record(action="blocked", execution=None):
    frame = pd.DataFrame({"time": pd.date_range("2026-11-26T12:00:00Z", periods=3, freq="5min"),
                          "open": [1, 2, 3], "high": [2, 3, 4], "low": [.5, 1, 2], "close": [1.5, 2.5, 3.5]})
    cycle = {"decision_id": "scan-1", "as_of_utc": "2026-11-26T12:15:00+00:00",
             "candles": {"M5": candle_manifest(frame, "M5")}}
    status = {"timeframe": "M5", "action": action, "message": "Final reason", "decision_analysis": {},
              "decision_trace": {}, "context_snapshot": {}, "timing_discipline": {"passed": False}}
    if execution is not None:
        status["execution"] = execution
    return bind_record(status, cycle)


def test_same_identity_snapshot_and_final_outcome_across_layers():
    s = record()
    assert validate_record(s)["verified"]
    for k in ("decision_trace", "decision_analysis", "context_snapshot", "timing_discipline"):
        assert s[k]["decision_ref"] == s["decision_ref"]
    assert s["current_execution"]["state"] == "not_submitted"
    assert s["context_snapshot"]["candle_close_utc"] == "2026-11-26T12:15:00+00:00"
    assert bind_record(deepcopy(s), s["decision_snapshot"]) == s


@pytest.mark.parametrize("action,execution,state", [
    ("paper", {"success": False}, "not_submitted"),
    ("blocked", {"request_id": "req-1", "success": False}, "blocked"),
    ("failed", {"request_id": "req-1", "success": False}, "failed"),
    ("execute", {"request_id": "req-1", "success": True, "deal_id": 2}, "filled"),
    ("execute", {"request_id": "req-1", "success": True, "order_id": 2}, "submitted"),
    ("execute", {"success": True}, "unknown"),
])
def test_explicit_outcome_requires_actual_result(action, execution, state):
    s = record(action, execution)
    assert s["current_execution"]["state"] == state
    assert validate_record(s)["verified"]


def test_mismatches_and_future_candles_are_detected():
    s = record()
    s["decision_analysis"]["decision_ref"]["decision_id"] = "old"
    assert "decision_analysis_reference_mismatch" in validate_record(s)["errors"]
    s = record()
    s["decision_snapshot"]["as_of_utc"] = "2026-11-26T12:14:59Z"
    assert "M5_not_closed_at_cutoff" in validate_record(s)["errors"]
    assert "snapshot_hash_mismatch" in validate_record(s)["errors"]
    s = record()
    s["current_execution"]["state"] = "filled"
    assert "outcome_mismatch" in validate_record(s)["errors"]
    s = record()
    s['indicator_evidence'] = {'bar_utc': '2026-11-26T12:15:00Z', 'bar_closed_at_evaluation': False}
    assert 'indicator_candle_mismatch' in validate_record(s)['errors']


def test_prices_change_manifest_even_with_identical_candle_timestamps():
    s = record()
    f = pd.DataFrame({"time": ["2026-11-26T12:10:00Z"], "close": [10.]})
    a = candle_manifest(f, "M5")
    f.loc[0, "close"] = 11.
    assert a["candles_sha256"] != candle_manifest(f, "M5")["candles_sha256"]


def test_vectorized_manifest_preserves_original_canonical_hash():
    from atlas_ai.decision_record import digest
    f = pd.DataFrame({'time': ['2026-11-26T12:00:00Z', '2026-11-26T12:05:00Z'],
                      'open': [10, 11], 'high': [11, 12], 'low': [9, 10], 'close': [10.5, 11.5],
                      'tick_volume': [1, 2]})
    times = pd.to_datetime(f.time, utc=True)
    fields = ['open', 'high', 'low', 'close', 'tick_volume']
    original = [{'open_utc': at.isoformat(), **{k: float(f.iloc[i][k]) for k in fields}}
                for i, at in enumerate(times)]
    assert candle_manifest(f, 'M5')['candles_sha256'] == digest(original)


def test_legacy_records_are_not_relabelled_as_verified():
    assert not validate_record({"action": "blocked"})["verified"]


def test_cycle_exception_cannot_inherit_a_previous_fill_or_analysis():
    s = record()
    failure = cycle_failure(s['decision_snapshot'], symbol='XAUUSD', timeframe='M5', error='feed unavailable')
    assert failure['action']=='degraded'
    assert failure['current_execution']['state']=='unknown'
    assert failure['current_execution']['request_id'] is None
    assert 'execution' not in failure
    assert validate_record(failure)['verified']


def test_status_apis_preserve_scan_outcome_and_separate_older_fill(tmp_path, monkeypatch):
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    from atlas_ai.ui_server import create_ui_app
    import atlas_ai.ui_server as server
    store = KnowledgeStore(str(tmp_path))
    s = record()
    store.save_status(s)
    old = {"last_execution_truth": {"request_id": "old-request", "ok": True}, "session_control": {}}
    monkeypatch.setattr(server, "announce_ui_ready_once", lambda *_a, **_kw: True)
    monkeypatch.setattr(server, "_load_automation_payload", lambda *_a: old)
    app = create_ui_app(store)
    client = app.test_client()
    for endpoint in ("/api/status", "/api/status/compact", "/api/status/full"):
        p = client.get(endpoint).get_json()
        assert p["decision_id"] == "scan-1"
        assert p["current_execution"] == s["current_execution"]
        assert p["decision_consistency"]["verified"]
        assert p["decision_trace"]["decision_ref"] == s["decision_ref"]
        assert p["timing_discipline"]["decision_ref"] == s["decision_ref"]
        assert p["context_snapshot"]["decision_ref"] == s["decision_ref"]
        if endpoint != "/api/status/compact":
            assert p.get("execution", {}).get("request_id") != "old-request"
            assert p["execution_truth"]["state"] == "not_submitted"


def test_event_api_compaction_keeps_identity_candles_and_outcome():
    from atlas_ai.ui_server import _compact_event_for_ui
    s = record()
    event = _compact_event_for_ui({'type': 'risk', 'message': s['message'], 'meta': s})
    for name in ('decision_id', 'decision_ref', 'current_execution', 'decision_snapshot'):
        assert event['meta'][name] == s[name]


def test_browser_rejects_cached_and_mismatched_decisions():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required")
    source = Path("atlas_ai/ui/app.js").read_text(encoding="utf-8")
    helper = source[source.index("function consistentDecisionView("):source.index("function decisionExecutionDisplay(")]
    s = record()
    cached = deepcopy(s)
    cached["decision_ref"]["decision_id"] = "older"
    cached["chart_features"] = {"stale": True}
    s["decision_analysis"]["decision_ref"]["decision_id"] = "unrelated"
    result = subprocess.run([node, "-"], input=helper + "\nconsole.log(JSON.stringify(consistentDecisionView(" +
                            json.dumps(s) + "," + json.dumps(cached) + ")));", text=True, capture_output=True,
                            encoding="utf-8", check=True, timeout=15)
    view = json.loads(result.stdout)
    assert "decision_analysis" not in view and "chart_features" not in view
    assert "decision_analysis" in view["consistency_warnings"]
