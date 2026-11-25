from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
from datetime import datetime, timezone

from atlas_ai.brain.context import SnapshotSource, build_reasoning_bundle
from atlas_ai.brain.adaptation import build_adaptation_summary
from atlas_ai.brain.memory import BrainMemory
from atlas_ai.decision_support import build_evidence_separation
from atlas_ai.ui.ask_atlas import AskAtlasService


class ChangingSource:
    def __init__(self): self.calls=Counter()
    def load_status(self):
        self.calls['status']+=1
        return {'updated_at':f'2026-11-26T08:{self.calls["status"]:02}:00+00:00',
                'symbol':'XAUUSD','timeframe':'M5','action':'blocked',
                'message':'Timing discipline blocked trade: weak M5 momentum.',
                'chosen':{'strategy':'ema_crossover','side':'sell','confidence':.8},
                'min_confidence_threshold':.6,'higher_timeframe':{'bias':'sell'},
                'chart_features':{'trend_structure':'LH/LL','trend_state':'downtrend'}}
    def load_runtime_flags(self): self.calls['runtime']+=1;return {'execute_trades':True}
    def load_events(self,limit=160): self.calls['events']+=1;return []
    def load_learning_state(self): self.calls['learning']+=1;return {'state':{}}
    def load_comparison(self): self.calls['comparison']+=1;return {}


def test_one_evidence_capture_per_answer_and_fresh_capture_for_followup():
    source=ChangingSource();service=AskAtlasService(source)
    first=service.answer('Why are you not taking trades?')
    assert source.calls==Counter(status=1,runtime=1,events=1,learning=1,comparison=1)
    receipt=first['evidence_receipt']
    assert receipt==first['answer_trace']['evidence_receipt']
    assert service.memory.latest().evidence_receipt['decision_key']==receipt['decision_key']
    second=service.answer('Why?')
    assert source.calls['status']==2
    assert second['evidence_receipt']['decision_key']!=receipt['decision_key']
    assert service.source is source
    assert receipt['cross_file_atomicity_verified'] is False


def test_snapshot_copies_protect_original_and_capture_read_failure():
    source=ChangingSource();snapshot=SnapshotSource(source)
    status=snapshot.load_status();status['chosen']['side']='buy'
    assert snapshot.load_status()['chosen']['side']=='sell'
    assert source.calls['status']==1
    source.load_learning_state=lambda: (_ for _ in ()).throw(RuntimeError('unavailable'))
    failed=SnapshotSource(source)
    assert failed.receipt['read_failures']=={'load_learning_state':'RuntimeError'}
    assert failed.load_learning_state()=={}


def test_enabled_gate_cannot_override_current_block_or_HOLD():
    status=ChangingSource().load_status()
    runtime={'execution':{'auto_trade_allowed':True,'automation_live_allowed':True}}
    for action in ('blocked','hold','wait','connecting'):
        assert build_evidence_separation({**status,'action':action},runtime)['execution_permission']=='not_allowed'
    executed={**status,'action':'execute','message':'Executed sell'}
    assert build_evidence_separation(executed,runtime)['execution_permission']=='allowed'


def test_dashboard_and_answer_bundle_use_same_bias_and_readiness():
    status=ChangingSource().load_status()
    # Final bias can be neutral despite a clear bearish market direction.
    status['decision_analysis']={'final_trade_bias':'neutral','higher_timeframe_bias':'sell'}
    kwargs=dict(status=status,runtime={},events=[],learning_state={},knowledge_payload={})
    ask=build_reasoning_bundle(**kwargs)
    dashboard=build_reasoning_bundle(**kwargs,execution_ready=False)
    assert ask['evidence_separation']==dashboard['evidence_separation']
    assert ask['cognitive_core']['decision_understanding']==dashboard['cognitive_core']['decision_understanding']
    assert ask['evidence_receipt']['decision_key']==dashboard['evidence_receipt']['decision_key']
    assert ask['evidence_separation']['market_bias']=='sell'
    assert ask['evidence_separation']['execution_permission']=='not_allowed'


def test_typed_and_voice_share_evidence_identity_without_command_execution(monkeypatch):
    source=ChangingSource();status=source.load_status()
    source.load_status=lambda:deepcopy(status)
    service=AskAtlasService(source)
    monkeypatch.setattr(service,'_execute_system_command',lambda *a,**k: (_ for _ in ()).throw(AssertionError('no command')),raising=False)
    typed=service.answer('What are your limitations?')
    voice=service.answer('What are your limitations?',mode='voice')
    assert typed['selected_domain']==voice['selected_domain']=='self_model'
    assert typed['evidence_receipt']['decision_key']==voice['evidence_receipt']['decision_key']
    assert len(voice['result'])<=len(typed['result'])


def test_adaptation_estimates_cannot_claim_measured_latency_and_memory_receipts_are_isolated():
    result=build_adaptation_summary({},[])
    assert result['measured_latency_available'] is False
    assert 'heuristic' in result['metric_basis']
    memory=BrainMemory();receipt={'decision_key':'A'}
    memory.add(query='Why?',intent='why',domain='status',plan='why',answer='Known evidence',evidence_receipt=receipt)
    receipt['decision_key']='B'
    assert memory.latest().evidence_receipt['decision_key']=='A'


def test_concurrent_requests_do_not_swap_each_others_sources(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    source=ChangingSource();service=AskAtlasService(source)
    barrier=Barrier(2)
    def handler(query,mode='standard'):
        barrier.wait(timeout=10)
        return {'handled_as':'general','observed':service.source.load_status()['updated_at']}
    monkeypatch.setattr(service,'_answer_in_context',handler)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(service.answer,['What can you do?','What are your limitations?']))
    for reply in replies:
        assert reply['observed']==reply['evidence_receipt']['status_updated_at']
    assert len({r['evidence_receipt']['decision_key'] for r in replies})==2
    assert service.source is source


def test_dashboard_uses_current_automation_and_does_not_promote_blocked_candidate(monkeypatch,tmp_path):
    import atlas_ai.ui_server as ui
    current={'auto_trade_allowed':False,'source':'current_automation'}
    monkeypatch.setattr(ui,'_load_automation_payload',lambda store:current)
    monkeypatch.setattr(ui,'_reconcile_desktop_window_state',lambda window,store:window)
    monkeypatch.setattr(ui,'_build_operator_readiness',lambda *args:{})
    monkeypatch.setattr(ui,'_build_execution_readiness',lambda *args:{'ready':True})
    monkeypatch.setattr(ui,'_build_learning_lanes_status',lambda *args:{'lanes':{}})
    monkeypatch.setattr(ui,'_tail_learning_events_fast',lambda *args,**kw:[])
    monkeypatch.setattr(ui,'_load_json_file',lambda *args:{})
    observed={}
    real=ui.build_reasoning_bundle
    def build(**kw):
        observed.update(kw['runtime'])
        return real(**kw)
    monkeypatch.setattr(ui,'build_reasoning_bundle',build)
    events=[{'type':'risk','message':'Timing discipline blocked trade'}]
    store=SimpleNamespace(base=tmp_path,load_learning_state=lambda:{},tail_events=lambda **kw:events)
    result=ui._build_cognitive_state_payload(ChangingSource().load_status(),
             {'execution':{'auto_trade_allowed':True,'source':'stale_runtime'}},store)
    assert observed['execution']==current
    assert result['evidence_separation']['execution_permission']=='not_allowed'
    assert result['execution_readiness']['infrastructure_ready'] is True
    assert result['execution_readiness']['ready'] is False
    assert 'execution is blocked' in result['headline']
    from atlas_ai.brain.context import fingerprint
    assert result['evidence_receipt']['events_fingerprint']==fingerprint(events)


def test_separate_voice_and_typed_workers_share_compact_local_continuity(tmp_path):
    path=tmp_path/'assistant_conversation.json'
    typed=BrainMemory(file_path=path);voice=BrainMemory(file_path=path)
    typed.add(query='What are your limitations?',intent='limitations',domain='self_model',
              plan='self_model',answer='My trading performance is unproven.',evidence_receipt={'decision_key':'A'})
    assert voice.latest().query=='What are your limitations?'
    voice.add(query='Why?',intent='limitations',domain='self_model',plan='self_model',
              answer='Independent evidence is required.',evidence_receipt={'decision_key':'B'})
    assert typed.latest().query=='Why?'
    assert typed.latest().evidence_receipt['decision_key']=='B'
    import json
    saved=json.loads(path.read_text())
    assert saved['authority']=='continuity_only_no_trading_or_command_control'


def test_persisted_memory_is_bounded_expires_and_redacts_basic_credentials(tmp_path,monkeypatch):
    import json
    import atlas_ai.brain.memory as module
    clock=[1000.]
    monkeypatch.setattr(module.time,'time',lambda:clock[0])
    path=tmp_path/'memory.json';memory=BrainMemory(max_turns=2,file_path=path,max_age_seconds=60)
    for i in range(3):
        memory.add(query=f'Question {i}',intent='help',domain='self_model',plan='help',
                   answer='password=example_private_value')
    saved=json.loads(path.read_text())
    assert len(saved['turns'])==2
    assert 'example_private_value' not in path.read_text()
    clock[0]=1061.
    assert memory.latest() is None


def test_standalone_voice_gets_learning_memory_and_comparison_without_second_status_read(tmp_path):
    from atlas_ai.voice.wake_loop import VoiceSource
    calls=Counter()
    def status():
        calls['status']+=1
        return {'updated_at':str(calls['status']),'comparison':{'run_id':'captured_once'}}
    store=SimpleNamespace(base=tmp_path,load_status=status,load_runtime_flags=lambda:{},
                          tail_events=lambda **kw:[],load_learning_state=lambda:{'state':{'loss_memory':{'samples':2}}})
    source=VoiceSource(store)
    captured=SnapshotSource(source)
    assert calls['status']==1
    assert captured.load_comparison()=={'run_id':'captured_once'}
    assert captured.load_learning_state()['state']['loss_memory']['samples']==2
