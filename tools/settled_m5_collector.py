"""Fresh settled-candle forecasts. No orders, outcome backfill or promotion."""
import argparse
from datetime import datetime,timedelta,timezone
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import normalize_rates,broker_time_to_utc
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.strategies.inventory import base_inventory
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.distance_units import corrected_atr_signal
from atlas_ai.testing.candle_revision import candle_map,revision_audit
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.testing.policy_replay import policy_trader
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny

ROOT=Path(__file__).resolve().parents[1]


def forecast_window(frame,now):
    times=pd.to_datetime(frame.time,utc=True)
    settled=frame[times+pd.Timedelta(minutes=5,seconds=60)<=now].copy()
    if settled.empty:return settled,None
    at=pd.Timestamp(settled.time.iloc[-1])
    at=at.tz_localize('UTC') if at.tzinfo is None else at.tz_convert('UTC')
    close_at=at+pd.Timedelta(minutes=5)
    lag=(now-close_at).total_seconds()
    return settled,{'bar_close_at':close_at.isoformat(),'lag_seconds':lag,'timely':60<=lag<=120}


def scope(settings):
    return hashlib.sha256((str(settings.hfm_login)+'|'+settings.hfm_server+'|'+settings.symbol).encode()).hexdigest()


def initialize(directory):
    reference=ROOT/'storage/demo_representative_m5_primary_20261118'
    prior=signed(reference,'protocol');report=signed(reference,'report')
    if report['protocol_sha256']!=digest(reference/'protocol.json'):raise ValueError('reference_changed')
    settings=load_settings();now=datetime.now(timezone.utc)
    directory.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'atlas_ai/testing/candle_revision.py',ROOT/'atlas_ai/trader.py',
        ROOT/'atlas_ai/strategies/distance_units.py',ROOT/'atlas_ai/strategies/inventory.py',
        ROOT/'atlas_ai/strategies/built_in.py',ROOT/'atlas_ai/strategies/minute_pack.py',
        ROOT/'atlas_ai/strategies/indicators.py',ROOT/'atlas_ai/data/top_down.py',ROOT/'atlas_ai/data/broker_clock.py']
    hashes={str(path.relative_to(ROOT)):digest(path) for path in sources}
    save_signed(directory,'protocol',{'settings':prior['settings'],'spec':prior['spec'],'scope':scope(settings),'source_hashes':hashes,
        'started_at':now.isoformat(),'deadline':(now+timedelta(days=21)).isoformat(),
        'reference_report_sha256':digest(reference/'report.json'),'settle_seconds':60,'max_forecast_lag_seconds':120,
        'entry_schedule':'next_M5_boundary_after_observation; never_prior_next_open',
        'purpose':'fresh_candidate_sets_only; no_trade_outcomes_or_qualification_claims',
        'confluence_policy':__import__('atlas_ai.data.top_down',fromlist=['POLICY']).POLICY,
        'terminal_attach_retry_limit':3,
        'broker_eligible':False,'orders_sent':0,'auto_promotion':False})
    save_signed(directory,'checkpoint',{'bars':{},'last_forecast':None,'forecasts':0,'late_windows_skipped':0,'journal_sha256':None})
    (directory/'forecasts.jsonl').write_text('',encoding='utf-8')


def once(directory):
    protocol=signed(directory,'protocol');state=signed(directory,'checkpoint');settings=load_settings()
    if scope(settings)!=protocol['scope']:raise ValueError('account_scope_changed')
    for name,expected in protocol['source_hashes'].items():
        if digest(ROOT/name)!=expected:raise ValueError('source_changed:'+name)
    now=pd.Timestamp.now(tz='UTC')
    if now>=pd.Timestamp(protocol['deadline']):return {'state':'deadline_review_required','broker_eligible':False}
    path=directory/'forecasts.jsonl'
    if state['journal_sha256'] is not None and digest(path)!=state['journal_sha256']:raise ValueError('forecast_journal_changed')
    with patch.object(mt5,'order_send',deny),patch.object(mt5,'login',deny):
        if not mt5.initialize(path=settings.hfm_terminal_path):raise RuntimeError('terminal_attach_failed')
        account=mt5.account_info()
        if account is None or account.login!=settings.hfm_login or account.server!=settings.hfm_server or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise ValueError('matching_demo_required')
        info=mt5.symbol_info(settings.symbol);tick=mt5.symbol_info_tick(settings.symbol)
        if info is None or tick is None or not 0<tick.bid<=tick.ask:raise ValueError('valid_quote_required')
        if info.point!=protocol['spec']['point']:raise ValueError('broker_point_size_changed')
        quote_age=(now.to_pydatetime()-broker_time_to_utc(tick.time,settings)).total_seconds()
        if not -2<=quote_age<=120:return {'state':'waiting_for_fresh_quotes','broker_eligible':False,'checked_at':now.isoformat()}
        frames={}
        for tf,number in [('M5',1500),*[(tf,90) for tf in TIMEFRAMES]]:
            raw=mt5.copy_rates_from_pos(settings.symbol,getattr(mt5,'TIMEFRAME_'+tf),0,number)
            if raw is None or len(raw)==0:raise ValueError('rates_unavailable:'+tf)
            frames[tf]=normalize_rates(raw,settings)
    settled,window=forecast_window(frames['M5'],now)
    if len(settled)<60:raise ValueError('settled_context_unavailable')
    if state['bars']:
        previous=pd.DataFrame([{'time':at,**row} for at,row in state['bars'].items()])
        audit=revision_audit(previous,settled)
        if not audit['compatible_overlap']:
            save_signed(directory,'revision_failure',audit)
            raise ValueError('settled_broker_candles_revised_or_overlap_missing')
    state['bars'].update(candle_map(settled))
    if window['bar_close_at']!=state['last_forecast'] and window['timely']:
        cfg=settings_for(protocol,directory/'isolated_policy')
        trader=policy_trader(cfg,KnowledgeStore(cfg.storage_dir));f=settled.tail(1200)
        context=trader._signal_generation_context(f,now.to_pydatetime());signals=[]
        volatility=float(atr(f).iloc[-1])
        for strategy in base_inventory('M5',top_down=True):
            if trader._strategy_enabled(strategy.name):
                signal=trader._apply_signal_generation_gating(trader._sanitize_signal(strategy.generate_signal(f)),context)
                signals.append(asdict(corrected_atr_signal(signal,volatility,info.point)))
        feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES});feed.now=now
        observed=pd.Timestamp.now(tz='UTC')
        if (observed-pd.Timestamp(window['bar_close_at'])).total_seconds()>120:
            state['late_windows_skipped']+=1
        else:
            record={'observed_at':observed.isoformat(),**window,'scheduled_entry_at':observed.ceil('5min').isoformat(),
                'signals':signals,'higher_timeframe':collect(feed,now,broker_timezone=cfg.mt5_server_timezone or 'UTC'),
                'quote':{'bid':tick.bid,'ask':tick.ask,'point':info.point},'quote_observed_at':now.isoformat(),
                'broker_eligible':False,'orders_sent':0,'outcomes_evaluated':False}
            with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps(record,allow_nan=False)+'\n');stream.flush()
            state['forecasts']+=1
        state['last_forecast']=window['bar_close_at']
    elif not window['timely'] and state['last_forecast']!=window['bar_close_at']:
        state['late_windows_skipped']+=1;state['last_forecast']=window['bar_close_at']
    state['journal_sha256']=digest(path);save_signed(directory,'checkpoint',state)
    return {'state':'collecting_settled_candidate_forecasts','checked_at':now.isoformat(),'forecasts':state['forecasts'],
        'late_windows_skipped':state['late_windows_skipped'],'broker_eligible':False,'orders_sent':0,
        'outcomes_evaluated':False,'policy_note':'Candidate forecasts only; not executed trades or completed forward qualification.'}


def observation_step(directory, *, failures=0, observe=once):
    """Retry only terminal attach failures; integrity/policy failures always pause."""
    try:
        result=observe(directory)
        return result,0,False
    except Exception as exc:
        transient=isinstance(exc,RuntimeError) and str(exc)=='terminal_attach_failed'
        failures=failures+1 if transient else 0
        retry=transient and failures<3
        result={'state':'waiting_for_terminal' if retry else 'blocked_review_required',
                'reason':str(exc),'consecutive_attach_failures':failures,
                'checked_at':datetime.now(timezone.utc).isoformat(),
                'broker_eligible':False,'orders_sent':0,'outcomes_evaluated':False}
        return result,failures,not retry


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--initialize',action='store_true');parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    if args.initialize:initialize(args.directory)
    with observation_lock(args.directory/'collector.lock'):
        failures=0
        while True:
            result,failures,blocked=observation_step(args.directory,failures=failures)
            atomic_json(args.directory/'status.json',result)
            print(json.dumps(result),flush=True)
            if blocked:raise SystemExit(1)
            if not args.watch or result['state']=='deadline_review_required':break
            time.sleep(15)
