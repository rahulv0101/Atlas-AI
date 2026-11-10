from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from atlas_ai.learning.cost_research_status import load_cost_research_status
from tools.observe_cost_research import public_summary


def test_cost_research_adapter_rejects_invalid_boundary_and_corrupt_state(tmp_path):
    assert load_cost_research_status(tmp_path)["state"]=="not_started"
    p=tmp_path/"cost_research/latest.json";p.parent.mkdir()
    p.write_text(json.dumps({"state":"observing_frozen_rules","broker_eligible":True,"orders_sent":0}))
    assert load_cost_research_status(tmp_path)["state"]=="summary_unavailable"
    p.write_text("{")
    assert load_cost_research_status(tmp_path)["state"]=="summary_unavailable"


def test_public_summary_cannot_claim_broker_trade_proof(tmp_path):
    (tmp_path/"selection.json").write_text(json.dumps({"frozen_at":"2026-11-10T11:00:00Z","qualified_training_lanes":0}))
    result=public_summary(tmp_path,{"state":"observing_frozen_rules","lanes":{"a":{"paper_outcomes":[{},{}]}}})
    assert result["paper_outcomes"]==2 and result["comparisons"]==1
    assert result["orders_sent"]==0 and result["broker_eligible"] is False
    assert "verified_natural_cycles" not in result
    assert result["state"]=="waiting_for_fresh_broker_bars" and result["data_fresh"] is False


@pytest.mark.parametrize("age,state,expected",[(5,"observing_frozen_rules","paper observation active"),
    (500,"observing_frozen_rules","heartbeat is stale"),(0,"observation_error","unavailable or stopped"),
    (0,"observation_window_completed","window completed"),
    (0,"waiting_for_fresh_broker_bars","waiting for fresh closed broker bars")])
def test_research_ui_shows_stale_and_failed_observation(age,state,expected):
    node=shutil.which("node")
    if not node:pytest.skip("Node required")
    source=(Path(__file__).resolve().parents[1]/"atlas_ai/ui/app.js").read_text(encoding="utf-8")
    helper=source[source.index("function renderCostResearch("):source.index("function renderTradeConfidence(")]
    status={"cost_research":{"state":state,"checked_at":(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),
        "comparisons":18,"paper_outcomes":2,"training_qualified":0}}
    script="let text='';function setText(k,v){text=v;}"+helper+"\nrenderCostResearch("+json.dumps(status)+");process.stdout.write(JSON.stringify(text));"
    result=json.loads(subprocess.run([node,"-"],input=script,text=True,encoding="utf-8",capture_output=True,check=True,timeout=15).stdout)
    assert expected in result and "No broker activation" in result or expected in result and "no broker activation" in result
