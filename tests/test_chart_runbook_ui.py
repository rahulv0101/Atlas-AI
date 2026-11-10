import json
from pathlib import Path
import shutil
import subprocess

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")


def run(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required")
    return json.loads(subprocess.run([node, "-"], input=script, text=True,
        capture_output=True, check=True, timeout=15).stdout)


@pytest.mark.parametrize("used,minutes,expected", [(0, 0, "OK"), (8, 30, "BLOCKED"), (None, -1, "REVIEW")])
def test_runbook_limits_and_zero_minute_warning(used, minutes, expected):
    helper = SOURCE[SOURCE.index("function renderPilotRunbook("):SOURCE.index("async function refreshOperatorPanels()")]
    execution = {"tiny_live_pilot_trade_count": used, "tiny_live_pilot_daily_loss_used": 0,
        "tiny_live_pilot_consecutive_losses": 0, "session_control": {"minutes_to_session_close": minutes},
        "tiny_live_pilot": {"max_trades_per_day": 8, "daily_loss_cap": .6, "max_consecutive_losses": 8}}
    script = '''const rows={};function mergedExecutionState(s,r){return r.execution;}
function compactText(v,f){return v == null || v === '' ? f : String(v);}
function renderRunbookRows(k,v){rows[k]=v;}function renderRunbookStopRows(){}
''' + helper + "\nrenderPilotRunbook({}," + json.dumps({"execution": execution}) + ");process.stdout.write(JSON.stringify(rows));"
    rows = run(script)
    during = rows["op-runbook-during"]
    assert during[0]["status"] == expected
    assert during[1]["status"] == "OK" and "0.600%" in during[1]["text"]
    assert during[5]["status"] == ("REVIEW" if minutes == 0 else "OK")
    assert rows["op-runbook-pre"][2]["status"] == "WAITING"


def test_empty_chart_explains_missing_data_instead_of_blank_grid():
    helper = SOURCE[SOURCE.index("function drawGoldChart()"):SOURCE.index("function renderStatus(")]
    script = '''const text=[];const chart={width:560,height:220};const priceHistory=[];
const chartCtx={clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},fillText(t){text.push(t);}};
''' + helper + "\ndrawGoldChart();process.stdout.write(JSON.stringify(text));"
    assert run(script) == ["No broker chart data available"]
