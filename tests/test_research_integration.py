from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from atlas_ai.atomic_files import atomic_json
from atlas_ai.brain.answer_engine import AnswerEngine
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.research_status import load_research_progress
from atlas_ai.ui.ask_atlas import AskAtlasService
from tools.learn_candidate_ranker import save_signed


@pytest.fixture
def reports(tmp_path):
    now = datetime.now(timezone.utc)
    atomic_json(tmp_path / "acceptance_plan.status.json", {
        "checked_at": now.isoformat(), "state": "collecting", "first_stage_cases": 2,
        "validation_stage_cases": 0, "required_per_stage": 30, "natural_cycle_verified": False,
        "execution_costs": {"state": "diagnostic_only", "measured_fill_observations": 0, "cost_calibration_ready": False}})
    atomic_json(tmp_path / "activity_review/status.json", {"checked_at": now.isoformat(), "state": "observing",
        "deadline": (now+timedelta(days=7)).isoformat(), "directional_publications": 6,
        "analysis_eligible_publications": 0, "verified_natural_cycles_in_window": 0})
    directory = tmp_path / "learning/test"; directory.mkdir(parents=True)
    atomic_json(tmp_path / "learned_ranker_active.json", {"run_dir": str(directory)})
    save_signed(directory, "manifest", {"broker_eligible": False, "auto_promotion": False, "frozen_at": now.isoformat()})
    save_signed(directory, "model", {"broker_eligible": False, "state": "fitted_research_only", "rows": 1978, "dates": 17})
    save_signed(directory, "historical_report", {"historical_review_passed": False,
        "validation_previously_inspected": {"learner": {"trades": 0}, "baseline": {"trades": 42, "net_r": -14.58}}})
    atomic_json(directory / "forward_status.json", {"state": "collecting_frozen_model_paper", "checked_at": now.isoformat(),
        "learner_paper_trades": 0, "baseline_paper_trades": 3, "first_stage": {"learner": {"trades": 0}},
        "validation_stage": {"learner": {"trades": 0}}})
    return tmp_path, directory, now


def test_shared_summary_keeps_evidence_streams_and_authority_separate(reports):
    folder, _, now = reports
    before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    result = load_research_progress(folder, now=now)
    assert result["acceptance"]["first_stage_cases"] == 2
    assert result["learning"]["first_stage_cases"] == 0
    assert result["learning"]["historical_review_passed"] is False
    assert not result["learning"]["stale"] and not result["profitability_proven"] and not result["broker_eligible"]
    assert result["costs"]["measured_fill_observations"] == 0
    assert before == {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_stale_reports_and_corrupt_models_cannot_look_current(reports):
    folder, directory, now = reports
    result = load_research_progress(folder, now=now+timedelta(hours=2))
    assert result["learning"]["stale"] and result["acceptance"]["stale"] and result["activity"]["stale"]
    (directory / "model.json").write_text("{}")
    result = load_research_progress(folder, now=now)
    assert result["learning"]["state"] == "integrity_review_required"
    assert "training_rows" not in result["learning"]


def test_missing_partial_and_external_reports_fail_visibly(tmp_path):
    result = load_research_progress(tmp_path)
    assert result["learning"]["state"] == "unavailable" and result["errors"]
    atomic_json(tmp_path / "learned_ranker_active.json", {"run_dir": str(tmp_path.parent)})
    assert load_research_progress(tmp_path)["learning"]["state"] == "integrity_review_required"
    (tmp_path / "acceptance_plan.status.json").write_text("{partial")
    assert load_research_progress(tmp_path)["acceptance"]["stale"]


def test_boot_inspection_failure_does_not_break_other_research_reports(reports, monkeypatch):
    folder, _, now = reports
    monkeypatch.setattr("atlas_ai.research_status.verify_startup", Mock(side_effect=OSError("boot information unavailable")))
    result = load_research_progress(folder, now=now)
    assert result["startup"]["verified"] is False
    assert result["learning"]["training_rows"] == 1978


def test_brain_uses_research_intent_evidence_plan_and_relevance(reports):
    folder, _, now = reports
    context = {"status": {"action": "hold", "message": "UNRELATED_TRADE_BLOCKER"},
               "runtime": {"research_progress": load_research_progress(folder, now=now)}}
    engine = AnswerEngine()
    typed = engine.answer("How is the learning experiment doing?", context)
    voice = engine.answer("How is the learning experiment doing?", context, mode="voice")
    assert typed.selected_intent == voice.selected_intent == "research_progress"
    assert typed.selected_plan == "research_progress_plan" and typed.relevance_passed and voice.relevance_passed
    assert "1978" in typed.text and "did not pass historical" in typed.text
    assert "no trading authority" in voice.text and len(voice.text) < len(typed.text)
    assert "UNRELATED_TRADE_BLOCKER" not in typed.text
    startup = engine.answer("Has startup verification passed?", context)
    assert "cannot confirm" in startup.text and startup.relevance_passed
    activity = engine.answer("How is the activity review?", context)
    assert "Verified natural cycles: 0" in activity.text and activity.relevance_passed
    mechanism = engine.answer("How does the learning model work?", context)
    assert "cost-adjusted" in mechanism.text and "cannot rewrite strategies" in mechanism.text
    reason = engine.answer("Why did the learning experiment not qualify?", context)
    assert "zero trades cannot qualify" in reason.text
    capabilities = engine.answer("What can you do?", context)
    assert capabilities.selected_intent == "capabilities" and capabilities.relevance_passed


def test_typed_and_voice_service_load_the_same_shared_view(reports):
    folder, _, _ = reports
    source = SimpleNamespace(store=KnowledgeStore(str(folder)), load_status=lambda: {"action": "hold"},
        load_runtime_flags=lambda: {}, load_events=lambda **kw: [], load_learning_state=lambda: {})
    service = AskAtlasService(source)
    service.decision_journal.append = Mock(side_effect=AssertionError("Research questions are not trading decisions"))
    service.decision_reviewer.review = Mock(side_effect=AssertionError("Research questions cannot train strategy preferences"))
    typed = service.answer("How is the learning experiment doing?")
    voice = service.answer("How is the learning experiment doing?", mode="voice")
    assert "1978" in typed["result"]
    assert "no trading authority" in voice["result"]
    assert typed["handled_as"] != "command" and voice["handled_as"] != "command"


def test_dashboard_and_runtime_endpoints_expose_same_view(reports, monkeypatch):
    from atlas_ai.ui_server import create_ui_app
    folder, _, _ = reports
    monkeypatch.setattr("atlas_ai.ui_server.announce_ui_ready_once", lambda *a, **kw: True)
    client = create_ui_app(KnowledgeStore(str(folder))).test_client()
    for url in ("/api/status/compact", "/api/status", "/api/runtime"):
        response = client.get(url)
        assert response.status_code == 200
        summary = response.get_json()["research_progress"]
        assert summary["learning"]["training_rows"] == 1978
        assert not summary["broker_eligible"] and summary["acceptance"]["first_stage_cases"] == 2


def test_real_dashboard_renderer_explains_failed_and_stale_evidence(reports):
    node = shutil.which("node")
    if not node: pytest.skip("Node required for frontend execution")
    folder, _, now = reports
    path = Path(__file__).resolve().parents[1] / "atlas_ai/ui/app.js"
    source = path.read_text(encoding="utf-8")
    renderer = source[source.index("function renderResearchProgress("):source.index("function renderLearningLoop(")]
    payload = {"research_progress": load_research_progress(folder, now=now)}
    script = "const output={}; function setText(id,text){output[id]=text;}\n" + renderer
    script += "\nrenderResearchProgress(" + json.dumps(payload) + "); console.log(JSON.stringify(output));"
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    rendered = json.loads(result.stdout)
    assert "historical screening not passed" in rendered["research-learning"]
    assert "2/30 + 0/30" in rendered["research-paper"]
    assert "Not yet verified" == rendered["research-cycle"]
    script += "\nrenderResearchProgress({});console.log(JSON.stringify(output));"
    rendered = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout.splitlines()[-1])
    assert "missing or stale" in rendered["research-state"] and "unavailable" in rendered["research-cycle"]
