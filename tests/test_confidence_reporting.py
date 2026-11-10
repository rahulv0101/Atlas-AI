import json
from pathlib import Path
import shutil
import subprocess

import pytest

from atlas_ai.trader import AtlasTrader


@pytest.mark.parametrize("status,label,text", [
    ({"chosen": {"side": "flat", "confidence": .45}, "min_confidence_threshold": .44,
      "best_actionable_candidate": {"side": "buy", "confidence": .89}}, "Candidate score", "No buy/sell signal"),
    ({"chosen": {"side": "buy", "confidence": .89}}, "Candidate score", "89/100"),
    ({"chosen": {"side": "sell", "confidence": .55}, "atlas_conviction": {"score": 59},
      "min_confidence_threshold": .44}, "Trade conviction", "55/100 · min 44"),
])
def test_confidence_distinguishes_signal_and_scoring_stage(status, label, text):
    binary = shutil.which("node")
    if not binary:
        pytest.skip("Node required")
    source = (Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js").read_text(encoding="utf-8")
    helper = source[source.index("function isActionableTrade("):source.index("function stableStringify(")]
    helper += source[source.index("function renderTradeConfidence("):source.index("function drawGoldChart(")]
    script = '''const elements={};const document={getElementById(id){return elements[id] ||= {};}};
function setText(id,text){document.getElementById(id).textContent=text;}
''' + helper + "\nrenderTradeConfidence(" + json.dumps(status) + ");process.stdout.write(JSON.stringify(elements));"
    result = json.loads(subprocess.run([binary, "-"], input=script, text=True, encoding="utf-8",
        capture_output=True, check=True, timeout=15).stdout)
    assert result["stat-confidence-label"]["textContent"] == label
    assert result["stat-confidence"]["textContent"] == text


def test_journal_preserves_confidence_provenance_without_large_payloads():
    status = {"chosen": {"side": "sell", "confidence": .55, "signal_confidence_seed": .8},
        "atlas_conviction": {"score": 59, "adjustments": []},
        "confidence_diagnostics": {"confidence_gap": .11}, "min_confidence_threshold": .44}
    result = AtlasTrader.__new__(AtlasTrader)._compact_runtime_event_meta(status, "risk")
    assert result["chosen"]["signal_confidence_seed"] == .8
    assert result["atlas_conviction"] == status["atlas_conviction"]
    assert result["confidence_diagnostics"] == status["confidence_diagnostics"]
    assert result["min_confidence_threshold"] == .44
