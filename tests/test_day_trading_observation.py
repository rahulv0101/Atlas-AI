from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from tools.observe_day_trading import lifecycle_summary,broker_snapshot


def evidence():
    return [{"meta":{"decision_id":"abc","strategy":"ema_crossover","order_id":"101",
        "request_origin":"trader_guarded","execution_success":True,"execution_mode":"demo"}}]


def fills():
    return {"1":{"position_id":"10","order_id":"101","entry":0,"deal_type":0,"broker_time_msc":1,"volume":.01,"net":-1},
            "2":{"position_id":"10","order_id":"102","entry":1,"deal_type":1,"broker_time_msc":2,"volume":.01,"net":9}}


def test_complete_broker_flat_lifecycle_requires_decision_link_and_balanced_fills():
    assert lifecycle_summary(fills(),evidence(),set())==[{"position_id":"10","decision_id":"abc","strategy":"ema_crossover","net":8}]
    assert lifecycle_summary(fills(),evidence(),{"10"})==[]
    assert lifecycle_summary(fills(),[],set())==[]
    partial=fills();partial["2"]["volume"]=.005
    assert lifecycle_summary(partial,evidence(),set())==[]


@pytest.mark.parametrize("change",[{"execution_success":False},{"execution_mode":"paper"},{"request_origin":"manual"},{"comment":"manual_broker_test"}])
def test_unproven_or_manual_events_are_not_natural_trade_evidence(change):
    events=evidence();events[0]["meta"].update(change)
    assert lifecycle_summary(fills(),events,set())==[]


def test_conflicting_links_and_nonfinite_outcomes_are_not_verified():
    events=evidence();other=deepcopy(events[0]);other["meta"]["decision_id"]="other";events.append(other)
    assert lifecycle_summary(fills(),events,set())==[]
    bad=fills();bad["2"]["net"]=float("nan")
    assert lifecycle_summary(bad,evidence(),set())==[]


def test_missing_broker_inventory_or_changed_account_cannot_report_flat():
    settings=NS(hfm_login=1,hfm_server="Demo")
    fake=NS(account_info=lambda:NS(login=2,server="Demo",trade_mode=0))
    with pytest.raises(ValueError,match="matching_demo"):broker_snapshot(settings,api=fake)
    fake.account_info=lambda:NS(login=1,server="Demo",trade_mode=0)
    fake.positions_get=lambda:None;fake.orders_get=lambda:[]
    with pytest.raises(ValueError,match="inventory"):broker_snapshot(settings,api=fake)


@pytest.mark.parametrize("change",[{"forced_demo_entry":True},{"forced_learning_probe":True}])
def test_forced_probe_is_not_autonomous_lifecycle_evidence(change):
    events=evidence();events[0]["meta"].update(change)
    assert lifecycle_summary(fills(),events,set())==[]


def test_full_lifecycle_requires_broker_observed_protection():
    from tools.observe_day_trading import protected_positions,acceptance_summary
    cycle=lifecycle_summary(fills(),evidence(),set())
    assert acceptance_summary(cycle,set())["state"]=="management_evidence_missing"
    managed=protected_positions([{"position_id":"10","side":"buy","sl":1999,"tp":2002,"current_price":2000}])
    assert acceptance_summary(cycle,managed)["state"]=="verified"
    assert protected_positions([{"position_id":"10","side":"buy","sl":0,"tp":2002,"current_price":2000}])==set()
    assert acceptance_summary([],managed)["state"]=="awaiting_autonomous_broker_cycle"


@pytest.mark.parametrize("change",[{"deal_type":0},{"broker_time_msc":0}])
def test_invalid_exit_direction_or_time_cannot_pass_acceptance(change):
    rows=fills();rows["2"].update(change)
    assert lifecycle_summary(rows,evidence(),set())==[]


def test_exit_before_entry_cannot_pass_acceptance():
    rows=fills();rows["2"]["broker_time_msc"]=.5
    assert lifecycle_summary(rows,evidence(),set())==[]
