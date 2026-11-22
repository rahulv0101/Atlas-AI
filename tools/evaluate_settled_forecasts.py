"""Evaluate recorded candidates against retained settled bid candles; never broker trades."""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import time
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.learn_candidate_ranker import signed,save_signed,digest


def paper_outcome(record, signal, bars, protocol):
    if signal.get('side') not in ('buy','sell'):return {'state':'not_directional'}
    observed=pd.Timestamp(record['observed_at']);entry_at=pd.Timestamp(record['scheduled_entry_at'])
    if observed.tzinfo is None or entry_at.tzinfo is None or entry_at<=observed:raise ValueError('future_entry_required')
    point=float(record['quote']['point']);stop=float(signal['stop_loss_points'])*point;target=float(signal['take_profit_points'])*point
    if not all(math.isfinite(x) and x>0 for x in (point,stop,target)):raise ValueError('valid_geometry_required')
    horizon=int(protocol['horizon_bars']);future=[(pd.Timestamp(k),v) for k,v in sorted(bars.items()) if pd.Timestamp(k)>=entry_at][:horizon]
    if not future or future[0][0]!=entry_at:return {'state':'pending_or_missing_entry'}
    for i,(at,bar) in enumerate(future):
        if at!=entry_at+pd.Timedelta(minutes=5*i):return {'state':'incomplete_candle_sequence'}
        if not all(math.isfinite(float(bar[k])) for k in ('open','high','low','close','spread')):raise ValueError('invalid_price')
        if not 0<float(bar['low'])<=min(float(bar['open']),float(bar['close']))<=max(float(bar['open']),float(bar['close']))<=float(bar['high']) or float(bar['spread'])<0:raise ValueError('invalid_ohlc')
    buy=signal['side']=='buy';direction=1 if buy else -1
    first=future[0][1];spread=float(first['spread'])*point;slip=float(protocol['slippage_points_per_side'])*point
    entry=float(first['open'])+(spread if buy else 0)+direction*slip
    stop_price=entry-direction*stop;target_price=entry+direction*target
    for index,(at,bar) in enumerate(future):
        # MT5 bars are bid; sell exits use a modeled per-bar ask spread.
        offset=0 if buy else float(bar['spread'])*point
        low=float(bar['low'])+offset;high=float(bar['high'])+offset;opened=float(bar['open'])+offset
        hit_stop=low<=stop_price if buy else high>=stop_price
        hit_target=high>=target_price if buy else low<=target_price
        if hit_stop:
            exit_price=(min(opened,stop_price) if buy else max(opened,stop_price))-direction*slip
            reason='stop_first_ambiguous' if hit_target else 'stop'
        elif hit_target:
            exit_price=target_price-direction*slip;reason='target'
        elif index==horizon-1:
            exit_price=float(bar['close'])+offset-direction*slip;reason='time_exit'
        else:continue
        return {'state':'resolved_paper','exit_reason':reason,'exit_bar_utc':at.isoformat(),
                'entry_at':entry_at.isoformat(),'entry_price_model':entry,'exit_price_model':exit_price,
                'net_r':direction*(exit_price-entry)/stop-float(protocol['additional_cost_r']),
                'bars_held':index+1,'broker_fill_verified':False}
    return {'state':'pending'}


def initialize(directory, source):
    directory.mkdir(parents=True,exist_ok=False)
    save_signed(directory,'protocol',{'source_dir':str(source.resolve()),'source_protocol_sha256':digest(source/'protocol.json'),
        'evaluator_sha256':digest(Path(__file__)),'started_at':datetime.now(timezone.utc).isoformat(),
        'horizon_bars':12,'slippage_points_per_side':3,'additional_cost_r':0.0,
        'cost_caveat':'Per-bar spread and assumed adverse slippage; commissions, swaps and broker fills unverified. Not qualification.',
        'entry_model':'scheduled future M5 bid open; buy pays spread; sell exits modeled ask',
        'ambiguous_bar':'stop_first','broker_eligible':False,'auto_promotion':False})


def once(directory):
    p=signed(directory,'protocol');source=Path(p['source_dir']);sp=signed(source,'protocol')
    if digest(Path(__file__))!=p['evaluator_sha256'] or digest(source/'protocol.json')!=p['source_protocol_sha256']:raise ValueError('frozen_source_changed')
    if sp.get('broker_eligible') is not False:raise ValueError('research_source_required')
    cp_hash=digest(source/'checkpoint.json');cp=signed(source,'checkpoint');journal=source/'forecasts.jsonl'
    if digest(journal)!=cp['journal_sha256']:return {'state':'waiting_for_atomic_source_snapshot','broker_eligible':False}
    records=[json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    results=[]
    for record in records:
        for signal in record['signals']:
            result=paper_outcome(record,signal,cp['bars'],p)
            if result['state']=='not_directional':continue
            results.append({'observed_at':record['observed_at'],'strategy':signal['strategy'],'side':signal['side'],
                'prospective':pd.Timestamp(record['observed_at'])>=pd.Timestamp(p['started_at']),**result})
    if digest(source/'checkpoint.json')!=cp_hash or digest(journal)!=cp['journal_sha256']:
        return {'state':'waiting_for_atomic_source_snapshot','broker_eligible':False}
    resolved=[r for r in results if r['state']=='resolved_paper'];prospective=[r for r in resolved if r['prospective']]
    report={'state':'evaluating_paper_candidates','checked_at':datetime.now(timezone.utc).isoformat(),
        'source_protocol_sha256':p['source_protocol_sha256'],'source_checkpoint_sha256':cp_hash,
        'source_journal_sha256':cp['journal_sha256'],'results':results,'resolved_candidates':len(resolved),
        'prospective_resolved_candidates':len(prospective),'diagnostic_resolved_candidates':len(resolved)-len(prospective),
        'pending_candidates':sum(r['state']!='resolved_paper' for r in results),
        'cost_caveat':p['cost_caveat'],'overlapping_candidates':True,'independent_trade_count':None,
        'strategy_qualified':False,'broker_eligible':False,'auto_promotion':False}
    save_signed(directory,'report',report)
    return {k:v for k,v in report.items() if k!='results'}


def resume(storage, *, start=None):
    import subprocess
    storage=Path(storage).resolve();pointer=storage/'settled_m5_outcomes_active.json'
    if not pointer.exists():return {'state':'not_configured'}
    directory=Path(json.loads(pointer.read_text())['run_dir']).resolve();directory.relative_to(storage)
    p=signed(directory,'protocol');source=Path(p['source_dir']).resolve();source.relative_to(storage)
    if p.get('broker_eligible') is not False or p.get('auto_promotion') is not False:raise ValueError('research_only_required')
    if digest(Path(__file__))!=p['evaluator_sha256']:return {'state':'source_review_required'}
    active=Path(json.loads((storage/'settled_m5_forward_active.json').read_text())['run_dir']).resolve()
    if active!=source:return {'state':'collector_review_required'}
    sp=signed(source,'protocol')
    if datetime.now(timezone.utc)>=datetime.fromisoformat(sp['deadline']):return {'state':'deadline_reached'}
    status=json.loads((directory/'status.json').read_text()) if (directory/'status.json').exists() else {}
    if status.get('state')=='blocked_review_required':return {'state':'blocked_review_required'}
    try:
        with observation_lock(directory/'evaluator.lock'):pass
    except RuntimeError:return {'state':'existing_evaluator_running'}
    python=storage.parent/'.venv/Scripts/pythonw.exe'
    if not python.is_file():raise ValueError('project_pythonw_missing')
    with (directory/'stdout.log').open('a') as out,(directory/'stderr.log').open('a') as err:
        child=(start or subprocess.Popen)([str(python),'-m','tools.evaluate_settled_forecasts','--directory',str(directory),'--watch'],
            cwd=storage.parent,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return {'state':'evaluator_started','pid':child.pid}


def observation_step(directory, *, failures=0, observe=once):
    """Bounded retry of Windows file-sharing errors; never hide integrity errors."""
    try:
        return observe(directory),0,False
    except PermissionError as exc:
        failures+=1
        return {'state':'waiting_for_source_file_access' if failures<3 else 'blocked_review_required',
                'reason':str(exc),'consecutive_file_access_failures':failures,
                'checked_at':datetime.now(timezone.utc).isoformat(),'broker_eligible':False},failures,failures>=3


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--initialize',action='store_true');parser.add_argument('--watch',action='store_true');a=parser.parse_args()
    if a.initialize:
        if a.source is None:parser.error('--source required')
        initialize(a.directory,a.source)
    with observation_lock(a.directory/'evaluator.lock'):
        failures=0
        while True:
            try:status,failures,blocked=observation_step(a.directory,failures=failures)
            except Exception as exc:
                atomic_json(a.directory/'status.json',{'state':'blocked_review_required','reason':str(exc),'broker_eligible':False});raise
            atomic_json(a.directory/'status.json',status);print(json.dumps(status),flush=True)
            if blocked:raise SystemExit(1)
            if not a.watch:break
            time.sleep(20)
