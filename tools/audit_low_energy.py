"""Freeze and run a read-only historical diagnostic of the low-energy veto."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.low_energy_audit import METHOD,current_audit,evaluate,summarize_publications
from atlas_ai.testing.decision_archive import index_rows
from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.penalty_shadow import read_record
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import signed,save_signed,digest,deny


def run(output):
    settings=load_settings(); storage=Path(settings.storage_dir)
    if settings.timeframe!='M1':raise ValueError('M1_required')
    reference=Path(json.loads((storage/'guarded_research_active.json').read_text())['run_dir']).resolve()
    reference.relative_to(storage.resolve()); old=signed(reference,'manifest')
    if old['settings']['symbol']!=settings.symbol or old['settings']['timeframe']!=settings.timeframe:
        raise ValueError('historical_market_mismatch')
    source=reference/'candles.csv'
    if digest(source)!=old['input_sha256']:raise ValueError('historical_candles_changed')
    output.resolve().relative_to(storage.resolve())
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(source,output/'candles.csv')
    if digest(output/'candles.csv')!=old['input_sha256']:raise ValueError('copied_candles_changed')
    hashes={}
    for folder in ['atlas_ai','tools']:
        for path in (ROOT/folder).rglob('*.py'):
            relative=path.relative_to(ROOT);target=output/'frozen_source'/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            hashes[relative.as_posix()]=digest(path)
    status=json.loads((storage/'status.json').read_text(encoding='utf-8'))
    manifest={'schema':'atlas_low_energy_audit_v1','frozen_at':datetime.now(timezone.utc).isoformat(),
        'method':METHOD,'settings':safe_settings(settings),'source_sha256':digest(output/'candles.csv'),
        'reference_manifest_sha256':digest(reference/'manifest.json'),'source_hashes':hashes,
        'broker_reference_frozen_at':old['frozen_at'],'spec':old['spec'],
        'broker_eligible':False,'automatic_promotion':False,'orders_sent':0}
    save_signed(output,'manifest',manifest)
    frame=prepare_frame(pd.read_csv(output/'candles.csv'))
    last_progress=[0]
    def progress(**data):
        if data['sampled_windows']-last_progress[0]>=100:
            atomic_json(output/'progress.json',data);print(json.dumps(data),flush=True);last_progress[0]=data['sampled_windows']
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny):
        report=evaluate(frame,settings,BrokerSpec(**old['spec']),progress=progress)
    report['current_audit']=current_audit(settings,status)
    report['input_bars']=len(frame); report['first_bar']=str(frame.time.iloc[0]);report['last_bar']=str(frame.time.iloc[-1])
    report['manifest_sha256']=digest(output/'manifest.json')
    try:
        archive=storage/'replay_evidence'
        with observation_lock(archive/'archive.lock'):
            records=[read_record(archive,row) for row in index_rows(archive)[-300:]]
        report['recent_publications']=summarize_publications(records)
    except RuntimeError:
        report['recent_publications']={'state':'archive_busy_not_sampled'}
    atomic_json(output/'report.json',report)
    print(json.dumps({'state':'completed_diagnostic_only','report':str(output/'report.json'),
        'counts':report['counts'],'strategies':report['strategies'],'policy_changes':[]}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
