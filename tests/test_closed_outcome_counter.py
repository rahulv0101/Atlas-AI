from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as NS
import MetaTrader5 as mt5
import pytest
from atlas_ai.risk.outcome_counter import daily_loss_streak,outcome_label
from atlas_ai.learning.closed_position_ledger import ClosedPositionLedger
from atlas_ai.trader import AtlasTrader
from atlas_ai.config.settings import Settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.execution.execution_gate import ExecutionGate


NOW=datetime(2026,11,24,10,tzinfo=timezone.utc)


def row(i,net,**kwargs):
    return dict(position_id=str(i),state='closed',manual_test=False,closed_at=(NOW-timedelta(minutes=1)+timedelta(seconds=i)).isoformat(),
                net_profit=net,**kwargs)


def test_order_idempotency_fees_draws_wins_and_utc_rollover():
    rows=[row(1,-10),row(2,-5),row(3,0)]
    assert daily_loss_streak(reversed(rows),NOW)['consecutive_losses']==2
    assert daily_loss_streak(rows,NOW)==daily_loss_streak(rows,NOW)
    assert daily_loss_streak(rows+[row(4,1)],NOW)['consecutive_losses']==0
    assert daily_loss_streak(rows,NOW+timedelta(days=1))['consecutive_losses']==0
    assert outcome_label(-.01)=='loss' and outcome_label(0)=='draw'
    with pytest.raises(ValueError):daily_loss_streak([row(1,-1),row(1,-1)],NOW)
    with pytest.raises(ValueError):outcome_label(float('nan'))


def setup_ledger(tmp_path):
    cfg=NS(storage_dir=tmp_path,hfm_login=123,hfm_server='demo',symbol='XAUUSD',magic_number=77,mt5_server_timezone='UTC')
    account=NS(login=123,server='demo',trade_mode=mt5.ACCOUNT_TRADE_MODE_DEMO,currency='USD')
    return cfg,account,ClosedPositionLedger(cfg)


def fill(ticket,entry,volume,profit=0,**kwargs):
    values=dict(ticket=ticket,order=ticket,position_id=10,symbol='XAUUSD',magic=77,entry=entry,
        type=mt5.DEAL_TYPE_BUY if entry==0 else mt5.DEAL_TYPE_SELL,volume=volume,price=2000.,
        profit=profit,commission=-.1,swap=0.,fee=0.,time=int(NOW.timestamp())-60+ticket,comment='AAI_Dabcdef_Semax')
    return NS(**{**values,**kwargs})


def test_partial_closes_count_once_after_flat_and_survive_restart(tmp_path):
    cfg,a,ledger=setup_ledger(tmp_path)
    deals=[fill(1,0,1),fill(2,1,.4,2)]
    ledger.ingest_broker_snapshot(account=a,deals=deals,positions=[NS(identifier=10,symbol='XAUUSD')])
    assert ledger.risk_outcome_counter(NOW)['consecutive_losses']==0
    deals.append(fill(3,1,.6,-5))
    ledger.ingest_broker_snapshot(account=a,deals=deals,positions=[])
    expected=ledger.risk_outcome_counter(NOW)
    assert expected['consecutive_losses']==expected['closed_positions_today']==1
    ledger.ingest_broker_snapshot(account=a,deals=deals,positions=[])
    assert ledger.risk_outcome_counter(NOW)==expected
    assert ClosedPositionLedger(cfg).risk_outcome_counter(NOW)==expected


def test_manual_unowned_and_unbalanced_closes_do_not_enter_streak(tmp_path):
    _,a,ledger=setup_ledger(tmp_path)
    ledger.ingest_broker_snapshot(account=a,deals=[fill(1,0,1,comment='manual_broker_test'),fill(2,1,1,-10)],positions=[])
    assert ledger.risk_outcome_counter(NOW)['closed_positions_today']==0
    _,a,ledger=setup_ledger(tmp_path/'unbalanced')
    ledger.ingest_broker_snapshot(account=a,deals=[fill(1,0,1),fill(2,1,.5,-10)],positions=[])
    with pytest.raises(ValueError,match='incomplete_closed_position'):ledger.risk_outcome_counter(NOW)
    _,a,ledger=setup_ledger(tmp_path/'missing_exit')
    ledger.ingest_broker_snapshot(account=a,deals=[fill(1,0,1)],positions=[])
    with pytest.raises(ValueError,match='incomplete_closed_position'):ledger.risk_outcome_counter(NOW)
    _,a,ledger=setup_ledger(tmp_path/'foreign')
    ledger.ingest_broker_snapshot(account=a,deals=[fill(1,0,1,magic=0),fill(2,1,1,-10,magic=0)],positions=[])
    assert ledger.risk_outcome_counter(NOW)['closed_positions_today']==0


def test_entry_acknowledgement_never_erases_losses_or_cooldown():
    state={'trades_today':1,'consecutive_losses':2,'cooldown_until':'future'}
    assert AtlasTrader._record_entry_guard_count(state,NS(success=True,broker_order_id='123'))
    assert state=={'trades_today':2,'consecutive_losses':2,'cooldown_until':'future'}
    assert not AtlasTrader._record_entry_guard_count(state,NS(success=False,broker_order_id='123'))
    assert state['consecutive_losses']==2 and state['trades_today']==2


def test_fees_can_make_a_gross_winner_a_loss_and_a_later_win_resets_it(tmp_path):
    _,a,ledger=setup_ledger(tmp_path)
    deals=[fill(1,0,1),fill(2,1,1,.05)]
    ledger.ingest_broker_snapshot(account=a,deals=deals,positions=[])
    assert ledger.risk_outcome_counter(NOW)['consecutive_losses']==1
    deals += [fill(3,0,1,position_id=11),fill(4,1,1,1.,position_id=11)]
    ledger.ingest_broker_snapshot(account=a,deals=deals,positions=[])
    assert ledger.risk_outcome_counter(NOW)['consecutive_losses']==0


def test_decimal_fee_break_even_does_not_clear_previous_loss(tmp_path):
    _,a,ledger=setup_ledger(tmp_path)
    deals=[fill(1,0,1),fill(2,1,1,-1),fill(3,0,1,position_id=11,commission=-1.11),
           fill(4,1,1,3.33,position_id=11,commission=-2.22)]
    ledger.ingest_broker_snapshot(account=a,deals=deals,positions=[])
    assert ledger.risk_outcome_counter(NOW)['consecutive_losses']==1


def test_trader_sync_preserves_last_verified_value_on_failure(tmp_path):
    t=AtlasTrader.__new__(AtlasTrader);t.store=KnowledgeStore(str(tmp_path));t.execution_gate=NS(sync_closed_outcome_counter=lambda x:None)
    t.settings=Settings(0,'','',storage_dir=str(tmp_path));flags={}
    counter={'verified':True,'consecutive_losses':2,'day_utc':datetime.now(timezone.utc).date().isoformat()}
    t._sync_guard_outcome_counter(flags,counter=counter)
    assert flags['risk_guard_state']['consecutive_losses']==flags['consecutive_losses']==2
    t._sync_guard_outcome_counter(flags,error=RuntimeError('history unavailable'))
    assert flags['consecutive_losses']==2 and flags['closed_outcome_accounting_verified'] is False
    assert 'accounting unavailable' in t._guard_block_reason(flags['risk_guard_state'])


def test_unavailable_broker_snapshot_does_not_advance_learning_history_cursor(tmp_path,monkeypatch):
    t=AtlasTrader.__new__(AtlasTrader);t.settings=Settings(123,'','demo',storage_dir=str(tmp_path))
    t.store=KnowledgeStore(str(tmp_path));t.closed_position_ledger=ClosedPositionLedger(t.settings)
    previous=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    flags={'closed_learning_synced_until':previous};t.store.update_runtime_flags(lambda _:dict(flags))
    monkeypatch.setattr(mt5,'history_deals_get',lambda *args:None)
    monkeypatch.setattr(mt5,'account_info',lambda:None)
    monkeypatch.setattr(mt5,'positions_get',lambda:None)
    t._sync_closed_trade_learning(flags)
    assert flags['closed_learning_synced_until']==previous
    assert t.store.load_runtime_flags()['closed_learning_synced_until']==previous
    assert flags['closed_outcome_accounting_verified'] is False


def test_explicit_zero_is_authoritative_for_session_and_gateway(tmp_path):
    session=DayTradingSessionControl();session.consecutive_losses=2
    assert session.to_dict(runtime_flags={'consecutive_losses':0})['consecutive_losses']==0
    gate=ExecutionGate(state_store_path=str(tmp_path/'automation_state.json'))
    counter={'verified':True,'day_utc':datetime.now(timezone.utc).date().isoformat(),'consecutive_losses':2}
    gate.sync_closed_outcome_counter(counter)
    assert gate._tiny_live_pilot_consecutive_losses==gate._session_control.consecutive_losses==2
    restored=ExecutionGate(state_store_path=str(tmp_path/'automation_state.json'))
    assert restored._tiny_live_pilot_consecutive_losses==restored._session_control.consecutive_losses==2
    gate.sync_closed_outcome_counter({**counter,'consecutive_losses':0})
    assert gate._tiny_live_pilot_consecutive_losses==gate._session_control.consecutive_losses==0
    result=gate._preflight_gate({'id':'test','environment':'demo'},runtime_flags={'closed_outcome_accounting_verified':False},risk_policy={})
    assert result['reason']=='closed_outcome_accounting_unavailable'


def test_gateway_does_not_allow_caller_zero_to_erase_verified_loss_streak(tmp_path,monkeypatch):
    gate=ExecutionGate(state_store_path=str(tmp_path/'automation_state.json'))
    gate.sync_closed_outcome_counter({'verified':True,'day_utc':datetime.now(timezone.utc).date().isoformat(),'consecutive_losses':2})
    seen={}
    def validate(flags,**kwargs):
        seen.update(flags);return {'ok':False,'reason':'test_stops_before_execution'}
    monkeypatch.setattr(gate,'_validate_required_runtime_flags',validate)
    gate._preflight_gate({'id':'test','environment':'demo'},runtime_flags={'consecutive_losses':0},risk_policy={})
    assert seen['consecutive_losses']==2
