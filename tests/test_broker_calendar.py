from datetime import datetime,timezone
from types import SimpleNamespace
import pytest

from atlas_ai.data.broker_calendar import market_hours
from atlas_ai.execution.session_control import DayTradingSessionControl,SessionWindow


def at(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def control():
    c=DayTradingSessionControl(sessions=[SessionWindow('new_york','09:30','16:00','America/New_York',no_trade_buffer_minutes=10)])
    c.bind_broker_calendar('HFM','XAUUSD')
    return c


@pytest.mark.parametrize('day,open_time,buffer_time,close_time', [
    ('26','19:19','19:20','19:30'),('27','19:34','19:35','19:45')])
def test_published_close_is_utc_converted_and_uses_existing_buffer(day,open_time,buffer_time,close_time):
    c=control();date='2026-11-'+day+'T'
    assert c.check(now=at(date+open_time+':00Z'),runtime_flags={}) .allowed
    near=c.check(now=at(date+buffer_time+':00Z'),runtime_flags={'open_positions':1})
    assert not near.allowed and near.minutes_to_close==10
    assert near.reason=='broker_close_no_new_trades' and near.forced_flat_required
    closed=c.check(now=at(date+close_time+':00Z'),runtime_flags={'open_positions':1})
    assert not closed.allowed and not closed.session_active and closed.forced_flat_required
    assert closed.reason=='broker_market_closed'


@pytest.mark.parametrize('broker,symbol,stamp',[('Other','XAUUSD','2026-11-26T20:00Z'),('HFM','EURUSD','2026-11-26T20:00Z'),('HFM','XAUUSD','2026-11-30T20:00Z')])
def test_exception_cannot_leak_to_other_brokers_symbols_or_dates(broker,symbol,stamp):
    assert market_hours(broker,symbol,at(stamp))['applicable'] is False


def test_next_local_day_does_not_inherit_yesterdays_closure_or_grant_reopening():
    c=control();r=c.check(now=at('2026-11-27T00:00:00Z'),runtime_flags={})
    assert not r.allowed  # This control has no eligible Asian session.
    hours=c.broker_market_hours(at('2026-11-27T00:00:00Z'))
    assert not hours['market_closed'] and hours['reopening_time_verified'] is False


def test_an_earlier_normal_session_close_is_not_relabelled_or_extended():
    c=DayTradingSessionControl(sessions=[SessionWindow('asia','00:00','06:00','UTC',no_trade_buffer_minutes=10)])
    c.bind_broker_calendar('HFM','XAUUSD')
    r=c.check(now=at('2026-11-27T05:50Z'),runtime_flags={})
    assert not r.allowed and r.reason=='near_session_close_no_new_trades'
    assert r.minutes_to_close==10 and r.calendar_status=='regular'


def test_early_close_reduces_owned_exposure_but_preserves_kill_switch(tmp_path):
    from test_intraday_exit import Broker,position
    from atlas_ai.execution.execution_gate import ExecutionGate
    class CalendarBroker(Broker):
        def market_calendar_identity(self):return {'broker':'HFM','symbol':'XAUUSD'}
    gate=ExecutionGate(state_store_path=str(tmp_path/'automation.json'))
    gate.set_execution_environment('demo');gate.set_gate_enabled(True)
    broker=CalendarBroker([position(),position('manual',owned=False)])
    gate.set_broker_adapter(broker)
    gate._session_control._sessions=control()._sessions
    gate.activate_kill_switch(reason='test')
    r=gate.enforce_intraday_exit(runtime_flags={'execute_trades':True},now=at('2026-11-27T19:35Z'))
    assert not broker.sent and r['entries_blocked'] and not r['flat_verified']
    gate.deactivate_kill_switch(reason='test')
    r=gate.enforce_intraday_exit(runtime_flags={'execute_trades':True},now=at('2026-11-27T19:35Z'))
    assert broker.sent==[('close','P')] and r['flat_verified']
    assert len(broker.rows)==1 and broker.rows[0]['broker_order_id']=='manual'


def test_session_override_cannot_bypass_broker_closure(tmp_path,monkeypatch):
    from test_intraday_exit import Broker
    from atlas_ai.execution import execution_gate as module
    class CalendarBroker(Broker):
        def market_calendar_identity(self):return {'broker':'HFM','symbol':'XAUUSD'}
    gate=module.ExecutionGate(state_store_path=str(tmp_path/'automation.json'))
    gate.set_broker_adapter(CalendarBroker([]));gate._session_control._sessions=control()._sessions
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return at('2026-11-27T19:46:00Z')
    monkeypatch.setattr(module,'datetime',Clock)
    r=gate._preflight_gate({'id':'test','environment':'demo'},runtime_flags={'session_override_active':True},risk_policy={})
    assert r['reason']=='broker_market_closed'


def test_scheduled_close_is_displayed_without_erasing_safety_blockers():
    from atlas_ai.ui_server import _build_execution_readiness
    hours=market_hours('HFM','XAUUSD',at('2026-11-26T20:00Z'))
    status={'action':'hold','message':'Scheduled HFM XAUUSD early close at 21:30 SAST.',
            'broker_market_hours':hours,'system_health':{'broker_connectivity_status':{'connected':True,'symbol_selected':True}}}
    automation={'automation_enabled':True,'session_control':{'session_active':False,'broker_market_hours':hours}}
    r=_build_execution_readiness(status,{'execute_trades':True},automation)
    assert r['primary_blocker']['code']=='broker_market_closed'
    automation['kill_switch_active']=True
    r=_build_execution_readiness(status,{'execute_trades':True},automation)
    assert r['primary_blocker']['code']=='kill_switch_active'
