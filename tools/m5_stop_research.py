"""Frozen matched ATR-unit study; durable research evidence, no live learning writes."""
import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
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
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.data.top_down import TIMEFRAMES,MINUTES
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.distance_units import ATR_DISTANCE_RULES,corrected_atr_signal
from atlas_ai.strategies.indicators import atr
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import cache_candidates,replay
from tools.cost_aware_strategy_audit import prepare_frame
from tools.guarded_research_audit import safe_settings
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for
from tools.m5_system_backtest import LIMITATIONS

POLICY_SOURCES=('atlas_ai/testing/policy_replay.py','atlas_ai/testing/historical_decision.py',
    'atlas_ai/trader.py','atlas_ai/strategies/inventory.py','atlas_ai/strategies/built_in.py',
    'atlas_ai/strategies/minute_pack.py','atlas_ai/strategies/indicators.py',
    'atlas_ai/strategies/distance_units.py','atlas_ai/risk/risk_manager.py',
    'atlas_ai/execution/session_control.py','atlas_ai/testing/historical_broker.py')


def disjoint(start,end,other_start,other_end):
    if not start<end or not other_start<other_end:raise ValueError('ordered_periods_required')
    return end<=other_start or start>=other_end


def corrected_candidates(frame,rows,point):
    """Same signals/times/confidences; only declared closed-bar ATR distances change."""
    result=deepcopy(rows);values=atr(frame)
    for row in result:
        i=row['index']
        if i<14 or i>=len(frame)-1:raise ValueError('candidate_closed_window_required')
        at=pd.Timestamp(frame.time.iloc[i]);at=at.tz_localize('UTC') if at.tzinfo is None else at.tz_convert('UTC')
        if pd.Timestamp(row['available_at'])!=at+pd.Timedelta(minutes=5):raise ValueError('candidate_time_changed')
        value=float(values.iloc[row['index']])
        row['signals']=[asdict(corrected_atr_signal(TradeSignal(**s),value,point))
                        if s['side'] in {'buy','sell'} else s for s in row['signals']]
    return result


def review(stats):
    dates={t['entry_at'][:10] for t in stats['trade_list']}
    reasons=[]
    if stats['trades']<30:reasons.append('fewer_than_30_trades')
    if len(dates)<2:reasons.append('fewer_than_2_dates')
    if stats['mean_net_r'] is None or stats['mean_net_r']<=0:reasons.append('no_positive_mean_net_R')
    if not ((stats['profit_factor'] or 0)>=1.1 or stats['wins']==stats['trades']>0):reasons.append('profit_factor_below_1_1')
    if stats['max_drawdown_r']>6:reasons.append('drawdown_above_6R')
    return {'passed':not reasons,'reasons':reasons}


def initialize(output,source,start,end):
    if start.tzinfo is None or end.tzinfo is None:raise ValueError('timezone_aware_validation_required')
    output=output.resolve();s=load_settings();output.relative_to(Path(s.storage_dir).resolve())
    if s.timeframe!='M5' or not s.top_down_confluence_enabled:raise ValueError('configured_M5_and_top_down_required')
    old=signed(source,'manifest');report=signed(source,'report')
    if report['state']!='completed_research_only' or report['manifest_sha256']!=digest(source/'manifest.json'):
        raise ValueError('completed_verified_discovery_required')
    if old['settings']!=json.loads(json.dumps(safe_settings(s))):raise ValueError('matched_settings_changed')
    for name in POLICY_SOURCES:
        if digest(ROOT/name)!=old['source_hashes'][name]:raise ValueError('discovery_policy_changed:'+name)
    a=pd.Timestamp(old['start_utc']);b=pd.Timestamp(old['end_utc'])
    if not disjoint(start,end,a,b):raise ValueError('validation_must_not_overlap_discovery')
    if end-start<pd.Timedelta(days=28) or end-start>pd.Timedelta(days=90):raise ValueError('validation_28_to_90_days_required')
    if end>pd.Timestamp.now(tz='UTC'):raise ValueError('historical_validation_must_be_closed')
    output.mkdir(parents=True,exist_ok=False)
    for folder in ['atlas_ai','tools']:
        for p in (ROOT/folder).rglob('*.py'):
            target=output/'frozen_source'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    protocol={'schema':'atlas_M5_stop_research_v1','frozen_at':datetime.now(timezone.utc).isoformat(),
        'hypothesis':'ATR-price distances require division by broker point size; volatility-scaled protection may reduce first-M5-bar stopouts but must fit the unchanged risk budget.',
        'interventions':['unchanged_baseline','reviewed_ATR_point_conversion'],
        'distance_rules':ATR_DISTANCE_RULES,'validation_start_utc':start.isoformat(),'validation_end_utc':end.isoformat(),
        'discovery_start_utc':a.isoformat(),'discovery_end_utc':b.isoformat(),
        'separation':'Disjoint earlier historical period, not future out-of-sample proof. Prior chart availability cannot establish blindness.',
        'review_criteria':{'minimum_trades':30,'minimum_dates':2,'mean_net_R':'positive','minimum_profit_factor':1.1,'maximum_drawdown_R':6},
        'no_parameter_search':True,'no_retuning_after_outcomes':True,'risk_fraction':s.max_risk_per_trade,
        'limits':old['limits'],'spec':old['spec'],'settings':old['settings'],'cost_evidence':old['cost_evidence'],
        'source_manifest_sha256':digest(source/'manifest.json'),'source_report_sha256':digest(source/'report.json'),
        'source_dir':str(source.resolve()),'slippage_points_per_side':3.,
        'fresh_forward_required_after_historical_review':True,'broker_eligible':False,'auto_promotion':False,'orders_sent':0,
        'learning_scope':'Persistent factual proposal and evidence only. No live allocator, lessons, strategy, risk or execution mutation.',
        'limitations':LIMITATIONS}
    save_signed(output,'protocol',protocol)
    save_signed(output,'source_receipt',{'protocol_sha256':digest(output/'protocol.json'),
        'frozen_source_hashes':{p.relative_to(output/'frozen_source').as_posix():digest(p)
                                for p in (output/'frozen_source').rglob('*.py')}})
    atomic_json(Path(s.storage_dir)/'m5_stop_research_active.json',{'run_dir':str(output)})
    return protocol


def run(output,source,start,end):
    p=initialize(output,source,start,end)
    def progress(phase,**kw):atomic_json(output/'progress.json',{'phase':phase,'checked_at':datetime.now(timezone.utc).isoformat(),**kw})
    def deny(*a,**kw):raise AssertionError('stop_research_broker_action_forbidden')
    try:
        with patch.object(mt5,'order_send',deny):
            frames={};inputs={};s=load_settings()
            from tools.smc_validation import check_account
            check_account(s)
            for tf in (*TIMEFRAMES,'M5'):
                progress('fetch_separate_native_history',timeframe=tf)
                warmup=140 if tf=='D1' else 30 if tf!='M5' else 7
                f=MarketDataFeed(replace(s,timeframe=tf)).get_rates_range((start-pd.Timedelta(days=warmup)).to_pydatetime(),end.to_pydatetime())
                f=f[pd.to_datetime(f.time,utc=True)+pd.Timedelta(minutes=MINUTES[tf])<=end].reset_index(drop=True)
                f=prepare_frame(f)
                if len(f)<90:raise ValueError('insufficient_history:'+tf)
                f.to_csv(output/(tf+'.csv'),index=False);frames[tf]=f;inputs[tf]=digest(output/(tf+'.csv'))
            times=pd.to_datetime(frames['M5'].time,utc=True)
            within=times[(times>=start)&(times+pd.Timedelta(minutes=5)<=end)]
            if len(within)<1000 or within.max()-within.min()<pd.Timedelta(days=20):raise ValueError('validation_coverage_too_short')
            save_signed(output,'inputs',{'hashes':inputs,'decision_bars':len(within),'first_utc':within.min().isoformat(),'last_utc':within.max().isoformat()})
            source_manifest=signed(source,'manifest');source_candidates=signed(source,'candidates')
            if digest(source/'candidates.json')!=signed(source,'report')['candidate_sha256']:raise ValueError('discovery_candidates_changed')
            discovery=prepare_frame(pd.read_csv(source/'M5.csv'))
            if digest(source/'M5.csv')!=source_manifest['data']['M5']['sha256']:raise ValueError('discovery_candles_changed')
            spec=BrokerSpec(**p['spec']);results={}
            with tempfile.TemporaryDirectory(prefix='isolated_',dir=output) as temporary:
                settings=settings_for({'settings':p['settings']},temporary);store=KnowledgeStore(temporary)
                frame=frames['M5'];first=max(250,int((times+pd.Timedelta(minutes=5)>=start).to_numpy().nonzero()[0][0]))
                cache,counts,names=cache_candidates(frame,settings,store,
                    lambda **kw:progress('separate_candidate_generation',**{k:v for k,v in kw.items() if k!='stage'}),
                    start_index=first,native_frames=frames)
                datasets={'discovery':(discovery,source_candidates['rows'],pd.Timestamp(p['discovery_start_utc']),pd.Timestamp(p['discovery_end_utc'])),
                          'separate_validation':(frame,cache,start,end)}
                prepared={}
                for name,(f,rows,begin,finish) in datasets.items():
                    prepared[name]={'unchanged_baseline':rows,'reviewed_ATR_point_conversion':corrected_candidates(f,rows,spec.point)}
                    save_signed(output,name+'_candidates',{'lanes':prepared[name]})
                save_signed(output,'prediction_receipt',{'protocol_sha256':digest(output/'protocol.json'),
                    'datasets':{name:digest(output/(name+'_candidates.json')) for name in prepared},'predictions_frozen_before_labels':True})
                receipt=signed(output,'prediction_receipt')
                # After inputs are saved, prevent any further terminal access during offline labels.
                with patch.object(mt5,'initialize',deny):
                    for name,(f,rows,begin,finish) in datasets.items():
                        results[name]={};execution=f.copy();execution['spread']=f.spread.shift(1)
                        for lane,candidates in prepared[name].items():
                            if digest(output/(name+'_candidates.json'))!=receipt['datasets'][name]:raise ValueError('predictions_changed')
                            progress('matched_policy_replay',dataset=name,lane=lane)
                            result=replay(execution,candidates,settings,spec,ExitVariant('configured',settings.backtest_break_even_lock_r,3.),
                                store,p['limits'],start=begin.to_pydatetime(),end=finish.to_pydatetime())
                            result['review']=review(result)
                            result['first_bar_stopouts']=sum(t['exit_reason']=='stop_loss' and t['entry_bar']==t['exit_bar'] for t in result['trade_list'])
                            results[name][lane]=result
                            save_signed(output,'report',{'state':'running','results':results,'broker_eligible':False})
                corrected=results['separate_validation']['reviewed_ATR_point_conversion']
                final={'schema':'atlas_M5_stop_research_result_v1','state':'completed_research_only','results':results,
                    'separate_historical_review_passed':corrected['review']['passed'],
                    'selected_for_live':None,'broker_eligible':False,'auto_promotion':False,'orders_sent':0,
                    'future_forward_required':True,'protocol_sha256':digest(output/'protocol.json'),
                    'prediction_receipt_sha256':digest(output/'prediction_receipt.json'),'full_live_policy_parity':False}
                save_signed(output,'report',final);progress('completed_research_only')
                return final
    except Exception as exc:
        progress('failed',error=type(exc).__name__,reason=str(exc));raise
    finally:mt5.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--start',required=True);parser.add_argument('--end',required=True)
    args=parser.parse_args();result=run(args.output.resolve(),args.source.resolve(),pd.Timestamp(args.start),pd.Timestamp(args.end))
    print(json.dumps({'state':result['state'],'separate_historical_review_passed':result['separate_historical_review_passed'],'broker_eligible':False}))
