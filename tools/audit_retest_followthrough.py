"""Quote-barrier diagnostic on saved entries; no new execution or return claims."""
import json
from pathlib import Path
from collections import Counter
import pandas as pd
from tools.learn_candidate_ranker import signed,save_signed,digest
from tools.cost_aware_strategy_audit import prepare_frame
ROOT=Path(__file__).resolve().parents[1]


def first_barrier(frame,trade,stop_points,point,horizon=12):
    side=1 if trade['side']=='buy' else -1
    distance=stop_points*point;entry=trade['entry_price']
    stop=entry-side*distance;target=entry+side*2*distance
    first=trade['entry_bar'];last=min(len(frame),first+horizon)
    times=pd.to_datetime(frame.time.iloc[first:last],utc=True)
    if not times.diff().dropna().eq(pd.Timedelta(minutes=5)).all():return 'coverage_gap'
    for i in range(first,last):
        row=frame.iloc[i];offset=float(row.spread)*point if side==-1 else 0.
        low,high=float(row.low)+offset,float(row.high)+offset
        hit_stop=low<=stop if side==1 else high>=stop
        hit_target=high>=target if side==1 else low<=target
        if hit_stop:return 'ambiguous_stop_first' if hit_target else 'initial_stop_first'
        if hit_target:return 'two_R_first'
    return 'neither_within_one_hour' if last-first==horizon else 'coverage_gap'


def run():
    source=ROOT/'storage/retest_capital_20261126T081720Z';p=signed(source,'protocol')
    setups=ROOT/'storage/complete_retest_setup_20261126T081014Z'
    locations={'earlier':ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5','recent':ROOT/'storage/today_learning_replay_20261123_v2'}
    result={}
    for period,folder in locations.items():
        file=folder/'M5.csv';assert digest(file)==p['inputs'][period]['M5']
        frame=prepare_frame(pd.read_csv(file));frame['spread']=frame.spread.shift(1)
        rows=signed(setups,period+'_setups')['rows'];index={r['available_at']:r for r in rows}
        trades=signed(source,period+'_base')['trade_list']
        result[period]=dict(Counter(first_barrier(frame,t,index[t['entry_at']]['signals'][0]['stop_loss_points'],p['spec']['point']) for t in trades))
    report={'state':'completed_diagnostic','results':result,'scope':'First quote-side barrier over 12 M5 bars, without break-even/trailing/time exits.',
            'limitations':['Barrier counts are not executable returns or qualification. Costs and session cutoff are not reproduced by this diagnostic.',
                           'M5 bars cannot establish intrabar order; ambiguous bars are stop-first.'],
            'orders_sent':0,'broker_eligible':False,'live_policy_changed':False}
    out=ROOT/'storage/retest_followthrough_audit';out.mkdir(exist_ok=True);save_signed(out,'report',report)
    print(json.dumps(report))


if __name__=='__main__':run()
