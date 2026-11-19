"""Bounded startup resume for the explicitly configured research-only collector."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.learn_candidate_ranker import signed


def resume(storage,*,start=subprocess.Popen):
    storage=Path(storage).resolve();pointer=storage/'settled_m5_forward_active.json'
    if not pointer.exists():return {'state':'not_configured'}
    directory=Path(json.loads(pointer.read_text())['run_dir']).resolve();directory.relative_to(storage)
    protocol=signed(directory,'protocol')
    if protocol.get('broker_eligible') is not False or protocol.get('auto_promotion') is not False or protocol.get('orders_sent')!=0:
        raise ValueError('research_only_collector_required')
    if datetime.now(timezone.utc)>=datetime.fromisoformat(protocol['deadline']):return {'state':'deadline_reached'}
    status=json.loads((directory/'status.json').read_text()) if (directory/'status.json').exists() else {}
    if status.get('state') in {'blocked_review_required','deadline_review_required'}:return {'state':status['state']}
    try:
        with observation_lock(directory/'collector.lock'):pass
    except RuntimeError:return {'state':'existing_settled_collector_running'}
    root=storage.parent;python=root/'.venv/Scripts/pythonw.exe'
    if not python.exists():raise ValueError('project_pythonw_missing')
    with (directory/'collector.stdout.log').open('a') as out,(directory/'collector.stderr.log').open('a') as err:
        child=start([str(python),'-m','tools.settled_m5_collector','--directory',str(directory),'--watch'],
            cwd=root,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return {'state':'settled_collector_started','pid':child.pid}
