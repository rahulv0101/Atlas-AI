"""Resume one immutable historical SMC review; never broker trading or promotion."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_signed(path):
    path=Path(path)
    if digest(path)!=path.with_suffix('.sha256').read_text().strip():raise ValueError('historical_review_receipt_changed')
    return json.loads(path.read_text())


def register(storage,directory):
    from tools.learn_candidate_ranker import save_signed
    storage=Path(storage).resolve();directory=Path(directory).resolve();directory.relative_to(storage)
    p=read_signed(directory/'protocol.json')
    if p.get('broker_eligible') is not False or p.get('auto_promotion') is not False:raise ValueError('research_only_required')
    path=storage/'smc_long_review_active.json'
    if path.exists():
        existing=read_signed(path)
        if existing['protocol_sha256']!=digest(directory/'protocol.json'):raise ValueError('historical_registration_no_reset')
        return path
    value={'schema':'atlas_smc_long_review_v1','directory':str(directory),
           'source_root':str(directory/p['models'][0]/'frozen_source'),
           'source_manifest_sha256':digest(directory/p['models'][0]/'manifest.json'),
           'input_receipts':{period:digest(directory/period/'inputs.json') for period in ('development','holdout')},
           'protocol_sha256':digest(directory/'protocol.json'),'worker_sha256':digest(__file__),
           'registered_at':datetime.now(timezone.utc).isoformat(),'deadline':p['deadline'],
           'broker_eligible':False,'orders_sent':0,'auto_promotion':False}
    save_signed(storage,'smc_long_review_active',value)
    return path


def validate(path,storage):
    value=read_signed(path);storage=Path(storage).resolve()
    if value.get('schema')!='atlas_smc_long_review_v1' or value.get('broker_eligible') is not False or value.get('auto_promotion') is not False or value.get('orders_sent')!=0:
        raise ValueError('historical_boundary_changed')
    directory=Path(value['directory']).resolve();directory.relative_to(storage)
    source=Path(value['source_root']).resolve();source.relative_to(directory)
    if value['worker_sha256']!=digest(__file__) or value['protocol_sha256']!=digest(directory/'protocol.json'):
        raise ValueError('historical_worker_or_protocol_changed')
    if digest(source.parent/'manifest.json')!=value['source_manifest_sha256']:raise ValueError('historical_model_manifest_changed')
    m=read_signed(source.parent/'manifest.json')
    for period,expected in value['input_receipts'].items():
        receipt=directory/period/'inputs.json'
        if digest(receipt)!=expected:raise ValueError('historical_input_receipt_changed')
        for tf,h in read_signed(receipt).items():
            if digest(directory/period/(tf+'.csv'))!=h:raise ValueError('historical_input_data_changed')
    for name,expected in m['source_hashes'].items():
        file=(source/name).resolve();file.relative_to(source)
        if digest(file)!=expected:raise ValueError('historical_frozen_source_changed')
    return value


def ensure(storage,state,*,can_start,now,start=subprocess.Popen):
    storage=Path(storage).resolve();path=storage/'smc_long_review_active.json'
    if not path.exists():return {'state':'not_configured'}
    r=validate(path,storage);directory=Path(r['directory'])
    if (directory/'report.json').exists():
        report=read_signed(directory/'report.json')
        if report['protocol_sha256']!=r['protocol_sha256']:raise ValueError('historical_report_scope_changed')
        return {'state':'completed_research_only','historically_qualified':report['historically_qualified'],'broker_eligible':False}
    if now>=datetime.fromisoformat(r['deadline']):return {'state':'deadline_review_required'}
    status=json.loads((directory/'worker_status.json').read_text()) if (directory/'worker_status.json').exists() else {}
    if status.get('state')=='blocked_review_required':return status
    from atlas_ai.learning.observation_checkpoint import observation_lock
    try:
        with observation_lock(directory/'historical_worker.lock'):pass
    except RuntimeError:return {'state':'existing_historical_review_running'}
    if not can_start:return {'state':'waiting_for_backend_and_operator'}
    attempts=state.setdefault('smc_long_review_starts',[]);attempts[:]=[t for t in attempts if 0<=now.timestamp()-t<3600]
    if len(attempts)>=3:return {'state':'restart_budget_exhausted_review_required'}
    with (directory/'worker.stdout.log').open('a') as out,(directory/'worker.stderr.log').open('a') as err:
        child=start([sys.executable,str(Path(__file__).resolve()),'run','--registry',str(path)],cwd=ROOT,
            env={**os.environ,'STORAGE_DIR':str(storage)},stdout=out,stderr=err,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
    attempts.append(now.timestamp());return {'state':'historical_review_started','pid':child.pid,'orders_sent':0,'broker_eligible':False}


def run(path):
    path=Path(path).resolve();r=validate(path,path.parent);directory=Path(r['directory'])
    sys.path.insert(0,r['source_root'])
    from atlas_ai.learning.observation_checkpoint import observation_lock
    from atlas_ai.atomic_files import atomic_json
    from tools.research_smc_h1 import run as frozen_run
    with observation_lock(directory/'historical_worker.lock'):
        if (directory/'report.json').exists():return
        try:
            atomic_json(directory/'worker_status.json',{'state':'running_historical_research','checked_at':datetime.now(timezone.utc).isoformat(),'orders_sent':0})
            frozen_run(directory)
            atomic_json(directory/'worker_status.json',{'state':'completed_research_only','checked_at':datetime.now(timezone.utc).isoformat(),'orders_sent':0})
        except Exception as exc:
            atomic_json(directory/'worker_status.json',{'state':'blocked_review_required','reason':str(exc),'checked_at':datetime.now(timezone.utc).isoformat(),'orders_sent':0})
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['register','run']);p.add_argument('--directory',type=Path);p.add_argument('--registry',type=Path);a=p.parse_args()
    if a.mode=='register':
        sys.path.insert(0,str(ROOT))
        from atlas_ai.config.settings import load_settings
        if a.directory is None:p.error('--directory required')
        print(register(load_settings().storage_dir,a.directory))
    else:
        if a.registry is None:p.error('--registry required')
        run(a.registry)
