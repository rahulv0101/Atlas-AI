"""Adjudicate recorded first-bar paths from verified broker quote history; no orders."""
import argparse
from datetime import datetime,timezone
import json
import math
import shutil
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import utc_query_time
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.models import TradeSignal
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.tick_reconstruction import normalize_ticks,first_barrier,candle_coverage
from atlas_ai.testing.structural_retest import RULES
from tools.learn_candidate_ranker import signed,save_signed,digest


def iter_first_array(path,key):
    """Stream the named first top-level array without loading the prediction file."""
    decoder=json.JSONDecoder()
    with Path(path).open(encoding='utf-8') as stream:
        buffer=stream.read(4096);marker='"'+key+'"'
        where=buffer.find(marker)
        if where<0:raise ValueError('prediction_array_not_first')
        begin=buffer.find('[',where)
        if begin<0:raise ValueError('prediction_array_missing')
        buffer=buffer[begin+1:]
        while True:
            buffer=buffer.lstrip(' \r\n\t,')
            if buffer.startswith(']'):return
            try:value,end=decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk=stream.read(65536)
                if not chunk:raise ValueError('truncated_prediction_array')
                buffer+=chunk;continue
            yield value;buffer=buffer[end:]


def barriers(entry,signal,spec,spread_points):
    sign=1 if signal.side=='buy' else -1
    minimum=max(spec.trade_stops_level,spec.trade_freeze_level)+max(2,round(spread_points*.35))
    stop=max(signal.stop_loss_points,minimum)*spec.point;target=max(signal.take_profit_points,minimum)*spec.point
    return round(entry-sign*stop,spec.digits),round(entry+sign*target,spec.digits)


def run(source,output):
    cfg=load_settings();source=source.resolve();output=output.resolve()
    source.relative_to(Path(cfg.storage_dir).resolve());output.relative_to(Path(cfg.storage_dir).resolve())
    p=signed(source,'protocol');r=signed(source,'report');receipt=signed(source,'prediction_receipt')
    if r.get('state')!='completed_research_only' or r['protocol_sha256']!=digest(source/'protocol.json'):raise ValueError('completed_source_required')
    if r['prediction_receipt_sha256']!=digest(source/'prediction_receipt.json') or receipt['protocol_sha256']!=digest(source/'protocol.json'):
        raise ValueError('prediction_receipt_changed')
    if digest(source/'predictions.json')!=receipt['sha256']:raise ValueError('predictions_changed')
    if account_scope(cfg)!=p['account_scope'] or cfg.symbol!=p['settings']['symbol']:raise ValueError('source_account_or_symbol_changed')
    if cfg.mt5_server_timezone!=p['settings']['mt5_server_timezone']:raise ValueError('broker_clock_changed')
    if digest(source/'M5.csv')!=signed(source,'inputs')['M5']:raise ValueError('candles_changed')
    trades=r['results']['validation']['repaired_baseline']['trade_list'];wanted={t['entry_bar']-1 for t in trades}
    cached={}
    for row in iter_first_array(source/'predictions.json','repaired_baseline'):
        if row['index'] in wanted:cached[row['index']]=row
        if len(cached)==len(wanted):break
    if len(cached)!=len(wanted):raise ValueError('source_predictions_missing')
    output.mkdir(parents=True,exist_ok=False);frame=pd.read_csv(source/'M5.csv');spec=BrokerSpec(**p['spec'])
    protocol={'schema':'atlas_tick_first_bar_audit_v1','frozen_at':datetime.now(timezone.utc).isoformat(),
        'source_report_sha256':digest(source/'report.json'),'source_protocol_sha256':digest(source/'protocol.json'),
        'clock_hypotheses':['configured_server_wall','documented_UTC'],'clock_selection':'Unique independently matching bid OHLC plus bounded quote coverage; never select by PnL.',
        'coverage':{'max_OHLC_error_points':1.01,'maximum_first_and_last_gap_seconds':10,'maximum_quote_gap_seconds':30},
        'structural_rules_frozen_before_tick_labels':RULES,'structural_model_sha256':digest(ROOT/'atlas_ai/testing/structural_retest.py'),
        'broker_eligible':False,'orders_sent':0,'auto_promotion':False,
        'limitations':['Recorded trade set only; changing exits would change subsequent portfolio selection, which is not replayed here.',
            'Quote history does not demonstrate fills, execution latency, protection acknowledgements or actual slippage.',
            'Only the recorded first M5 execution bar is reconstructed; a position still open has an unknown later outcome.',
            'A candle-matching bounded quote sample is evidence of alignment, not a guarantee of complete tick history.']}
    source_hashes={}
    for name in ['tools/reconstruct_m5_losses.py','atlas_ai/testing/tick_reconstruction.py','atlas_ai/testing/structural_retest.py','atlas_ai/data/broker_clock.py','atlas_ai/strategies/smc_composite.py']:
        dest=output/'frozen_source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest);source_hashes[name]=digest(dest)
    protocol['source_hashes']=source_hashes
    save_signed(output,'protocol',protocol)
    from tools.smc_validation import check_account
    def deny(*a,**kw):raise AssertionError('tick_audit_order_dispatch_forbidden')
    cases=[]
    with patch.object(mt5,'order_send',deny):
        check_account(cfg)
        for n,t in enumerate(trades):
            atomic_json(output/'progress.json',{'phase':'tick_reconstruction','case':n+1,'cases':len(trades),'checked_at':datetime.now(timezone.utc).isoformat()})
            start=pd.Timestamp(t['entry_at']);end=start+pd.Timedelta(minutes=5);i=t['entry_bar']
            bar=frame.iloc[i]
            if pd.Timestamp(bar.time,tz='UTC')!=start:raise ValueError('trade_bar_timestamp_changed')
            raw=next(s for s in cached[i-1]['signals'] if s['strategy']==t['strategy'] and s['side']==t['side'])
            signal=TradeSignal(**raw);record={'entry_at':start.isoformat(),'strategy':t['strategy'],'side':t['side'],
                'recorded_net_cash':t['net_cash'],'recorded_first_bar_stop_loss':t['exit_reason']=='stop_loss',
                'recorded_ambiguous_stop_first':t['ambiguous_stop_first'],'attempts':[]}
            usable=[]
            if t['exit_bar']!=i:
                cases.append({**record,'status':'unsupported_multi_bar_record'});continue
            for basis in protocol['clock_hypotheses']:
                try:
                    utc_basis=basis=='documented_UTC'
                    a=start.to_pydatetime() if utc_basis else utc_query_time(start.to_pydatetime(),cfg)
                    b=end.to_pydatetime() if utc_basis else utc_query_time(end.to_pydatetime(),cfg)
                    ticks=mt5.copy_ticks_range(cfg.symbol,a,b,mt5.COPY_TICKS_INFO)
                    if ticks is None or not len(ticks):
                        record['attempts'].append({'basis':basis,'usable':False,'reason':'tick_history_unavailable'});continue
                    settings=SimpleNamespace(mt5_server_timezone='UTC' if utc_basis else cfg.mt5_server_timezone)
                    rows=normalize_ticks(ticks,settings);rows,evidence=candle_coverage(rows,bar,start,end,spec.point)
                    evidence['basis']=basis;record['attempts'].append(evidence)
                    if evidence['usable']:usable.append((basis,rows))
                except (RuntimeError,ValueError,TypeError,OverflowError) as exc:
                    record['attempts'].append({'basis':basis,'usable':False,'reason':type(exc).__name__+':'+str(exc)})
            # UTC configuration makes the hypotheses identical, not ambiguous.
            if len(usable)==2 and str(cfg.mt5_server_timezone).upper() in {'UTC','ETC/UTC'}:usable=usable[:1]
            if len(usable)!=1:
                cases.append({**record,'status':'unresolved_clock_or_coverage' if not usable else 'ambiguous_clock_basis'})
                save_signed(output,'report',{'state':'running','cases':cases,'broker_eligible':False});continue
            basis,rows=usable[0];path=output/f'ticks_{n:02d}.csv';rows.to_csv(path,index=False)
            lagged_spread=float(frame.spread.iloc[i-1]);sl,tp=barriers(t['entry_price'],signal,spec,lagged_spread)
            expected_risk=abs(spec.cash(-abs(t['entry_price']-sl),t['volume']))
            if not math.isclose(expected_risk,t['initial_risk_cash'],abs_tol=.03):raise ValueError('recorded_protection_does_not_match_signal')
            first=rows.iloc[0];sign=1 if t['side']=='buy' else -1
            quote_entry=float(first.ask if sign==1 else first.bid)
            tick_entry=round(quote_entry+sign*3*spec.point,spec.digits)
            spread_points=float(first.ask-first.bid)/spec.point
            tick_sl,tick_tp=barriers(tick_entry,signal,spec,spread_points)
            record.update(status='quote_path_reconstructed',tick_timestamp_basis=basis,tick_data_sha256=digest(path),
                fixed_recorded_barriers={'stop':sl,'target':tp,**first_barrier(rows,t['side'],sl,tp)},
                tick_entry_diagnostic={'entry':tick_entry,'entry_quote_at':first.utc.isoformat(),'stop':tick_sl,'target':tick_tp,
                    **first_barrier(rows,t['side'],tick_sl,tick_tp)},broker_fill=False,protection_observed=False)
            cases.append(record);save_signed(output,'report',{'state':'running','cases':cases,'broker_eligible':False})
    result={'state':'completed_research_only','cases':cases,'protocol_sha256':digest(output/'protocol.json'),
            'broker_eligible':False,'orders_sent':0,'replaces_portfolio_backtest':False}
    save_signed(output,'report',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();r=run(a.source,a.output);print(json.dumps({'state':r['state'],'cases':len(r['cases'])}))
