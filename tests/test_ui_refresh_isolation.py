import json
from pathlib import Path
import shutil
import subprocess

import pytest


def source():
    return (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")


def node(script):
    binary = shutil.which("node")
    if not binary:
        pytest.skip("Node required")
    return json.loads(subprocess.run([binary, "-"], input=script, text=True,
        capture_output=True, check=True, timeout=10).stdout)


@pytest.mark.parametrize("view,first_done", [("command", True), ("diagnostics", False)])
def test_hidden_or_starting_diagnostics_do_not_send_operator_questions(view, first_done):
    text = source()
    helper = text[text.index("async function refreshOperatorPanels()"):text.index("function setDashboardView(")]
    script = "let operatorRefreshInFlight=false;const document={hidden:false};"
    script += "const dashboardView=" + json.dumps(view) + ";const firstRefreshDone=" + json.dumps(first_done) + ";"
    script += helper + "\nrefreshOperatorPanels().then(()=>process.stdout.write(JSON.stringify({inFlight:operatorRefreshInFlight})));"
    assert node(script) == {"inFlight": False}


def test_pending_optional_panels_do_not_hold_core_refresh_or_mark_it_offline():
    text = source()
    core = text[text.index("async function refreshAuxiliaryPanels()"):text.index("function startPolling()")]
    script = """
let refreshInFlight=false,refreshStartedAt=0,firstRefreshDone=false,lastAuxRefreshAt=0;
let refreshFailureCount=0,lastStatusSignature='',lastSignalsSignature='',lastLearningSignature='';
let lastRichStatus={},lastSuccessfulRefreshAt=0,auxiliaryRefreshInFlight=false;
const dashboardView='command', document={hidden:false,getElementById:()=>null};
const optional=new Promise(()=>{});
const loadStatus=async()=>({updated_at:'now',action:'hold'}),loadRuntime=async()=>({});
const loadEvents=()=>optional,loadLearningInsights=()=>optional;
const getSettledValue=(r,f)=>r.status==='fulfilled'?r.value:f;
const dismissStartup=()=>{},renderStatus=()=>{},renderEvents=()=>{},renderLearningInsights=()=>{};
const renderModeToggle=()=>{},renderGeminiInfluenceToggle=()=>{},renderCommandStrip=()=>{};
const renderOperatorSnapshot=()=>{},renderOperatorLivePilotReview=()=>{},renderPilotRunbook=()=>{};
const renderSelfImprovementPanel=()=>{},renderSelfImprovementReviewPacket=()=>{},renderAICorePanel=()=>{};
const operatorPanelCache={},selfImprovementCache={},aiCoreCache={};
const updateUIConnection=()=>{},setText=()=>{};
console.debug=()=>{};
"""
    script += core + """
refresh().then(()=>process.stdout.write(JSON.stringify({firstRefreshDone,
  coreReturned:!refreshInFlight,connected:lastSuccessfulRefreshAt>0,
  failures:refreshFailureCount,optionalStillPending:auxiliaryRefreshInFlight})));
"""
    assert node(script) == {"firstRefreshDone": True, "coreReturned": True,
        "connected": True, "failures": 0, "optionalStillPending": True}
