import json

import pytest

from tools.review_cost_research import review_lanes,review


def stats(trades=30,days=2):
    return {"trades":trades,"days":days,"mean_r":.2,"profit_factor":1.5,"max_drawdown_r":2,"wins":20,"losses":10}


def test_paper_counts_cannot_be_summed_across_lanes_to_qualify():
    history={k:{"training":{"configured_costs":stats()},"holdout":{"configured_costs":stats()}} for k in ("a","b")}
    forward={k:{"summary":{"configured_costs":stats(20)}} for k in history}
    result=review_lanes(history,forward)
    assert result["operator_review_ready_count"]==0 and result["broker_eligible"] is False
    assert all("insufficient_trades" in v["pending"]["forward"] for v in result["lanes"].values())


def test_even_a_passing_comparison_only_becomes_ready_for_operator_review():
    history={"a":{"training":{"configured_costs":stats()},"holdout":{"configured_costs":stats()}}}
    forward={"a":{"summary":{"configured_costs":stats()}}}
    result=review_lanes(history,forward)
    assert result["operator_review_ready_count"]==1 and result["broker_eligible"] is False and result["orders_sent"]==0
    assert review_lanes(history,forward,source_valid=False)["operator_review_ready_count"]==0


def test_one_day_is_not_sufficient_even_with_thirty_outcomes():
    history={"a":{"training":{"configured_costs":stats()},"holdout":{"configured_costs":stats()}}}
    forward={"a":{"summary":{"configured_costs":stats(30,1)}}}
    result=review_lanes(history,forward)
    assert "insufficient_days" in result["lanes"]["a"]["pending"]["forward"]


def test_nonfinite_forward_returns_never_qualify():
    history={"a":{"training":{"configured_costs":stats()},"holdout":{"configured_costs":stats()}}}
    forward={"a":{"summary":{"configured_costs":{**stats(),"mean_r":float("nan")}}}}
    result=review_lanes(history,forward)
    assert result["operator_review_ready_count"]==0


def test_stale_observation_does_not_misreport_source_integrity():
    history={"a":{"training":{"configured_costs":stats()},"holdout":{"configured_costs":stats()}}}
    forward={"a":{"summary":{"configured_costs":stats()}}}
    result=review_lanes(history,forward,source_valid=True,evidence_current=False)
    assert result["operator_review_ready_count"]==0 and result["source_integrity_verified"] is True
    assert result["observation_evidence_current"] is False


def test_stricter_manifest_and_training_selection_are_respected():
    history={"a":{"training":{"configured_costs":stats(20)},"holdout":{"configured_costs":stats(20)}}}
    forward={"a":{"summary":{"configured_costs":stats()}}}
    assert review_lanes(history,forward,minimum_cases={"training":30,"holdout":30,"forward":30})["operator_review_ready_count"]==0
    assert review_lanes(history,forward,eligible_keys=set())["operator_review_ready_count"]==0


@pytest.mark.parametrize("factor",[float("nan"),float("inf"),-1])
def test_invalid_profit_factor_cannot_pass(factor):
    from tools.review_cost_research import stage_requirements
    assert stage_requirements({**stats(),"profit_factor":factor},30)==["missing_or_invalid_stats"]


def test_historical_only_experiment_reports_pending_forward_evidence(tmp_path):
    (tmp_path/"manifest.json").write_text(json.dumps({"sources":{}}))
    (tmp_path/"results.json").write_text(json.dumps({"lanes":{"a":{
        "training":{"configured_costs":stats()},"holdout":{"configured_costs":stats()}}}}))
    (tmp_path/"selection.json").write_text(json.dumps({"selected_from_training_only":"a"}))
    result=review(tmp_path)
    assert not result["observation_evidence_current"] and result["forward_asof"] is None
    assert result["operator_review_ready_count"]==0 and not result["broker_eligible"]
