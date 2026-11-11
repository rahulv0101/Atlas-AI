from datetime import datetime, timedelta, timezone
import json

import pytest

from atlas_ai.config.settings import Settings
from atlas_ai.learning.observation_checkpoint import save_checkpoint
from atlas_ai.testing.activity_review import classify, initialize, review
from atlas_ai.testing.decision_archive import capture


NOW = datetime(2026, 11, 11, 19, tzinfo=timezone.utc)


@pytest.fixture
def run(tmp_path):
    settings = Settings(1, "test", "Demo", storage_dir=str(tmp_path), mt5_server_timezone="Etc/GMT-2")
    journal = tmp_path / "journal.jsonl"; journal.write_text("{}\n")
    save_checkpoint(journal.with_suffix(".checkpoint.json"), settings, set(), {}, set(),
                    {"orders_sent": 0, "lifecycle_acceptance": {}}, journal=journal)
    initialize(tmp_path, settings, journal, NOW)
    return tmp_path, settings, journal


def publish(folder, at, **fields):
    status = {"updated_at": at.isoformat(), "action": "hold", "signals": [], **fields}
    (folder / "status.json").write_text(json.dumps(status))
    capture(folder, at)


def test_fixed_window_is_not_reset_and_old_evidence_is_not_counted(run):
    folder, settings, journal = run
    with pytest.raises(FileExistsError): initialize(folder, settings, journal, NOW + timedelta(days=1))
    publish(folder, NOW - timedelta(minutes=1))
    publish(folder, NOW + timedelta(minutes=1), signals=[{"strategy": "ema", "side": "sell", "confidence": .4}],
            blocker_classification={"class": "signal_quality"})
    before = (folder / "status.json").read_bytes()
    result = review(folder, settings, NOW + timedelta(minutes=2))
    assert result["sampled_publications"] == result["directional_publications"] == 1
    assert result["categories"] == {"directional_signal_filtered": 1}
    assert result["excluded"] == {"outside_window": 1}
    assert result["daily_samples_sast"]["2026-11-11"]["sampled_publications"] == 1
    assert (folder / "status.json").read_bytes() == before
    again = review(folder, settings, NOW + timedelta(minutes=3))
    assert again["sampled_publications"] == 1 and again["deadline"] == result["deadline"]
    assert not again["broker_eligible"] and not again["profitability_proven"] and again["orders_sent"] == 0


@pytest.mark.parametrize("fields,category", [
    ({"freshness_runtime": {"is_stale": True}}, "technical_or_data_block"),
    ({"execution_state": {"kill_switch_active": True}}, "operator_or_execution_control"),
    ({"safety_layer": {"cooldown_active": True}}, "risk_or_safety_block"),
    ({"signals": []}, "no_directional_signal"),
    ({"chosen": {"side": "sell"}, "timing_discipline": {"enabled": True, "passed": False}}, "directional_signal_filtered"),
    ({"decision_analysis": {"decision_protocol": {"act": {"execution_request_eligible": True}}}}, "analysis_eligible_requires_execution_gates"),
    ({}, "insufficient_evidence"),
])
def test_distinguishes_faults_controls_no_signals_and_filters(fields, category):
    assert classify(fields)["category"] == category


def test_zero_cycles_fails_at_deadline_even_with_no_observations(run):
    folder, settings, _ = run
    result = review(folder, settings, NOW + timedelta(days=7))
    assert result["state"] == "activity_requirement_failed"
    assert result["sampled_publications"] == result["verified_natural_cycles_in_window"] == 0
    assert all(day["observation_state"] == "no_samples" for day in result["daily_samples_sast"].values())


def save_cycle(run, when, *, manual=False):
    folder, settings, journal = run
    # Configured server wall clock is UTC+2; timestamps are deliberately not UTC epochs.
    broker_msc = int((when + timedelta(hours=2)).timestamp() * 1000)
    seen = {"11": {"ticket": "11", "position_id": "5", "broker_time_msc": broker_msc},
            "12": {"ticket": "12", "position_id": "5", "broker_time_msc": broker_msc + 1000}}
    natural = {"state": "verified", "manual_and_forced_tests_count_as_acceptance": manual,
               "verified_end_to_end_cycles": [{"position_id": "5", "decision_id": "id", "strategy": "ema",
                                               "management_evidence": "broker_open_position_with_protective_sl_tp"}]}
    save_checkpoint(journal.with_suffix(".checkpoint.json"), settings, set(), seen, {"5"},
                    {"orders_sent": 0, "lifecycle_acceptance": natural}, journal=journal)


@pytest.mark.parametrize("offset,manual,expected", [
    (timedelta(minutes=1), False, 1),
    (timedelta(minutes=1), True, 0),
    (timedelta(minutes=-1), False, 0),
    (timedelta(days=7, minutes=1), False, 0),
])
def test_only_natural_cycles_with_broker_times_inside_window_count(run, offset, manual, expected):
    folder, settings, _ = run; save_cycle(run, NOW + offset, manual=manual)
    result = review(folder, settings, NOW + timedelta(days=8))
    assert result["verified_natural_cycles_in_window"] == expected
    assert result["state"] == ("activity_requirement_met" if expected else "activity_requirement_failed")
    assert not result["profitability_proven"]


def test_coverage_gaps_and_reasons_are_counted_without_claiming_missed_profits(run):
    folder, settings, _ = run
    publish(folder, NOW + timedelta(minutes=1), signals=[],
            decision_analysis={"strategy_coverage": {"coverage_gap": True}, "hard_blockers": ["macro_conflict"]})
    result = review(folder, settings, NOW + timedelta(minutes=2))
    assert result["coverage_gap_publications"] == 1 and result["reason_codes"]["macro_conflict"] == 1
    assert "not unique setups" in result["coverage"]


@pytest.mark.parametrize("target", ["protocol.json", "checkpoint.json"])
def test_protocol_and_checkpoint_changes_are_not_silently_reset(run, target):
    folder, settings, _ = run; review(folder, settings, NOW)
    path = folder / "activity_review" / target
    data = json.loads(path.read_text())
    if target == "protocol.json": data["deadline"] = (NOW + timedelta(days=8)).isoformat()
    else: data["state"]["samples"] = 999
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): review(folder, settings, NOW + timedelta(minutes=1))


def test_new_archive_corruption_blocks_review_and_preserves_checkpoint(run):
    folder, settings, _ = run
    review(folder, settings, NOW)
    path = folder / "activity_review/checkpoint.json"; before = path.read_bytes()
    publish(folder, NOW + timedelta(minutes=1))
    next((folder / "replay_evidence/records").iterdir()).write_bytes(b"changed")
    with pytest.raises(ValueError, match="activity_archive_record_changed"):
        review(folder, settings, NOW + timedelta(minutes=2))
    assert path.read_bytes() == before
