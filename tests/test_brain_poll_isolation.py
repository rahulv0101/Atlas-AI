import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Barrier
from types import SimpleNamespace

from atlas_ai.brain.context import BACKGROUND_OPERATOR_QUERIES
from atlas_ai.brain.memory import BrainMemory
from atlas_ai.ui.ask_atlas import AskAtlasService
from test_brain_coordination import ChangingSource


def test_panel_refresh_does_not_replace_operator_context(tmp_path):
    source = ChangingSource()
    source.store = SimpleNamespace(base=tmp_path)
    service = AskAtlasService(source)
    service.answer('What are your limitations?')
    path = tmp_path / 'assistant_conversation.json'
    before = path.read_bytes()
    for query in BACKGROUND_OPERATOR_QUERIES:
        answer = service.answer(query, request_origin='dashboard_poll')
        assert answer['request_origin'] == 'dashboard_poll'
        assert answer.get('handled_as') != 'rejected'
    assert path.read_bytes() == before
    assert service.memory.latest().query == 'What are your limitations?'
    service.answer('Show me the live pilot review', request_origin='operator')
    assert service.memory.latest().query == 'Show me the live pilot review'


def test_background_cannot_route_actions(monkeypatch):
    service = AskAtlasService(ChangingSource())
    monkeypatch.setattr(service, '_answer_pinned', lambda *a, **k: (_ for _ in ()).throw(AssertionError('routed')))
    for query in ('start system', 'close system', 'buy gold', 'Atlas wake'):
        assert service.answer(query, request_origin='dashboard_poll')['handled_as'] == 'rejected'


def test_legacy_poll_is_preserved_but_not_used_as_context(tmp_path):
    memory = BrainMemory()
    for query in ('What are your limitations?', 'Show me the live pilot review'):
        memory.add(query=query, intent='test', domain='test', plan='test', answer='Grounded')
    rows = [asdict(turn) for turn in memory.recent()]
    for row in rows:
        row.pop('request_origin')
    path = tmp_path / 'conversation.json'
    path.write_text(json.dumps({'schema': 'atlas_operator_conversation_v1', 'turns': rows}))
    before = path.read_bytes()
    restored = BrainMemory(file_path=path)
    assert restored.latest().query == 'What are your limitations?'
    assert len(restored.recent()) == 1
    assert path.read_bytes() == before


def test_concurrent_poll_has_private_memory(monkeypatch):
    service = AskAtlasService(ChangingSource())
    barrier = Barrier(2)
    def answer(query, **kwargs):
        barrier.wait(timeout=5)
        service.memory.add(query=query, intent='test', domain='test', plan='test', answer='Grounded')
        return {'result': query}
    monkeypatch.setattr(service, '_answer_pinned', answer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        operator = pool.submit(service.answer, 'What are your limitations?')
        poll = pool.submit(service.answer, 'Show me the live pilot review', request_origin='dashboard_poll')
        operator.result(); poll.result()
    assert [turn.query for turn in service.memory.recent()] == ['What are your limitations?']


def test_api_marks_legacy_polls_but_preserves_explicit_operator(tmp_path, monkeypatch):
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    from atlas_ai.ui_server import create_ui_app
    monkeypatch.setattr('atlas_ai.ui_server.announce_ui_ready_once', lambda *a, **k: True)
    calls = []
    def answer(self, query, mode='', *, request_origin='operator'):
        calls.append((query, request_origin))
        return {'result': 'Read-only summary'}
    monkeypatch.setattr(AskAtlasService, 'answer', answer)
    client = create_ui_app(KnowledgeStore(str(tmp_path))).test_client()
    for query in BACKGROUND_OPERATOR_QUERIES:
        assert client.post('/api/ask-atlas', json={'query': query}).status_code == 200
        assert calls[-1] == (query, 'dashboard_poll')
    client.post('/api/ask-atlas', json={'query': query, 'request_origin': 'operator'})
    assert calls[-1] == (query, 'operator')
    client.post('/api/ask-atlas', json={'query': 'What are your limitations?'})
    assert calls[-1][1] == 'operator'
