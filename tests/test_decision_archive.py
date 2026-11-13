from datetime import datetime,timedelta,timezone
import gzip
import json
from pathlib import Path

import pytest

from atlas_ai.learning.observation_checkpoint import observation_lock
from atlas_ai.testing.decision_archive import capture,index_rows,sanitize,verify


def now():return datetime(2026,11,11,18,tzinfo=timezone.utc)


@pytest.fixture
def publication(tmp_path):
    status={"symbol":"XAUUSD","timeframe":"M1","updated_at":now().isoformat(),"action":"hold",
        "chosen":{"side":"flat","strategy":"ema_crossover","confidence":.3},
        "message":"key=not-a-secret https://example.invalid/?key=TOPSECRETKEY",
        "visual_chart_read":{"source":"screenshot_plus_chart_features","captured_at":now().isoformat()},
        "context_snapshot":{"dxy_alignment":"unknown"},"password":"TOPSECRETKEY",
        "health":{"broker":{"account_login":123,"api_key":"TOPSECRETKEY"}}}
    (tmp_path/"status.json").write_text(json.dumps(status))
    (tmp_path/"learning_state.json").write_text(json.dumps({"state":{"allocator":{"ema_crossover":{"wins":1}},
        "model_registry":{"api_key":"TOPSECRETKEY","score":float("nan")},"unrelated_chat":"private conversation"}}))
    (tmp_path/"runtime_flags.json").write_text(json.dumps({"execute_trades":True,"hfm_password":"TOPSECRETKEY"}))
    (tmp_path/"automation_state.json").write_text(json.dumps({"payload":{"sleep_mode_active":False,"hfm_login":123}}))
    return tmp_path,status


def record(folder,index=0):
    row=index_rows(folder/"replay_evidence")[index]
    return json.loads(gzip.decompress((folder/"replay_evidence/records"/(row["record_id"]+".json.gz")).read_bytes()))


def test_captures_published_evidence_without_claiming_parity_or_changing_source(publication):
    folder,_=publication;original={p.name:p.read_bytes() for p in folder.glob("*.json")}
    result=capture(folder,now(),secrets=("TOPSECRETKEY",))
    assert result["records"]==1 and result["state"]=="publication_captured"
    captured=record(folder)
    assert captured["publication_fresh"] and captured["publication_time_verified"]
    assert not captured["replay_ready"] and not captured["broker_eligible"]
    assert captured["orders_sent"]==0 and captured["capture_kind"]=="post_publication_observer"
    assert captured["publication"]["context_snapshot"]["dxy_alignment"]=="unknown"
    assert {p.name:p.read_bytes() for p in folder.glob("*.json")}==original
    assert verify(folder/"replay_evidence")["valid"]


def test_secrets_and_unrelated_conversation_are_not_archived(publication):
    folder,_=publication;capture(folder,now(),secrets=("TOPSECRETKEY",))
    text="\n".join(gzip.decompress(p.read_bytes()).decode() for p in (folder/"replay_evidence").rglob("*.gz"))
    assert "TOPSECRETKEY" not in text and "private conversation" not in text
    assert "nonfinite_observation" in text and "NaN" not in text
    assert sanitize({"hfm_login":123,"account_login":123,"authorization":"secret","safe":1})=={"safe":1}


def test_same_publication_is_not_an_additional_decision_and_states_are_deduplicated(publication):
    folder,status=publication
    capture(folder,now());again=capture(folder,now()+timedelta(seconds=60))
    assert again["records"]==1 and again["state"]=="same_publication_already_captured"
    before=list((folder/"replay_evidence/state_blobs").glob("*.gz"))
    status["updated_at"]=(now()+timedelta(minutes=1)).isoformat()
    (folder/"status.json").write_text(json.dumps(status))
    assert capture(folder,now()+timedelta(minutes=1))["records"]==2
    assert len(list((folder/"replay_evidence/state_blobs").glob("*.gz")))==len(before)
    assert record(folder,0)["saved_state"]==record(folder,1)["saved_state"]


def test_capsule_and_index_corruption_are_detected_without_reset(publication):
    folder,status=publication;capture(folder,now())
    rows=index_rows(folder/"replay_evidence")
    blob=folder/"replay_evidence/records"/(rows[0]["record_id"]+".json.gz")
    blob.write_bytes(blob.read_bytes()+b"changed")
    assert verify(folder/"replay_evidence")["valid"] is False
    status["updated_at"]=(now()+timedelta(minutes=1)).isoformat()
    (folder/"status.json").write_text(json.dumps(status))
    with pytest.raises(ValueError,match="archive_blob_changed"):capture(folder,now())
    assert len(index_rows(folder/"replay_evidence"))==1


def test_budget_never_deletes_evidence_or_claims_success(publication):
    folder,status=publication;capture(folder,now())
    status["updated_at"]=(now()+timedelta(minutes=1)).isoformat()
    (folder/"status.json").write_text(json.dumps(status))
    assert capture(folder,now(),budget_bytes=1)["state"]=="storage_budget_reached_no_deletion"
    assert verify(folder/"replay_evidence")["records"]==1


@pytest.mark.parametrize("stamp",["2026-11-11T18:00:00","2026-11-12T18:00:00+00:00"])
def test_naive_or_future_publications_cannot_be_treated_as_fresh(publication,stamp):
    folder,status=publication;status["updated_at"]=stamp
    (folder/"status.json").write_text(json.dumps(status));capture(folder,now())
    assert not record(folder)["publication_fresh"] and not record(folder)["replay_ready"]


def test_verification_reports_busy_and_missing_archives(publication,tmp_path):
    folder,_=publication;assert verify(folder/"missing")["state"]=="archive_missing"
    capture(folder,now())
    with observation_lock(folder/"replay_evidence/archive.lock"):
        assert verify(folder/"replay_evidence")["state"]=="writer_busy_retry"


def test_verifier_cli_cannot_report_success_for_corrupt_evidence(publication,capsys):
    from tools.verify_replay_evidence import main
    folder,_=publication;capture(folder,now())
    assert main(["--storage",str(folder)])==0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    row=index_rows(folder/"replay_evidence")[0]
    (folder/"replay_evidence/records"/(row["record_id"]+".json.gz")).write_bytes(b"changed")
    assert main(["--storage",str(folder)])==1
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_referenced_pixels_are_preserved_without_claiming_decision_binding(publication):
    folder,status=publication;image=folder/"chart.png";image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    status["visual_chart_read"]["image"]={"path":str(image)}
    (folder/"status.json").write_text(json.dumps(status));capture(folder,now())
    captured=record(folder)["image_asset"]
    assert captured["state"]=="pixels_captured_as_observed"
    assert not captured["decision_image_identity_verified"]
    image.write_bytes(b"overwritten later")
    assert verify(folder/"replay_evidence")["valid"]


def test_arbitrary_outside_files_are_not_copied(publication,tmp_path):
    folder,status=publication
    status["visual_chart_read"]["image"]={"path":str(folder.parent/"outside.png")}
    (folder/"status.json").write_text(json.dumps(status));capture(folder,now())
    assert record(folder)["image_asset"]["state"]=="pixel_reference_unavailable_or_outside_storage"
    assert not (folder/"replay_evidence/assets").exists()


def test_changed_archived_pixels_block_capture_instead_of_becoming_missing(publication):
    folder,status=publication;image=folder/"chart.png";image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    status["visual_chart_read"]["image"]={"path":str(image)}
    (folder/"status.json").write_text(json.dumps(status));capture(folder,now())
    next((folder/"replay_evidence/assets").iterdir()).write_bytes(b"changed")
    status["updated_at"]=(now()+timedelta(minutes=1)).isoformat()
    (folder/"status.json").write_text(json.dumps(status))
    with pytest.raises(RuntimeError,match="archived_pixels_changed"):capture(folder,now())
    assert not verify(folder/"replay_evidence")["valid"]


def test_penalty_inputs_are_preserved_for_future_audits_with_redaction(publication):
    folder,status=publication
    status["signal_generation"]={"context":{"entry_wickiness":.6},"candidates":[
        {"strategy":"ema_crossover","before_filters":{"confidence":.5},"after_filters":{"confidence":.43}}],
        "api_key":"TOPSECRETKEY"}
    (folder/"status.json").write_text(json.dumps(status))
    path=folder/"learning_state.json";state=json.loads(path.read_text())
    state["state"]["historical_loss_analysis"]={"source":"historical_backtest","password":"TOPSECRETKEY"}
    path.write_text(json.dumps(state));capture(folder,now(),secrets=("TOPSECRETKEY",))
    archived=record(folder)
    assert archived["publication"]["signal_generation"]["context"]["entry_wickiness"]==.6
    assert "api_key" not in archived["publication"]["signal_generation"]
    ref=archived["saved_state"]["learning_state.json"]
    saved=json.loads(gzip.decompress((folder/"replay_evidence/state_blobs"/(ref["blob_id"]+".json.gz")).read_bytes()))
    assert saved["historical_loss_analysis"]=={"source":"historical_backtest"}
