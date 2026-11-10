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
    renderer = source[source.index("function entryWaitingSummary("):source.index("function renderVisualChartRead(")]
    payload = {"action": action, "message": display["detail"] if display else "Current decision", "execution_readiness": {"display": display} if display else {}}
    if action == "blocked" and display and display["label"] == "WAITING":
        payload["timing_discipline"] = {"hard_block": True, "missing": ["tradable_location", "strong_or_turning_m1_momentum", "visual_confirmation"]}
    script = '''
const values = {};
const document = {getElementById() { return null; }};
function compactText(value, fallback) { return value === undefined || value === null || value === "" ? fallback : String(value); }
function mergedExecutionState() { return {automation_enabled:true,session_control:{session_active:true}}; }
function setText(key,value) { values[key] = value; }
function setCommandTileState() {}
function renderReadinessLanes() {}
function titleCase(value) { return value; }
''' + source[source.index("function isActionableTrade("):source.index("function stableStringify(")] + renderer + "\nrenderCommandStrip(" + json.dumps(payload) + ", {});\nprocess.stdout.write(JSON.stringify(values));"
    completed = subprocess.run([node, "-"], input=script, text=True, encoding="utf-8", capture_output=True, timeout=15, check=True)
    values = json.loads(completed.stdout)
    assert values["cmd-readiness"] == expected
    if action == "blocked" and display and display["label"] == "WAITING":
        assert values["cmd-readiness-detail"] == "Waiting for a clear entry location, M1 momentum, chart confirmation."
        assert values["cmd-blocker"] == "Entry timing"
    elif action == "hold" and display:
        assert values["cmd-readiness-detail"] == "No buy or sell candidate is available in this cycle."
        assert values["cmd-blocker"] == "Scanning for a setup"
    elif display:
        assert values["cmd-readiness-detail"] == display["detail"]


def test_operator_overview_shows_demo_goal_and_evidence_without_claiming_profit():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the dashboard renderer")
    source = (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")
    renderer = source[source.index("function renderOperatorOverview("):source.index("function renderCommandStrip(")]
    payload = {"daily_profit_objective": {"enabled": True, "target_zar": 1000, "equity_change_zar": 250, "reached": False},
               "strategy_evidence": {"available": True, "strict_strategy_positions": 0, "closed_positions": 158}}
    script = '''
const values = {};
const elements = {};
const document = {getElementById(id) { return elements[id] ||= {style: {}, setAttribute(key,value) { this[key] = value; }}; }};
function setText(id,value) { values[id] = value; }
''' + renderer + "\nrenderOperatorOverview(" + json.dumps(payload) + ");\nprocess.stdout.write(JSON.stringify({values,elements}));"
    completed = subprocess.run([node, "-"], input=script, text=True, encoding="utf-8", capture_output=True, timeout=15, check=True)
    result = json.loads(completed.stdout)
    assert result["elements"]["cmd-goal-value"]["textContent"] == "R250 / R1 000" or result["elements"]["cmd-goal-value"]["textContent"] == "R250 / R1,000"
    assert result["elements"]["cmd-goal-fill"]["style"]["width"] == "25%"
    assert result["values"]["cmd-evidence-count"] == "0 verified"
    assert "decision links" in result["values"]["cmd-evidence-detail"]


@pytest.mark.parametrize("age,in_flight,request_age,failures,expected", [
    (3, False, 0, 0, "Connected - checked 3s ago"),
    (31, False, 0, 0, "Status checks delayed - retrying"),
    (3, True, 16, 0, "Status checks delayed - retrying"),
    (3, False, 0, 1, "Connection lost - retrying automatically"),
])
def test_ui_heartbeat_does_not_call_old_status_connected(age, in_flight, request_age, failures, expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the dashboard heartbeat")
    source = (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")
    helper = source[source.index("function updateUIConnection()"):source.index("async function refresh()")]
    script = "const Date = {now: () => 100000}; let output; function setText(id,text) {output=text;}\n"
    script += f"const lastSuccessfulRefreshAt={100000-age*1000}; const refreshInFlight={str(in_flight).lower()}; const refreshStartedAt={100000-request_age*1000}; const refreshFailureCount={failures};\n"
    script += helper + "\nupdateUIConnection(); process.stdout.write(output);"
    result = subprocess.run([node, "-"], input=script, text=True, capture_output=True, timeout=15, check=True)
    assert result.stdout == expected


@pytest.mark.parametrize("side,confidence,expected", [
    ("buy", 0.48, "Candidates under review"),
    ("sell", 0.35, "Candidates under review"),
    ("flat", 0.0, "Scanning for a setup"),
])
def test_waiting_explanation_preserves_raw_candidate_evidence(side, confidence, expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the dashboard renderer")
    source = (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")
    helper = source[source.index("function isActionableTrade("):source.index("function stableStringify(")]
    helper += source[source.index("function entryWaitingSummary("):source.index("function renderOperatorOverview(")]
    payload = {"action": "hold", "message": "No directional trade signal selected.", "signals": [{"side": side, "confidence": confidence}]}
    script = helper + "\nprocess.stdout.write(entryWaitingSummary(" + json.dumps(payload) + ").headline);"
    result = subprocess.run([node, "-"], input=script, text=True, capture_output=True, timeout=15, check=True)
    assert result.stdout == expected


def test_cutoff_summary_does_not_claim_scanning_or_disconnection():
    node=shutil.which("node")
    if not node:pytest.skip("Node required")
    source=(Path(__file__).resolve().parents[1]/"atlas_ai/ui/app.js").read_text(encoding="utf-8")
    helper=source[source.index("function entryWaitingSummary("):source.index("function renderOperatorOverview(")]
    payload={"action":"hold","intraday_exit":{"entries_blocked":True,"flat_verified":True}}
    script=helper+"\nprocess.stdout.write(JSON.stringify(entryWaitingSummary("+json.dumps(payload)+")));"
    result=json.loads(subprocess.run([node,"-"],input=script,text=True,capture_output=True,check=True).stdout)
    assert result["headline"]=="Session cutoff" and "paused" in result["detail"]
