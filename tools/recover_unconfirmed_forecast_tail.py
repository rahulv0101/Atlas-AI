"""Reviewed collector repair; preserve all evaluated inputs and forecasts."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import shutil
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.learn_candidate_ranker import signed,save_signed,digest
ROOT=Path(__file__).resolve().parents[1]


def rebind_contract(contract,old_plan_sha,new_plan_sha):
    if contract['plan_sha256']!=old_plan_sha:raise ValueError('review_contract_scope_changed')
    result=deepcopy(contract);result['plan_sha256']=new_plan_sha
    return result


def trim_unreferenced(saved,state):
    cutoff=pd.Timestamp(state['last_available'])
    if cutoff.tzinfo is None:raise ValueError('aware_evaluated_cutoff_required')
    for rows in state['forecasts'].values():
        if any(pd.Timestamp(row['available_at'])>cutoff for row in rows):raise ValueError('forecast_references_tail')
    result=deepcopy(saved);dropped={}
    for tf,minutes in [('M5',5),('H1',60)]:
        times=pd.DatetimeIndex(pd.to_datetime([r['time'] for r in saved[tf]],utc=True))
        if times.has_duplicates or not times.is_monotonic_increasing:raise ValueError('ordered_saved_inputs_required')
        result[tf]=[r for r,at in zip(saved[tf],times) if at+pd.Timedelta(minutes=minutes)<=cutoff]
        dropped[tf]=len(saved[tf])-len(result[tf])
        if len(result[tf])<30:raise ValueError('cannot_remove_required_warmup')
    if pd.Timestamp(result['M5'][-1]['time'])+pd.Timedelta(minutes=5)!=cutoff:raise ValueError('evaluated_M5_input_missing')
    if not sum(dropped.values()):raise ValueError('no_unreferenced_tail_to_repair')
    return result,dropped


def run():
    directory=Path(json.loads((ROOT/'storage/entry_forecast_active.json').read_text())['run_dir']).resolve()
    directory.relative_to((ROOT/'storage').resolve())
    with observation_lock(directory/'observer.lock'):
        plan=signed(directory,'plan');state=signed(directory,'checkpoint')
        status=json.loads((directory/'status.json').read_text())
        if status.get('reason')!='previous_closed_bar_revised':raise ValueError('specific_revision_review_required')
        if state['plan_sha256']!=digest(directory/'plan.json') or state['frame_hash']!=digest(directory/'closed_frames.json'):
            raise ValueError('original_evidence_changed')
        frames=json.loads((directory/'closed_frames.json').read_text());trimmed,dropped=trim_unreferenced(frames,state)
        changed=[n for n,h in plan['source_hashes'].items() if digest(ROOT/n)!=h]
        if len(changed)!=1 or changed[0].replace('\\','/')!='tools/entry_forecast_observer.py':
            raise ValueError('only_reviewed_collector_correction_allowed')
        runner=changed[0];old_runner=directory/'frozen_source'/runner
        if digest(old_runner)!=plan['source_hashes'][runner]:raise ValueError('original_collector_snapshot_changed')
        recovery='recovery_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');archive=directory/recovery;archive.mkdir()
        for name in ('plan.json','plan.sha256','checkpoint.json','checkpoint.sha256','closed_frames.json','status.json','source_snapshot_receipt.json','source_snapshot_receipt.sha256'):
            shutil.copyfile(directory/name,archive/name)
        shutil.copyfile(old_runner,archive/'original_collector.py');shutil.copyfile(Path(__file__),archive/'recovery_tool.py')
        original_plan_sha=digest(directory/'plan.json');forecast_counts={k:len(v) for k,v in state['forecasts'].items()}
        review_contract=None
        if (directory/'outcome_review_contract.json').exists():
            review_contract=signed(directory,'outcome_review_contract')
            if review_contract['plan_sha256']!=original_plan_sha:raise ValueError('review_contract_scope_changed')
            for name in ('outcome_review_contract.json','outcome_review_contract.sha256'):shutil.copyfile(directory/name,archive/name)
        plan['source_hashes'][runner]=digest(ROOT/runner)
        plan['data_closure_basis']='Following native bar must exist as well as nominal close time passing.'
        plan.setdefault('collector_recovery_history',[]).append({'archive':recovery,'original_plan_sha256':original_plan_sha,
            'reason':'Repair unconfirmed, unevaluated final native rows; preserve every forecast and original start/deadline.'})
        save_signed(directory,'plan',plan)
        if review_contract is not None:
            save_signed(directory,'outcome_review_contract',rebind_contract(review_contract,original_plan_sha,digest(directory/'plan.json')))
        atomic_json(directory/'closed_frames.json',trimmed)
        state['plan_sha256']=digest(directory/'plan.json');state['frame_hash']=digest(directory/'closed_frames.json')
        save_signed(directory,'checkpoint',state);shutil.copyfile(ROOT/runner,old_runner)
        save_signed(directory,'source_snapshot_receipt',{'plan_sha256':digest(directory/'plan.json'),
            'source_files':len(plan['source_hashes']),'source_hashes':plan['source_hashes']})
        receipt={'reason':'Only unreferenced tail removed. Original data and code archived. No evaluated candle or forecast rewritten.',
            'original_plan_sha256':original_plan_sha,'new_plan_sha256':digest(directory/'plan.json'),
            'dropped_unconfirmed_bars':dropped,'retained_forecasts':forecast_counts,'retained_bars_evaluated':state['bars_evaluated'],
            'original_start':plan['start'],'original_deadline':plan['deadline'],'model_rules_changed':False,
            'registration_reset':False,'orders_sent':0,'broker_eligible':False}
        save_signed(archive,'receipt',receipt)
        atomic_json(directory/'status.json',{'state':'reviewed_waiting_for_resume','checked_at':datetime.now(timezone.utc).isoformat(),
            'forecasts':forecast_counts,'bars_evaluated':state['bars_evaluated'],'qualification_cases':0,'orders_sent':0,'broker_eligible':False})
        (ROOT/'docs/FORECAST_CLOSURE_RECOVERY_20261126.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(receipt))


if __name__=='__main__':run()
