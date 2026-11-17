"""Reproduce the fixed deployed-M5 simulations and explain losses; no orders."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.indicators import atr
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant,simulate
from atlas_ai.execution.session_control import DayTradingSessionControl
from tools.diagnose_structural_strategy import path_excursions
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny


def summarize(trades):
    wins=[t['net_cash'] for t in trades if t['net_cash']>0]
    losses=[-t['net_cash'] for t in trades if t['net_cash']<0]
    aw=statistics.mean(wins) if wins else None
    al=statistics.mean(losses) if losses else None
    return {'trades':len(trades),'wins':len(wins),'losses':len(losses),'flat':len(trades)-len(wins)-len(losses),
        'net_cash':sum(t['net_cash'] for t in trades),'mean_win_cash':aw,'mean_loss_cash':al,
        'observed_win_rate':len(wins)/len(trades) if trades else None,
        'break_even_win_rate_at_observed_payoffs':al/(aw+al) if aw is not None and al is not None else None,
        'losing_first_bar_stops':sum(t['net_cash']<0 and t['exit_reason']=='stop_loss' and t['entry_bar']==t['exit_bar'] for t in trades),
        'ambiguous_stop_first':sum(bool(t.get('ambiguous_stop_first')) for t in trades),
        'exit_reasons':dict(Counter(t['exit_reason'] for t in trades))}


def diagnose(study,data,output):
    protocol,report=signed(study,'protocol'),signed(study,'report')
    if report['protocol_sha256']!=digest(study/'protocol.json') or report['candidate_receipt_sha256']!=digest(study/'candidates.json'):
        raise ValueError('study_receipts_changed')
    if report.get('orders_sent')!=0 or report.get('broker_eligible') is not False:
        raise ValueError('research_only_required')
    if digest(data/'M5.csv')!=protocol['historical_inputs']['M5']:
        raise ValueError('candles_changed')
    root=Path(__file__).resolve().parents[1]
    for name,expected in protocol['source_hashes'].items():
        if name.replace('\\','/').startswith('atlas_ai/') and digest(root/name)!=expected:
            raise ValueError('shared_policy_changed')
    output.mkdir(exist_ok=False)
    frame=pd.read_csv(data/'M5.csv');execution=frame.copy();execution['spread']=frame.spread.shift(1)
    candidates=signed(study,'candidates')['rows']; lookup={row['index']:row for row in candidates}
    spec=BrokerSpec(**protocol['broker_spec']); groups=defaultdict(list); traces=[]
    calendar=DayTradingSessionControl()
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory() as temp:
        cfg=settings_for(protocol,temp)
        for trade in report['diagnostic']['trade_list']:
            i=trade['entry_bar']-1;row=lookup[i]
            signal=next(s for s in row['signals'] if s['strategy']==trade['strategy'])
            chosen=TradeSignal(**signal);chosen.confidence=trade['confidence']
            session=calendar._detect_session(pd.Timestamp(trade['entry_at']).to_pydatetime())
            held=min(cfg.backtest_max_hold_bars,(session.minutes_to_close-10)//5)
            actual=simulate(execution,trade['entry_bar'],chosen,trade['volume'],spec,cfg,
                ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                last_index=trade['entry_bar']+held-1 if held<cfg.backtest_max_hold_bars else None)
            for key in ['entry_bar','exit_bar','exit_reason']:
                if actual[key]!=trade[key]:raise ValueError('reproduction_mismatch:'+key)
            for key in ['entry_price','exit_price','net_cash','initial_risk_cash']:
                if abs(actual[key]-trade[key])>1e-6:raise ValueError('reproduction_mismatch:'+key)
            volatility=float(atr(frame.iloc[max(0,i-1199):i+1]).iloc[-1])
            distance=trade['initial_risk_cash']/abs(spec.cash(-1.,trade['volume']))
            trace={**trade,'stop_price_distance':distance,'preceding_closed_ATR':volatility,
                'stop_to_preceding_ATR':distance/volatility if volatility>0 else None,
                'initial_target_R':signal['take_profit_points']/signal['stop_loss_points'],
                'path':path_excursions(execution,trade,spec),'reproduced':True}
            traces.append(trace)
            for field in ['strategy','session','side','exit_reason']:groups[field+':'+str(trade[field])].append(trade)
    result={'state':'completed_fixed_sample_diagnosis','summary':summarize(traces),
        'groups':{k:summarize(v) for k,v in groups.items()},'trades':traces,
        'median_stop_to_preceding_ATR':statistics.median(t['stop_to_preceding_ATR'] for t in traces if t['stop_to_preceding_ATR'] is not None),
        'median_stop_price_distance':statistics.median(t['stop_price_distance'] for t in traces),
        'median_preceding_closed_ATR':statistics.median(t['preceding_closed_ATR'] for t in traces),
        'source_report_sha256':digest(study/'report.json'),'source_protocol_sha256':digest(study/'protocol.json'),
        'candles_sha256':digest(data/'M5.csv'),'diagnostic_source_sha256':digest(Path(__file__)),
        'orders_sent':0,'policy_changed':False,'broker_eligible':False,
        'limits':['Previously inspected reused history; descriptive, not independent validation.',
            'No exit-bar favorable excursion is used; intrabar tick ordering is unknown.',
            'Frozen broker conversion and modeled costs, not measured natural fill costs.',
            'Subgroup winners are not permission to select or activate a hindsight filter.']}
    save_signed(output,'report',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['study','data','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    result=diagnose(args.study,args.data,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ['trades','groups']}))
