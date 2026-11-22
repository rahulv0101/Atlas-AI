import json
import threading
from atlas_ai.memory.knowledge_store import KnowledgeStore


def test_scanning_does_not_block_writer_and_never_discards_its_append(tmp_path,monkeypatch):
    store=KnowledgeStore(str(tmp_path));store.log_event('system','original')
    original_loads=json.loads;injected=False;result={};errors=[]
    def loads(raw,*args,**kwargs):
        nonlocal injected
        if not injected:
            injected=True
            store.log_event('system','appended_during_scan')
        return original_loads(raw,*args,**kwargs)
    monkeypatch.setattr(json,'loads',loads)
    def run():
        try:result.update(store.maintain_events(max_lines=1))
        except Exception as exc:errors.append(exc)
    worker=threading.Thread(target=run,daemon=True);worker.start();worker.join(3)
    assert not worker.is_alive(), 'maintenance held the shared lock while parsing'
    assert not errors and result['deferred_concurrent_write']==1
    rows=[original_loads(line) for line in store.events_file.read_text().splitlines()]
    assert [row['message'] for row in rows]==['original','appended_during_scan']
    assert not list((tmp_path/'archive').glob('events_*.jsonl'))
    # A subsequent unchanged scan can perform normal retention.
    result=store.maintain_events(max_lines=1)
    assert result['kept']==1 and result['archived']==1
