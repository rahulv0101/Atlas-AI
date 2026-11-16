"""One frozen structural-entry experiment against verified existing baseline evidence."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import replay
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.testing.structural_retest import evaluate,NAME,RULES
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for
from tools.m5_calibration_study import load_reused_frames,deny
from tools.m5_stop_research import review


def verify_source(source,tick_audit):
    p=signed(source,'protocol');r=signed(source,'report');tick=signed(tick_audit,'protocol')
    if r['state']!='completed_research_only' or r['protocol_sha256']!=digest(source/'protocol.json'):raise ValueError('verified_baseline_required')
    if tick['source_report_sha256']!=digest(source/'report.json'):raise ValueError('tick_audit_source_changed')
    if tick['structural_rules_frozen_before_tick_labels']!=json.loads(json.dumps(RULES)):
        raise ValueError('structural_rules_changed_after_tick_labels')
    if tick['structural_model_sha256']!=digest(ROOT/'atlas_ai/testing/structural_retest.py'):
        raise ValueError('structural_model_changed_after_tick_labels')
    # Reuse prior outcomes only when their full Atlas policy dependencies and
    # source input files still match, not merely because the numbers look useful.
    sources=signed(source,'source_receipt')['source_hashes']
    for name,h in sources.items():
        if name.startswith('atlas_ai/') and digest(ROOT/name)!=h:raise ValueError('baseline_policy_dependency_changed:'+name)
        if digest(source/'frozen_source'/name)!=h:raise ValueError('baseline_frozen_source_changed')
    if r['prediction_receipt_sha256']!=digest(source/'prediction_receipt.json'):raise ValueError('baseline_receipt_changed')
    return p,r,tick


def run(source,tick_audit,output):
    p,baseline,tick=verify_source(source,tick_audit)
    output=output.resolve();output.relative_to(Path(p['project_root'])/'storage');output.mkdir(parents=True,exist_ok=False)
    for folder in ['atlas_ai','tools']:
        for path in (ROOT/folder).rglob('*.py'):
            target=output/'frozen_source'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    protocol={'schema':'atlas_structural_retest_research_v1','frozen_at':datetime.now(timezone.utc).isoformat(),
        'model':NAME,'rules':RULES,'source_report_sha256':digest(source/'report.json'),
        'source_protocol_sha256':digest(source/'protocol.json'),'tick_audit_protocol_sha256':digest(tick_audit/'protocol.json'),
        'windows':{k:p[k] for k in ['development_start','split','validation_end']},'settings':p['settings'],'spec':p['spec'],'limits':p['limits'],
        'selection':'One fixed model, no search or retuning. Both periods need >=30 trades across >=2 dates, positive mean net R, PF>=1.1 or all wins, drawdown<=6R.',
        'volatility_policy':'Unchanged live guard; prior calibrated M5 proposal is not used.',
        'data_status':'Reused and inspected retrospective data; not blind validation.',
        'baseline_reuse':'Previously completed outcome artifact with matching input and full Atlas dependency hashes; not newly generated evidence.',
        'broker_eligible':False,'auto_promotion':False,'orders_sent':0,'forward_required':True,
        'limitations':['No historical visual/macro/news state or natural broker fills are reconstructed. Shared deterministic research gates do not establish full live-pipeline parity.',
            'Protection derives from a structural level/retest convention, not proof of institutional orders. This model does not require FVG/order-block detection.',
            'Fixed research confidence is not a win probability. Costs/currency/margin use the same frozen approximation as the baseline.']}
    save_signed(output,'protocol',protocol)
    save_signed(output,'source_receipt',{'protocol_sha256':digest(output/'protocol.json'),
        'hashes':{f.relative_to(output/'frozen_source').as_posix():digest(f) for f in (output/'frozen_source').rglob('*.py')}})
    storage=Path(p['project_root'])/'storage'
    atomic_json(storage/'structural_research_active.json',{'run_dir':str(output),'tick_audit_dir':str(tick_audit.resolve())})
    def progress(phase,**kw):atomic_json(output/'progress.json',{'phase':phase,'checked_at':datetime.now(timezone.utc).isoformat(),**kw})
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory(prefix='isolated_',dir=output) as temp:
        # Raw data reuse validates all six original native inputs, including M1.
        frames=load_reused_frames(source,p)
        frame=frames['M5'];times=pd.to_datetime(frame.time,utc=True);feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES})
        cfg=settings_for(p,temp);spec=BrokerSpec(**p['spec']);trader=AtlasTrader.__new__(AtlasTrader)
        rows=[];counts=Counter();context_key=None;higher=None
        start=pd.Timestamp(p['development_start']);split=pd.Timestamp(p['split']);end=pd.Timestamp(p['validation_end'])
        with (output/'predictions.jsonl').open('w',encoding='utf-8') as stream:
            for i in range(250,len(frame)-1):
                now=times.iloc[i]+pd.Timedelta(minutes=5)
                if now<start or now>=end:continue
                if times.iloc[i+1]!=now:counts['missing_next_M5_open']+=1;continue
                key=now.floor('15min')
                if key!=context_key:
                    feed.now=now;higher=collect(feed,now,broker_timezone=cfg.mt5_server_timezone or 'UTC');context_key=key
                context={**higher,'evaluated_at':now.isoformat()}
                bid=float(frame.open.iloc[i+1]);quote={'bid':bid,'ask':bid+float(frame.spread.iloc[i])*spec.point,'point':spec.point,'at':now.isoformat()}
                observation=evaluate(frame.iloc[max(0,i-79):i+1],context,quote,now)
                counts[observation['stage']+':'+observation['reason']]+=1
                stream.write(json.dumps({'index':i,'available_at':now.isoformat(),'last_closed_bar_utc':times.iloc[i].isoformat(),
                    'observation':observation},allow_nan=False)+'\n')
                if observation['candidate']:
                    rows.append({'index':i,'available_at':now.isoformat(),'signals':[observation['candidate']],
                        'regime':trader._market_regime(list(frame.close.iloc[max(0,i-59):i+1])),
                        'higher_tf_bias':context['bias'],'higher_context':context})
                if i%250==0:progress('structural_predictions_before_labels',bar=i,bars=len(frame),complete_candidates=len(rows))
        save_signed(output,'candidate_cache',{'rows':rows,'counts':dict(counts)})
        save_signed(output,'prediction_receipt',{'predictions_sha256':digest(output/'predictions.jsonl'),
            'candidate_sha256':digest(output/'candidate_cache.json'),'protocol_sha256':digest(output/'protocol.json'),
            'prediction_phase_completed_before_labels':True})
        execution=frame.copy();execution['spread']=frame.spread.shift(1)
        result={'schema':'atlas_structural_retest_result_v1','state':'running','model':NAME,'counts':dict(counts),
                'complete_candidates':len(rows),'periods':{},'broker_eligible':False,'auto_promotion':False,'orders_sent':0}
        for name,begin,finish in [('development',start,split),('validation',split,end)]:
            progress('shared_policy_replay',period=name)
            stats=replay(execution,rows,cfg,spec,ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                KnowledgeStore(temp),p['limits'],start=begin.to_pydatetime(),end=finish.to_pydatetime())
            stats['review']=review(stats)
            old=baseline['results'][name]['repaired_baseline']
            result['periods'][name]={'structural_proposal':stats,'verified_baseline':old}
            save_signed(output,'report',result)
        result.update(state='completed_research_only',historical_review_passed=all(v['structural_proposal']['review']['passed'] for v in result['periods'].values()),
            selected_for_live=None,protocol_sha256=digest(output/'protocol.json'),prediction_receipt_sha256=digest(output/'prediction_receipt.json'))
        if digest(output/'predictions.jsonl')!=signed(output,'prediction_receipt')['predictions_sha256']:raise ValueError('predictions_changed')
        save_signed(output,'report',result);progress('completed_research_only')
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--tick-audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:r=run(args.source.resolve(),args.tick_audit.resolve(),args.output.resolve())
    except Exception as exc:
        if args.output.exists():atomic_json(args.output/'progress.json',{'phase':'failed','checked_at':datetime.now(timezone.utc).isoformat(),'error':type(exc).__name__,'reason':str(exc)})
        raise
    print(json.dumps({'state':r['state'],'complete_candidates':r['complete_candidates'],'historical_review_passed':r['historical_review_passed']}))
