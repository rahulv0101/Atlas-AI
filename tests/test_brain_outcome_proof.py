import json
from dataclasses import replace
import pytest
from atlas_ai.config.settings import Settings
from atlas_ai.brain.outcomes import load_confirmed_outcomes
from atlas_ai.learning.closed_position_ledger import ClosedPositionLedger,SCHEMA,rebuild_positions
from atlas_ai.ui_server import _last_confirmed_trade_outcome
from atlas_ai.ui.ask_atlas import AskAtlasService


def test_broker_closure_adapter_uses_scoped_ledger_and_excludes_manual_or_unlinked(tmp_path,monkeypatch):
    cfg=Settings(123,'','Demo',storage_dir=str(tmp_path))
    ledger=ClosedPositionLedger(cfg)
    fills={}
    for pos,linked,manual in [('10',True,False),('20',False,False),('30',True,True)]:
        for index,entry in enumerate((0,1)):
            ticket=int(pos)+index
            fills[str(ticket)]={'ticket':ticket,'position_id':pos,'entry_type':entry,
                'deal_type':entry,'time_utc':f'2026-11-25T08:0{index}:00+00:00',
                'volume':.01,'profit':-10 if entry else 0,'commission':0,'swap':0,'fee':0,
                'strategy':'ema_crossover','manual_test':manual,
                'attribution':'decision_linked' if linked else 'broker_comment_only','decision_id':'abc'}
    doc={'schema':SCHEMA,'account_fingerprint':ledger.fingerprint,'currency':'ZAR','fills':fills,
         'positions':rebuild_positions(fills,set())}
    ledger.path.write_text(json.dumps(doc))
    monkeypatch.setattr('MetaTrader5.initialize',lambda *a,**k:(_ for _ in ()).throw(AssertionError('read-only proof')))
    rows=load_confirmed_outcomes(tmp_path,cfg)
    assert len(rows)==1 and rows[0]['position_id']=='10'
    assert rows[0]['broker_confirmed_closed'] and rows[0]['net_pnl_zar']==-10
    assert rows[0]['side']=='buy'
    payload=_last_confirmed_trade_outcome(rows)
    assert payload['available'] and payload['source']=='account_scoped_closed_position_ledger'
    assert 'single outcome' in payload['lesson']
    doc['account_fingerprint']='other_account';ledger.path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='identity_mismatch'):load_confirmed_outcomes(tmp_path,cfg)


def test_plain_memory_and_backtests_cannot_become_confirmed_broker_outcomes():
    assert _last_confirmed_trade_outcome([{'ticket':'123','outcome':'win','net_pnl_zar':1000}])['available'] is False
    class Source:
        def load_learning_state(self):
            return {'state':{'loss_memory':{'recent_outcomes':[{'ticket':'bt_1','outcome':'win'}]}}}
    svc=AskAtlasService(Source())
    assert svc._last_confirmed_trade_outcome()=={}
