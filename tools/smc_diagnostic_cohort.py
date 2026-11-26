"""One supervised, read-only process for frozen SMC diagnostic paper models."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signed(path):
    path=Path(path)
    if digest(path)!=path.with_suffix('.sha256').read_text().strip():raise ValueError('signed_artifact_changed:'+path.name)
    return json.loads(path.read_text())


def validate_registry(path,storage):
    r=signed(path);storage=Path(storage).resolve()
    if r.get('schema')!='atlas_smc_diagnostic_cohort_v1' or any(r.get(k) is not False for k in ('broker_eligible','auto_promotion')) or r.get('orders_sent')!=0:
        raise ValueError('diagnostic_boundary_changed')
    source=Path(r['source_root']).resolve();source.relative_to(storage)
    if digest(__file__)!=r['runner_sha256']:raise ValueError('diagnostic_runner_changed')
    shared=None
    for name,entry in r['models'].items():
        d=Path(entry['run_dir']).resolve();d.relative_to(storage)
        if digest(d/'manifest.json')!=entry['manifest_sha256']:raise ValueError('model_manifest_changed')
        m=signed(d/'manifest.json')
        if m.get('model')!=name or m.get('broker_eligible') is not False or m.get('orders_sent')!=0:
            raise ValueError('model_boundary_changed')
        if m['deadline']!=r['deadline'] or m['account_scope']!=r['account_scope']:raise ValueError('model_scope_changed')
        if shared is None:shared=m['source_hashes']
        if shared!=m['source_hashes']:raise ValueError('different_frozen_source_versions')
    if not shared or 'atlas_ai/strategies/smc_h1_research.py' not in shared or 'tools/smc_validation.py' not in shared:
        raise ValueError('verified_model_sources_required')
    for name,expected in shared.items():
        file=(source/name).resolve();file.relative_to(source)
        if digest(file)!=expected:raise ValueError('frozen_model_source_changed')
    return r


def register(storage,directory):
    from tools.learn_candidate_ranker import signed as read_signed,save_signed
    storage=Path(storage).resolve();directory=Path(directory).resolve();directory.relative_to(storage)
    p=read_signed(directory,'protocol')
    path=storage/'smc_h1_diagnostic_active.json'
    if path.exists():
        r=validate_registry(path,storage)
        if r['comparison_protocol_sha256']!=digest(directory/'protocol.json'):raise ValueError('existing_diagnostic_registration_no_reset')
        return path
    r={'schema':'atlas_smc_diagnostic_cohort_v1','registered_at':datetime.now(timezone.utc).isoformat(),
       'comparison_directory':str(directory),'comparison_protocol_sha256':digest(directory/'protocol.json'),
       'source_root':str(directory/p['models'][0]/'frozen_source'),'models':{},
       'account_scope':p['account_scope'],'deadline':p['deadline'],'runner_sha256':digest(__file__),
       'broker_eligible':False,'orders_sent':0,'auto_promotion':False,
       'purpose':'Diagnostic paper cases for all declared models, including historically unqualified controls; no trade activation or qualification claim.'}
    for name in p['models']:
        d=directory/name;m=read_signed(d,'manifest')
        r['models'][name]={'run_dir':str(d),'manifest_sha256':digest(d/'manifest.json')}
    save_signed(storage,'smc_h1_diagnostic_active',r);validate_registry(path,storage)
    return path


def ensure(storage,state,*,can_start,now,start=subprocess.Popen):
    storage=Path(storage).resolve();path=storage/'smc_h1_diagnostic_active.json'
    if not path.exists():return {'state':'not_configured'}
    r=validate_registry(path,storage)
    if now>=datetime.fromisoformat(r['deadline']):return {'state':'deadline_reached'}
    from atlas_ai.learning.observation_checkpoint import observation_lock
    try:
        with observation_lock(storage/'smc_h1_diagnostic.lock'):pass
    except RuntimeError:return {'state':'existing_smc_h1_diagnostic_running'}
    if not can_start:return {'state':'waiting_for_backend_and_operator'}
    attempts=state.setdefault('smc_h1_diagnostic_starts',[]);attempts[:]=[at for at in attempts if 0<=now.timestamp()-at<3600]
    if len(attempts)>=3:return {'state':'restart_budget_exhausted_review_required'}
    with (storage/'smc_h1_diagnostic.stdout.log').open('a') as out,(storage/'smc_h1_diagnostic.stderr.log').open('a') as err:
        child=start([sys.executable,str(Path(__file__).resolve()),'watch','--registry',str(path)],cwd=ROOT,
                    env={**os.environ,'STORAGE_DIR':str(storage)},stdout=out,stderr=err,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    attempts.append(now.timestamp());return {'state':'smc_h1_diagnostic_started','pid':child.pid,'orders_sent':0,'broker_eligible':False}


def watch(path):
    path=Path(path).resolve();storage=path.parent;r=validate_registry(path,storage)
    # Import the model/evaluator from the registered source, not the live tree.
    sys.path.insert(0,r['source_root'])
    from tools.smc_validation import once
    from atlas_ai.atomic_files import atomic_json
    from atlas_ai.learning.observation_checkpoint import observation_lock
    import MetaTrader5 as mt5
    from unittest.mock import patch
    def deny(*a,**kw):raise AssertionError('diagnostic_broker_mutation_forbidden')
    summary_path=storage/'smc_h1_diagnostic_status.json'
    prior=json.loads(summary_path.read_text()) if summary_path.exists() else {}
    if prior.get('registry_sha256') not in (None,digest(path)):raise ValueError('cohort_registry_changed')
    suspended={name:row for name,row in prior.get('models',{}).items() if row.get('state')=='blocked_review_required'}
    with observation_lock(storage/'smc_h1_diagnostic.lock'),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        try:
            while True:
                now=datetime.now(timezone.utc);models={}
                for name,entry in r['models'].items():
                    if name in suspended:models[name]=suspended[name];continue
                    try:
                        report=once(Path(entry['run_dir']),now)
                        models[name]={k:report.get(k) for k in ('state','checked_at','model','paper_trades','pending','first_stage','validation_stage','counts')}
                    except Exception as exc:
                        models[name]={'state':'blocked_review_required','reason':str(exc),'error':type(exc).__name__}
                        suspended[name]=models[name]
                atomic_json(summary_path,{'state':'deadline_review_required' if now>=datetime.fromisoformat(r['deadline']) else 'collecting_diagnostic_paper',
                    'checked_at':now.isoformat(),'registry_sha256':digest(path),'models':models,
                    'broker_eligible':False,'orders_sent':0,'auto_promotion':False,
                    'note':r['purpose']})
                if now>=datetime.fromisoformat(r['deadline']):return
                time.sleep(60)
        finally:mt5.shutdown()


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('mode',choices=['register','watch']);a.add_argument('--directory',type=Path);a.add_argument('--registry',type=Path);args=a.parse_args()
    if args.mode=='register':
        sys.path.insert(0,str(ROOT))
        from atlas_ai.config.settings import load_settings
        if args.directory is None:a.error('--directory required')
        print(register(load_settings().storage_dir,args.directory))
    else:
        if args.registry is None:a.error('--registry required')
        watch(args.registry)
