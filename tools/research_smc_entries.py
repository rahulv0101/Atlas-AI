"""Matched, frozen two-hypothesis SMC research. Never activate a broker model."""
from pathlib import Path
import argparse,json,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pandas as pd
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.strategies import smc_entry_models as models
from atlas_ai.testing.smc_validation import HistoricalFeed,historical
from atlas_ai.testing.historical_broker import BrokerSpec
from tools.smc_validation import validate,evaluator_for
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny


class PredictionReader:
    def __init__(self,path,model):self.stream=Path(path).open(encoding='utf-8');self.model=model;self.item=None
    def close(self):self.stream.close()
    def __call__(self,frame,context,quote,now):
        while self.item is None or pd.Timestamp(self.item['now'])<now:
            line=self.stream.readline()
            if not line:raise ValueError('prediction_missing_for_replay_time')
            self.item=json.loads(line)
        if pd.Timestamp(self.item['now'])!=now or self.item['quote']!=quote:
            raise ValueError('prediction_quote_or_time_changed')
        if pd.Timestamp(self.item['input_last_bar'])!=pd.Timestamp(frame.time.iloc[-1]):raise ValueError('prediction_bar_changed')
        return self.item['predictions'][self.model]


def training_selection(results):
    qualified=[name for name,r in results.items() if r['stages']['development']['review_passed']]
    qualified.sort(key=lambda name:(-results[name]['stages']['development']['mean_r'],name))
    return {'selected_for_forward_paper':qualified[0] if qualified else None,'development_qualified':qualified,
        'selected_for_broker':None,'broker_eligible':False,'automatic_broker_activation':False}


def run(directory):
    protocol=signed(directory,'protocol')
    if protocol['models']!=list(models.MODELS) or protocol['broker_eligible'] is not False:raise ValueError('comparison_protocol_changed')
    manifests={name:validate(directory/name) for name in models.MODELS}
    first=manifests[models.MODELS[0]];inputs=signed(directory/models.MODELS[0],'inputs')
    for name,m in manifests.items():
        if m['model']!=name or m.get('paper_activation_requested') is not False:raise ValueError('research_only_preparation_required')
        for key in ['settings','spec','limits','history_start','history_end','source_hashes']:
            if m[key]!=first[key]:raise ValueError('unmatched_comparison:'+key)
        if signed(directory/name,'inputs')!=inputs:raise ValueError('unmatched_candles')
    frames={}
    for tf,expected in inputs.items():
        path=directory/models.MODELS[0]/(tf+'.csv')
        if digest(path)!=expected:raise ValueError('input_changed')
        frames[tf]=pd.read_csv(path);frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
    cfg=settings_for(first,str(directory/'unused_no_writes'));spec=BrokerSpec(**first['spec'])
    f=frames['M5'].reset_index(drop=True);times=pd.to_datetime(f.time,utc=True);feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES})
    start=pd.Timestamp(first['history_start']);end=pd.Timestamp(first['history_end']);bounds=[start+(end-start)*.6,start+(end-start)*.8,end]
    calendar=DayTradingSessionControl();context_key=None;context_cache=None
    predictions=directory/'predictions.jsonl'
    if predictions.exists():raise FileExistsError('new_comparison_predictions_required')
    counts={name:{} for name in models.MODELS};samples=0;equivalence_checks=0;original=models.context_observation
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny),predictions.open('w',encoding='utf-8') as out:
        for i in range(80,len(f)-12):
            now=times.iloc[i]+pd.Timedelta(minutes=5)
            if not start<=now<end:continue
            session=calendar._detect_session(now.to_pydatetime())
            if not session.allowed or session.minutes_to_close<70:continue
            stage=next(j for j,b in enumerate(bounds) if now<b)
            if times.iloc[i+12]+pd.Timedelta(minutes=5)>bounds[stage]:continue
            if times.iloc[i+1]!=now or not times.iloc[i-79:i+13].diff().dropna().eq(pd.Timedelta(minutes=5)).all():continue
            feed.now=now;key=now.floor('15min')
            if context_key!=key:context_cache=collect(feed,now,broker_timezone=cfg.mt5_server_timezone or 'UTC');context_key=key
            context={**context_cache,'evaluated_at':now.isoformat()};window=f.iloc[i-79:i+1]
            quote={'bid':float(f.open.iloc[i+1]),'ask':float(f.open.iloc[i+1])+float(f.spread.iloc[i])*spec.point,'point':spec.point,'at':now.isoformat()}
            shared=[]
            def observe(*args):
                if not shared:shared.append(original(*args))
                return shared[0]
            with patch.object(models,'context_observation',observe):
                values={name:evaluator_for(manifests[name])(window,context,quote,now) for name in models.MODELS}
            if i%500==0:
                for name in models.MODELS:
                    if values[name]!=evaluator_for(manifests[name])(window,context,quote,now):raise AssertionError('shared_context_changed_predictions')
                equivalence_checks+=1
            out.write(json.dumps({'now':now.isoformat(),'input_last_bar':times.iloc[i].isoformat(),'quote':quote,'predictions':values},allow_nan=False)+'\n')
            samples+=1
            for name,v in values.items():
                reason=v['stage']+':'+v['reason'];counts[name][reason]=counts[name].get(reason,0)+1
            if i%100==0:out.flush();atomic_json(directory/'progress.json',{'phase':'predictions_before_labels','bar':i,'bars':len(f),'sampled_windows':samples,'reason_counts':counts})
    save_signed(directory,'prediction_receipt',{'sha256':digest(predictions),'sampled_windows':samples,'equivalence_checks':equivalence_checks,
        'protocol_sha256':digest(directory/'protocol.json'),'prediction_phase_completed_before_labels':True,
        'future_timestamp_use':'shared_input_outcome_continuity_screen_only_no_future_high_low_close_features'})
    results={}
    for name,m in manifests.items():
        receipt=signed(directory,'prediction_receipt')
        if digest(predictions)!=receipt['sha256']:raise ValueError('predictions_changed')
        reader=PredictionReader(predictions,name)
        try:
            with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny):
                r=historical(frames,cfg,spec,m['limits'],start,end,evaluator=reader,context_provider=lambda now:{},
                    progress=lambda **kw:atomic_json(directory/'progress.json',{'phase':'outcome_labels','model':name,**kw}))
        finally:reader.close()
        if digest(predictions)!=receipt['sha256']:raise ValueError('predictions_changed_during_labels')
        r.update(model=name,reason_counts=counts[name],prediction_receipt_sha256=digest(directory/'prediction_receipt.json'))
        save_signed(directory/name,'history',r);results[name]=r
    selection=training_selection(results)
    report={'schema':'atlas_smc_entry_comparison_result_v1','selection':selection,'models':{name:{'stages':r['stages'],'counts':r['counts'],'reason_counts':r['reason_counts']} for name,r in results.items()},
        'broker_eligible':False,'orders_sent':0,'data_status':protocol['data_status'],'protocol_sha256':digest(directory/'protocol.json')}
    save_signed(directory,'report',report);print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,required=True);a=p.parse_args();run(a.run_dir.resolve())
