import json
import sys

import pytest

from tools import diagnose_trade_pipeline as diagnostic


def test_report_counts_trader_decisions_without_double_counting_samples(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    archive = storage / "archive"
    archive.mkdir(parents=True)
    (storage / "learning_state.json").write_text('{"state": {}}', encoding="utf-8")
    def event(kind, stamp, side, message):
        return {"type": kind, "time": stamp, "message": message,
                "meta": {"timeframe": "M1", "chosen": {"side": side, "confidence": 0.9},
                         "action": "blocked" if side == "buy" else "hold"}}
    old = event("risk", "2026-10-12T12:00:00+00:00", "buy", "Higher-timeframe alignment required.")
    flat = event("decision", "2026-10-14T12:00:00+00:00", "flat", "No directional trade signal selected.")
    blocked = event("risk", "2026-10-14T12:01:00+00:00", "buy", "Timing discipline blocked trade.")
    sample = event("decision_sample", "2026-10-14T12:02:00+00:00", "buy", "Captured live decision sample.")
    (archive / "events_old.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
    (storage / "events.jsonl").write_text(
        "\n".join(json.dumps(row) for row in (old, flat, blocked, sample)) + "\n[]\ninvalid\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(diagnostic, "__file__", str(tmp_path / "tools" / "diagnose_trade_pipeline.py"))
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--since", "2026-10-13", "--output", str(output)])
    diagnostic.main()
    report = json.loads(output.read_text())
    assert report["groups"]["all_retained"]["cycles"] == 3
    assert report["groups"]["since_cutoff"]["cycles"] == 2
    assert report["groups"]["since_cutoff"]["directional"] == 1
    assert report["groups"]["since_cutoff"]["directional_reasons"] == {"timing_discipline": 1}
    assert report["groups"]["before_cutoff"]["directional_reasons"] == {"htf_alignment": 1}
    assert len(report["execution_records"]) == 1


def test_report_refuses_to_overwrite_previous_evidence(tmp_path, monkeypatch):
    output = tmp_path / "existing.json"
    output.write_text("original evidence", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--output", str(output)])
    with pytest.raises(SystemExit):
        diagnostic.main()
    assert output.read_text() == "original evidence"


def test_report_exposes_missing_lfs_history_and_retains_appended_events(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    record = {"type": "decision", "time": "2026-11-04T08:00:00+00:00", "message": "No directional signal.",
              "meta": {"chosen": {"side": "flat"}, "action": "hold"}}
    (storage / "events.jsonl").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 12345\n" + json.dumps(record) + "\n"
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(diagnostic, "__file__", str(tmp_path / "tools" / "diagnose_trade_pipeline.py"))
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--since", "2026-11-04", "--output", str(output)])
    diagnostic.main()
    report = json.loads(output.read_text())
    coverage = report["source_coverage"]
    assert coverage["partial_history"] is True
    assert coverage["source_issues"][0]["kind"] == "git_lfs_pointer"
    assert coverage["source_issues"][0]["size"] == "12345"
    assert coverage["since_cutoff_decisions_available"] is True
    assert report["groups"]["since_cutoff"]["cycles"] == 1


def test_report_preserves_a_declared_gap_after_journal_repair(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "events.jsonl").write_text("")
    (storage / "learning_state.json").write_text('{"state":{}}')
    (storage / "event_history_gap.json").write_text('{"recovered":false,"reason":"missing_lfs_object"}')
    output = tmp_path / "report.json"
    monkeypatch.setattr(diagnostic, "__file__", str(tmp_path / "tools" / "diagnose_trade_pipeline.py"))
    monkeypatch.setattr(sys, "argv", ["diagnostic", "--since", "2026-11-04", "--output", str(output)])
    diagnostic.main()
    coverage = json.loads(output.read_text())["source_coverage"]
    assert coverage["partial_history"] is True
    assert coverage["history_gap"]["recovered"] is False
    assert coverage["since_cutoff_decisions_available"] is False
