"""Run the actual command-strip renderer against API readiness decisions."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("action,display,expected", [
    ("hold", {"state": "waiting", "label": "WAITING", "detail": "No directional trade signal selected."}, "WAITING"),
    ("blocked", {"state": "waiting", "label": "WAITING", "detail": "Waiting for clean entry timing."}, "WAITING"),
    ("buy", {"state": "blocked", "label": "BLOCKED", "detail": "Broker not ready."}, "BLOCKED"),
    ("buy", None, "REVIEW"),
])
def test_dashboard_uses_api_readiness_instead_of_inventing_ready_from_side(action, display, expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the dashboard renderer")
    source = (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")
    renderer = source[source.index("function renderCommandStrip("):source.index("function renderVisualChartRead(")]
    payload = {"action": action, "message": "Current decision", "execution_readiness": {"display": display} if display else {}}
    script = '''
const values = {};
function compactText(value, fallback) { return value === undefined || value === null || value === "" ? fallback : String(value); }
function mergedExecutionState() { return {automation_enabled:true,session_control:{session_active:true}}; }
function setText(key,value) { values[key] = value; }
function setCommandTileState() {}
function renderReadinessLanes() {}
function titleCase(value) { return value; }
''' + renderer + "\nrenderCommandStrip(" + json.dumps(payload) + ", {});\nprocess.stdout.write(JSON.stringify(values));"
    completed = subprocess.run([node, "-"], input=script, text=True, capture_output=True, timeout=15, check=True)
    values = json.loads(completed.stdout)
    assert values["cmd-readiness"] == expected
    if display:
        assert values["cmd-readiness-detail"] == display["detail"]
