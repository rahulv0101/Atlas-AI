"""Reconstruct reported retest near misses without orders or policy changes."""
import json
from pathlib import Path
import pandas as pd
from atlas_ai.data.top_down import collect, TIMEFRAMES
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.testing.sweep_bos_retest import evaluate
from tools.learn_candidate_ranker import signed, digest, save_signed
from tools.research_entry_horizon import load_frames


def run(root):
    study = root/'storage/sweep_bos_retest_v10_20261116'
    protocol = signed(study,'protocol')
    receipt = signed(study,'prediction_receipt')
    if digest(study/'observations.jsonl') != receipt['observations_sha256']:
        raise ValueError('observations_changed')
    frames = load_frames(root/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',protocol['input_hashes']['primary'])
    feed = HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES})
    cases = []
    for line in (study/'observations.jsonl').read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['period'] != 'primary' or row['observation']['stage'] != 'retest':
            continue
        now = pd.Timestamp(row['available_at'])
        f = frames['M5']
        i = f.index[f.time == now-pd.Timedelta(minutes=5)][0]
        feed.now = now
        ctx = collect(feed,now,broker_timezone=protocol['settings']['mt5_server_timezone'] or 'UTC')
        bid, point = float(f.open.iloc[i+1]),protocol['spec']['point']
        quote = {'bid':bid,'ask':bid+float(f.spread.iloc[i])*point,'point':point,'at':now.isoformat()}
        result = evaluate(f.iloc[max(0,i-1199):i+1],ctx,quote,now)
        cases.append({'at':now.isoformat(),'reported_reason':row['observation']['reason'],
            'reproduced_reason':result['reason'],'candidate':bool(result.get('candidate')),
            'last_candles':json.loads(f.iloc[i-6:i+1].to_json(orient='records',date_format='iso'))})
    output = study/'near_miss_audit'
    output.mkdir(exist_ok=False)
    save_signed(output,'report',{'source_observations_sha256':receipt['observations_sha256'],
        'cases':cases,'orders_sent':0,'policy_changed':False,
        'all_reasons_reproduced':all(c['reported_reason']==c['reproduced_reason'] for c in cases)})
    print(json.dumps({'cases':len(cases),'all_reasons_reproduced':all(c['reported_reason']==c['reproduced_reason'] for c in cases)}))


if __name__ == '__main__':
    run(Path(__file__).resolve().parents[1])
