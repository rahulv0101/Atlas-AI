from tools.execution_quality_report import summarize
from tools.candidate_score_audit import filtered_cache


def test_quality_report_does_not_count_diagnostics_unknown_fills_or_duplicates():
    row={"schema":"atlas_execution_cost_v1","source":"entry","started_at":"2026-11-10T10:00Z",
        "order_id":"1","deal_id":"2","filled":True,"diagnostic":False,
        "adverse_fill_difference_bps":.5,"dispatch_ms":20}
    result=summarize([row,row,{**row,"order_id":"3","diagnostic":True},
        {**row,"order_id":"4","filled":False},{**row,"order_id":"5","adverse_fill_difference_bps":float("nan")}])
    assert result["measured_fill_observations"]==1 and result["diagnostic_dispatches_excluded"]==1
    assert result["unmeasured_or_unfilled_dispatches"]==2
    assert result["adverse_request_to_fill_bps"]["mean"]==.5
    assert not result["strategy_performance_proven"] and not result["broker_eligible"]


def test_empty_evidence_is_not_a_zero_slippage_estimate():
    result=summarize([])
    assert result["state"]=="awaiting_measured_fills"
    assert result["adverse_request_to_fill_bps"]["mean"] is None


def test_research_score_filter_is_fixed_and_does_not_rewrite_its_source_cache():
    cache={"bar":[{"side":"buy","confidence":.54},{"side":"sell","confidence":.55}]}
    filtered=filtered_cache(cache)
    assert filtered["bar"][0]["side"]=="flat" and cache["bar"][0]["side"]=="buy"
    assert filtered["bar"][1]==cache["bar"][1]
