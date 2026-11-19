"""Bounded recorded gate outcomes; never infer results for unreached checks."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
from atlas_ai.memory.jsonl_tail import read_jsonl_tail
from atlas_ai.atomic_files import atomic_json


def summarize(rows):
    counts={name:Counter() for name in ('confluence','timing')}
    actions=Counter();policies=Counter();missing=Counter();directional=0
    for row in rows:
        meta=row.get('meta') or {}
        if (meta.get('chosen') or {}).get('side') not in ('buy','sell'):continue
        directional+=1;actions[str(meta.get('action') or 'unknown')]+=1
        confluence=(meta.get('higher_timeframe') or {}).get('entry_gate') or {}
        timing=meta.get('timing_discipline') or {}
        for name,gate in [('confluence',confluence),('timing',timing)]:
            result=gate.get('passed')
            counts[name]['passed' if result is True else 'failed' if result is False else 'unrecorded']+=1
        policies[str(confluence.get('policy') or 'unrecorded')]+=1
        if timing.get('passed') is False:missing.update(timing.get('missing') or [])
    return {'recorded_publications':len(rows),'directional_publications':directional,
            'actions':dict(actions),'gates':{k:dict(v) for k,v in counts.items()},
            'confluence_policies':dict(policies),'timing_missing':dict(missing),
            'unique_opportunities':None,'live_trade_rate_estimate':None,
            'limitations':'Tail sample only. Publications may repeat a candidate. Unrecorded gates are unknown, never passes. Mixed policy versions are separate counts. No profitability or counterfactual survivorship claim.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--storage',type=Path,default=Path('storage'))
    p.add_argument('--limit',type=int,default=500);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not 1<=a.limit<=10000:raise ValueError('bounded_limit_required')
    report=summarize(read_jsonl_tail(a.storage/'events.jsonl',a.limit))
    report['generated_at']=datetime.now(timezone.utc).isoformat();atomic_json(a.output,report)
    print(json.dumps(report))
