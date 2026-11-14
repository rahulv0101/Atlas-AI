from atlas_ai.testing.historical_broker import BrokerSpec
from tools.audit_smc_sizing import minimum_lot_check


def test_minimum_lot_reasons_are_independent_and_boundary_is_allowed():
    spec=BrokerSpec(point=.01,tick_size=.01,tick_value_profit=10,tick_value_loss=10,
                    volume_min=.01,volume_max=100,volume_step=.01,digits=2,
                    trade_stops_level=0,trade_freeze_level=0,margin_per_lot=1000,
                    roundtrip_fee_per_lot=0)
    boundary=minimum_lot_check(500,spec,10000,.005,.01)
    assert boundary['risk_cash']==50
    assert not any(boundary[k] for k in ['risk_budget_exceeded','lot_cap_exceeded','margin_exceeded'])
    assert minimum_lot_check(501,spec,10000,.005,.01)['risk_budget_exceeded']
    assert minimum_lot_check(1,spec,10000,.005,.001)['lot_cap_exceeded']
    assert minimum_lot_check(1,spec,9,.5,.01)['margin_exceeded']


def test_shared_research_reply_labels_sizing_as_simulation():
    from atlas_ai.research_status import research_answer
    progress={'entry_comparison':{'stale':False,'state':'completed_research_only',
        'selection':{'selected_for_forward_paper':None},'sizing_audit':{'models':{
            'event':{'complete_signals':13,'risk_budget_exceeded':12},
            'sweep':{'complete_signals':67,'risk_budget_exceeded':66}}}}}
    for voice in [True,False]:
        text=research_answer(progress,'entry model comparison results',voice=voice)
        assert '78 of 80' in text and 'simulation' in text and 'none' in text
        assert 'No broker model is activated' in text
