from tools.review_gate_evidence import summarize


def test_absent_gate_is_unknown_and_repeated_publications_are_not_unique_trades():
    row={'meta':{'chosen':{'side':'sell'},'action':'blocked','higher_timeframe':{'entry_gate':{'passed':True,'policy':'v2'}},'timing_discipline':{'passed':False,'missing':['momentum']}}}
    result=summarize([row,row,{'meta':{'chosen':{'side':'buy'}}}])
    assert result['directional_publications']==3
    assert result['gates']['confluence']=={'passed':2,'unrecorded':1}
    assert result['gates']['timing']=={'failed':2,'unrecorded':1}
    assert result['timing_missing']=={'momentum':2}
    assert result['unique_opportunities'] is None
    assert result['live_trade_rate_estimate'] is None
