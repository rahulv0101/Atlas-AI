"""Read-only audit of sampled publications; counts are not unique trade setups."""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.testing.decision_archive import index_rows
from tools.penalty_shadow import read_record
from tools.learn_candidate_ranker import save_signed


def audit(storage,now):
    start=now-timedelta(days=7);archive=storage/'replay_evidence';rows=index_rows(archive)
    messages=Counter();missing=Counter();generation=Counter();strategies=Counter();hours=Counter();primary=Counter()
    counts=Counter();chosen_count=0;earliest=latest=None;seen=set();by_day={};policy_counts=Counter()
    for row in rows:
        indexed=row.get('decision_at')
        if indexed:
            indexed=datetime.fromisoformat(indexed.replace('Z','+00:00'))
            if not start<=indexed<=now:continue
        record=read_record(archive,row);status=record['publication'];at=status.get('updated_at')
        if not at:continue
        at=datetime.fromisoformat(at.replace('Z','+00:00'))
        if not start<=at<=now or status.get('timeframe')!='M5':continue
        identity=(status.get('updated_at'),status.get('message'),json.dumps(status.get('chosen'),sort_keys=True))
        if identity in seen:continue
        seen.add(identity);counts['sampled_publications']+=1
        earliest=min(earliest,at) if earliest else at;latest=max(latest,at) if latest else at
        message=str(status.get('primary_blocker') or status.get('message') or 'unknown')
        messages[message]+=1;hour=at.date().isoformat();hours[hour]+=1
        for candidate in (status.get('signal_generation') or {}).get('candidates',[]):
            if candidate.get('suppressed'):
                generation.update(candidate.get('reason_codes') or ['unspecified']);strategies[candidate.get('strategy','unknown')]+=1
        chosen=status.get('chosen') or {};direction=chosen.get('side') in ('buy','sell')
        if direction:
            chosen_count+=1
            timing=status.get('timing_discipline') or {}
            if timing.get('passed') is False:
                counts['chosen_timing_failed']+=1;missing.update(timing.get('missing') or [])
            if timing.get('passed') is True:counts['chosen_timing_passed']+=1
            primary[message]+=1
        else:counts['without_chosen_direction']+=1
        msg=message.lower()
        category=('volatility_guard' if 'volatility protection' in msg else
                  'session_cutoff' if 'session cutoff' in msg else
                  'timing_discipline' if 'timing discipline' in msg else
                  'higher_timeframe' if 'higher' in msg and 'timeframe' in msg else
                  'no_confident_signal' if 'no high-confidence' in msg else 'other')
        counts['primary:'+category]+=1
        day=by_day.setdefault(hour,Counter());day['primary:'+category]+=1
        if direction:
            day['chosen_directional']+=1
            day['timing_passed' if timing.get('passed') is True else 'timing_failed_or_unknown']+=1
        policy_counts[str((status.get('higher_timeframe') or {}).get('policy','unrecorded'))]+=1
    return {'checked_at':now.isoformat(),'window_start':start.isoformat(),'timeframe':'M5',
        'first_captured':earliest.isoformat() if earliest else None,'last_captured':latest.isoformat() if latest else None,
        'counts':dict(counts),'chosen_directional_publications':chosen_count,'primary_messages':messages.most_common(20),
        'directional_primary_messages':primary.most_common(15),'timing_missing':dict(missing),
        'generation_suppression_reasons':dict(generation),'suppressed_strategy_samples':dict(strategies),'publications_per_day':dict(hours),
        'per_day':{day:dict(values) for day,values in by_day.items()},'recorded_htf_policy_samples':dict(policy_counts),
        'limitations':['Sampled post-decision publications, not unique setups or complete atomic gate inputs.',
                       'Primary blockers can coexist with additional failed gates; counts do not predict counterfactual fills.',
                       'M5 only; no pooling older M1 decisions or manual orders.'],
        'orders_sent':0,'live_policy_changed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report=audit(ROOT/'storage',datetime.now(timezone.utc));save_signed(args.output,'report',report)
    print(json.dumps(report,indent=2))
