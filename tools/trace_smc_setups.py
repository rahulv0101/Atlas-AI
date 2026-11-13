"""Capture real late-stage SMC failures without altering detector output."""
import argparse
from pathlib import Path
import sys,json
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.testing.smc_validation import historical
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.strategies import smc_retest
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny


def records(frame):
    return json.loads(frame.to_json(orient='records',date_format='iso',double_precision=12))


def run(source,output):
    output.mkdir(parents=True,exist_ok=False);m=signed(source,'manifest');inputs=signed(source,'inputs');frames={}
    for tf,expected in inputs.items():
        p=source/(tf+'.csv')
        if digest(p)!=expected:raise ValueError('source_changed')
        frames[tf]=pd.read_csv(p);frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
    save_signed(output,'manifest',{'mode':'diagnostic_only_no_model_changes','source_manifest_sha256':digest(source/'manifest.json'),
        'model_sha256':digest(ROOT/'atlas_ai/strategies/smc_retest.py'),'engine_sha256':digest(ROOT/'atlas_ai/strategies/smc_composite.py'),
        'inputs':inputs,'broker_eligible':False,'orders_sent':0})
    traces=[];original=smc_retest.first_retest;reason_counts={}
    def traced(frame,context,quote,now):
        calls=[]
        def inspect(bars,zones,side,extreme):
            result=original(bars,zones,side,extreme)
            calls.append({'bars':records(bars),'zones':zones,'side':side,'extreme':extreme,'result':result})
            return result
        with patch.object(smc_retest,'first_retest',inspect):result=smc_retest.evaluate(frame,context,quote,now)
        if calls:
            if result!=smc_retest.evaluate(frame,context,quote,now):raise AssertionError('trace_changed_model_output')
            traces.append({'at':now.isoformat(),'frame':records(frame),'context':context,'quote':quote,'result':result,'retest_calls':calls})
            atomic_json(output/'setups.json',traces)
        key=result['stage']+':'+result['reason'];reason_counts[key]=reason_counts.get(key,0)+1
        return result
    cfg=settings_for(m,str(output/'unused_no_writes'))
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny):
        result=historical(frames,cfg,BrokerSpec(**m['spec']),m['limits'],pd.Timestamp(m['history_start']),pd.Timestamp(m['history_end']),
            evaluator=traced,progress=lambda **kw:atomic_json(output/'progress.json',kw))
    report={'reason_counts':reason_counts,'late_stage_windows':len(traces),'counts':result['counts'],'stages':result['stages'],
        'broker_eligible':False,'orders_sent':0,'trace_equivalence_checked':True}
    atomic_json(output/'report.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.source,a.output)
