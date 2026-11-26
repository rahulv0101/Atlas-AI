"""Recompute historical lifecycle proof from saved evidence. No broker calls."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from tools.observe_day_trading import protected_positions, lifecycle_summary


def audit_journal(path, seen, decisions):
    path=Path(path);before=path.stat();sha=hashlib.sha256()
    positions={r['position_id'] for r in seen.values()}
    timelines={p:{} for p in positions};raw_fills={};last_open=None
    for raw in path.open('rb'):
        sha.update(raw)
        row=json.loads(raw)
        if row.get('broker_ok') is not True:continue
        at=row['observed_at']
        if datetime.fromisoformat(at).tzinfo is None:raise ValueError('aware_observation_timestamp_required')
        last_open={str(p['position_id']) for p in row.get('positions',[])}
        for pos in protected_positions(row.get('positions',[])) & positions:
            timelines[pos].setdefault('protected_at',at)
        for fill in row.get('new_deals',[]):
            if fill.get('position_id') not in positions:continue
            raw_fills[fill['ticket']]=fill
            key='entry_observed_at' if fill.get('entry')==0 else 'exit_observed_at'
            timelines[fill['position_id']].setdefault(key,at)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('journal_changed_during_audit_retry_without_reset')
    # A checkpoint can only summarize fills actually preserved in the journal.
    for ticket, fill in seen.items():
        if raw_fills.get(ticket)!=fill:raise ValueError('checkpoint_fill_missing_or_different_in_journal')
    cycles=lifecycle_summary(seen,decisions,last_open or set()) if last_open is not None else []
    verified=[]
    for cycle in cycles:
        timeline=timelines[cycle['position_id']]
        times=[timeline.get(k) for k in ('entry_observed_at','protected_at','exit_observed_at')]
        parsed=[datetime.fromisoformat(at) for at in times] if all(times) else []
        if parsed and parsed==sorted(parsed):
            verified.append({**cycle,**timeline})
    return {'journal_sha256':sha.hexdigest(),'recomputed_closed_cycles':len(cycles),
            'verified_protected_cycles':verified,'protected_lifecycle_count':len(verified),
            'scope':'Historical guarded entry, observed SL/TP, balanced broker exit and subsequently flat position.',
            'current_build_verified':False,'new_model_verified':False,'active_trailing_management_proven':False,
            'profitability_proven':False,'orders_sent':0,'broker_eligible':False}


def main():
    from atlas_ai.config.settings import load_settings
    from atlas_ai.learning.observation_checkpoint import load_checkpoint
    from atlas_ai.learning.decision_index import GuardedDecisionIndex
    from atlas_ai.atomic_files import atomic_json
    cfg=load_settings()
    plan=json.loads((Path(cfg.storage_dir)/'acceptance_plan.json').read_text())
    journal=Path(plan['journal'])
    _,seen,_,_=load_checkpoint(journal.with_suffix('.checkpoint.json'),cfg,journal=journal)
    result=audit_journal(journal,seen,GuardedDecisionIndex(cfg).events())
    atomic_json(Path(cfg.storage_dir)/'historical_lifecycle_audit.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
