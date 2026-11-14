"""Frozen historical and prospective paper validation; no broker-order route."""
import argparse
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import json,os,shutil,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.data.broker_clock import broker_time_to_utc,utc_query_time
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.execution.session_control import DayTradingSessionControl
from atlas_ai.learning.observation_checkpoint import observation_lock,account_scope
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.smc_validation import METHOD,historical,advance_ticks,stage,setup_identity
from atlas_ai.strategies.smc_composite import evaluate
from atlas_ai.strategies.research_protocol import environment_versions
from tools.guarded_research_audit import broker_snapshot,safe_settings
from tools.learn_candidate_ranker import read,digest,signed,save_signed,settings_for,deny


def check_account(settings):
    MarketDataFeed(settings)._ensure_initialized()
    a=mt5.account_info()
    if a is None or a.login!=settings.hfm_login or a.server!=settings.hfm_server or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise ValueError('matching_demo_account_required')


def evaluator_for(manifest):
    name=manifest.get('model','smc_composite_v1')
    if name=='smc_composite_v1':return evaluate
    if name=='smc_pullback_v2':
        from atlas_ai.strategies.smc_pullback import evaluate as pullback
        return pullback
    if name=='smc_retest_v3':
        from atlas_ai.strategies.smc_retest import evaluate as retest
        return retest
    if name=='smc_framework_v4':
        from atlas_ai.strategies.smc_framework import evaluate as framework
        return framework
    if name=='smc_event_retest_v5':
        from atlas_ai.strategies.smc_entry_models import event_retest
        return event_retest
    if name=='smc_sweep_reclaim_v5':
        from atlas_ai.strategies.smc_entry_models import sweep_reclaim
        return sweep_reclaim
    raise ValueError('unsupported_frozen_model')


def initialize(directory,model='smc_composite_v1',reuse=None,*,activate=True,reuse_costs=False):
    s=load_settings();storage=Path(s.storage_dir);directory=directory.resolve()
    directory.relative_to(storage.resolve());directory.mkdir(parents=True,exist_ok=False)
    if s.timeframe!='M5' or not s.top_down_confluence_enabled or s.backtest_max_hold_bars!=12:
        raise ValueError('configured_top_down_M5_and_12_bar_research_horizon_required')
    if not reuse_costs:check_account(s)
    now=datetime.now(timezone.utc);end=pd.Timestamp(now).floor('5min');start=end-pd.Timedelta(days=180)
    if reuse_costs and reuse is None:raise ValueError('reused_costs_require_verified_source')
    if not reuse_costs:spec,evidence,limits=broker_snapshot(s)
    if reuse is not None:
        reuse=reuse.resolve();reuse.relative_to(storage.resolve());old=signed(reuse,'manifest')
        if old['account_scope']!=account_scope(s) or old['settings']['symbol']!=s.symbol:raise ValueError('historical_reuse_scope_changed')
        start=pd.Timestamp(old['history_start']);end=pd.Timestamp(old['history_end'])
        if reuse_costs:
            if json.loads(json.dumps(safe_settings(s)))!=old['settings']:raise ValueError('settings_changed_in_matched_comparison')
            spec=BrokerSpec(**old['spec']);evidence={**old['cost_evidence'],'reference_manifest_sha256':digest(reuse/'manifest.json')};limits=old['limits']
    hashes={}
    for folder in ['atlas_ai','tools']:
        for p in (ROOT/folder).rglob('*.py'):
            relative=p.relative_to(ROOT);target=directory/'frozen_source'/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);hashes[relative.as_posix()]=digest(p)
    manifest={'schema':'atlas_smc_validation_v1','method':METHOD,'frozen_at':now.isoformat(),
        'model':model,'history_reused_after_prior_diagnostic':reuse is not None,
        'paper_activation_requested':activate,'matched_frozen_cost_reference':reuse_costs,
        'history_start':start.isoformat(),'history_end':end.isoformat(),'settings':safe_settings(s),
        'spec':asdict(spec),'cost_evidence':evidence,'limits':limits,'account_scope':account_scope(s),
        'source_hashes':hashes,'environment':environment_versions(),'broker_eligible':False,'orders_sent':0,
        'deadline':signed(storage,'acceptance_plan')['deadline']}
    save_signed(directory,'manifest',manifest)
    old_inputs=signed(reuse,'inputs') if reuse is not None else None
    for tf in (*TIMEFRAMES,'M5'):
        if reuse is not None:
            source=reuse/(tf+'.csv')
            if digest(source)!=old_inputs[tf]:raise ValueError('reused_input_changed')
            shutil.copyfile(source,directory/(tf+'.csv'))
            if digest(directory/(tf+'.csv'))!=old_inputs[tf]:raise ValueError('copied_input_changed')
            continue
        warmup=120 if tf=='D1' else 30 if tf in {'H4','H1','M15'} else 2
        frame=MarketDataFeed(replace(s,timeframe=tf)).get_rates_range((start-pd.Timedelta(days=warmup)).to_pydatetime(),end.to_pydatetime())
        if len(frame)<90:raise ValueError('insufficient_history:'+tf)
        frame.to_csv(directory/(tf+'.csv'),index=False)
        print(json.dumps({'downloaded':tf,'bars':len(frame),'first':str(frame.time.iloc[0]),'last':str(frame.time.iloc[-1])}),flush=True)
    save_signed(directory,'inputs',{tf:digest(directory/(tf+'.csv')) for tf in (*TIMEFRAMES,'M5')})
    # Activated paper observation has no dependency on a historical pass and no
    # ability to enable broker trading. The historical screen is separate.
    if activate:atomic_json(storage/'smc_validation_active.json',{'run_dir':str(directory)})
    print(json.dumps({'state':'frozen_inputs_ready','run_dir':str(directory)}),flush=True)


def validate(directory):
    m=signed(directory,'manifest')
    if m['schema']!='atlas_smc_validation_v1' or m['method']!=METHOD or m['broker_eligible'] is not False or m['orders_sent']!=0:
        raise ValueError('validation_boundary_changed')
    evaluator_for(m)
    for name,value in m['source_hashes'].items():
        if digest(directory/'frozen_source'/name)!=value:raise ValueError('frozen_source_changed')
    return m


def run_history(directory):
    m=validate(directory);inputs=signed(directory,'inputs');frames={}
    for tf,expected in inputs.items():
        path=directory/(tf+'.csv')
        if digest(path)!=expected:raise ValueError('historical_input_changed')
        frames[tf]=pd.read_csv(path);frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
    cfg=settings_for(m,str(directory/'unused_no_writes'))
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny):
        result=historical(frames,cfg,BrokerSpec(**m['spec']),m['limits'],pd.Timestamp(m['history_start']),pd.Timestamp(m['history_end']),
            progress=lambda **kw:atomic_json(directory/'history_progress.json',kw),evaluator=evaluator_for(m))
    result['model']=m.get('model','smc_composite_v1')
    result['manifest_sha256']=digest(directory/'manifest.json');save_signed(directory,'history',result)
    print(json.dumps({'state':'historical_complete','stages':result['stages'],'counts':result['counts'],
        'historical_screen_passed':result['historical_screen_passed'],'broker_eligible':False}),flush=True)


def once(directory,now):
    m=validate(directory);s=load_settings();check_account(s)
    if account_scope(s)!=m['account_scope']:raise ValueError('account_scope_changed')
    cfg=settings_for(m,str(directory/'unused_no_writes'));spec=BrokerSpec(**m['spec'])
    path=directory/'paper_checkpoint.json'
    if path.exists():
        state=signed(directory,'paper_checkpoint')
        if state['manifest_sha256']!=digest(directory/'manifest.json'):raise ValueError('paper_manifest_changed')
    else:state={'manifest_sha256':digest(directory/'manifest.json'),'pending':None,'cases':[],'seen':[], 'daily':{},'counts':{}}
    now=pd.Timestamp(now);deadline=pd.Timestamp(m['deadline'])
    def count(key):state['counts'][key]=state['counts'].get(key,0)+1
    pending=state['pending']
    if pending:
        cursor=pd.Timestamp(pending.get('query_until_utc') or broker_time_to_utc(pending['last_tick_msc']/1000,s))
        end=min(now,pd.Timestamp(cursor)+pd.Timedelta(minutes=5))
        raw=mt5.copy_ticks_range(s.symbol,utc_query_time(cursor,s),utc_query_time(end.to_pydatetime(),s),mt5.COPY_TICKS_ALL)
        if raw is None:count('tick_history_unavailable')
        else:
            ticks=[{'time_msc':int(t['time_msc']),'bid':float(t['bid']),'ask':float(t['ask']),
                'utc':broker_time_to_utc(float(t['time_msc'])/1000,s).isoformat()} for t in raw]
            state['pending'],resolved=advance_ticks(pending,ticks,spec,cfg,now)
            if state['pending']:state['pending']['query_until_utc']=end.isoformat()
            if resolved:state['cases'].append(resolved)
    latest=None
    if not state['pending'] and now<deadline and len(state['cases'])<60:
        calendar=DayTradingSessionControl();session=calendar._detect_session(now.to_pydatetime())
        day=now.date().isoformat();today=[c for c in state['cases'] if c['entry_at'][:10]==day]
        loss_streak=0
        for c in reversed(today):
            if c['net_cash']>=0:break
            loss_streak+=1
        balance=float(cfg.backtest_initial_balance)+sum(c['net_cash'] for c in state['cases'])
        limits=m['limits']
        allowed=(session.allowed and session.minutes_to_close>=70 and now+pd.Timedelta(minutes=60)<deadline
            and state['daily'].get(day,0)<min(6,limits['day_trades']) and loss_streak<min(cfg.max_consecutive_losses,limits['loss_streak'])
            and sum(c['net_cash'] for c in today)>-balance*limits['daily_loss_percent']/100)
        if allowed:
            feed=MarketDataFeed(s);context=collect(feed,now,broker_timezone=s.mt5_server_timezone or 'UTC')
            frame=feed.get_rates_for_timeframe('M5',bars=90);tick=mt5.symbol_info_tick(s.symbol)
            if tick:
                quote={'bid':tick.bid,'ask':tick.ask,'point':spec.point,'at':broker_time_to_utc(tick.time,s).isoformat()}
                latest=evaluator_for(m)(frame,context,quote,now)
                key=setup_identity(latest)
                if latest.get('candidate') and key not in state['seen'] and now>=pd.Timestamp(m['frozen_at']):
                    candidate=latest['candidate'];sign=1 if candidate['side']=='buy' else -1
                    entry=float(latest['entry_reference'])+sign*3*spec.point
                    distance=candidate['stop_loss_points']*spec.point
                    cash=abs(spec.cash(-distance,spec.volume_min))
                    spread=(tick.ask-tick.bid)/spec.point
                    minimum=max(spec.trade_stops_level,spec.trade_freeze_level)+max(2,round(spread*.35))
                    if (cash<=balance*cfg.max_risk_per_trade and spec.volume_min<=limits['lot_cap']
                        and spec.margin_per_lot*spec.volume_min<=balance and min(candidate['stop_loss_points'],candidate['take_profit_points'])>=minimum):
                        state['pending']={'entry_at':now.isoformat(),'side':candidate['side'],'entry_price':entry,
                            'risk_price':distance,'initial_risk_cash':cash,'stop':entry-sign*distance,
                            'target':entry+sign*candidate['take_profit_points']*spec.point,'best_r':0.,
                            'entry_tick_msc':int(tick.time_msc),'last_tick_msc':int(tick.time_msc),'last_tick_keys':[],
                            'signal':latest,'volume':spec.volume_min,'broker_fill':False,'evidence_complete':True}
                        state['seen'].append(key);state['daily'][day]=state['daily'].get(day,0)+1
                    else:count('paper_risk_margin_or_protection_rejection')
        else:count('session_risk_or_daily_limit')
    eligible=[c for c in state['cases'] if c.get('evidence_complete') is True]
    first=stage(eligible[:30]);second=stage(eligible[30:60])
    report={'state':'completed_review_required' if len(state['cases'])>=60 else 'deadline_review_required' if now>=deadline else 'collecting_paper',
        'checked_at':now.isoformat(),'frozen_at':m['frozen_at'],'deadline':m['deadline'],
        'model':m.get('model','smc_composite_v1'),
        'paper_trades':len(eligible),'incomplete_tick_cases':len(state['cases'])-len(eligible),'pending':bool(state['pending']),'first_stage':first,'validation_stage':second,
        'prospective_screen_passed':first['review_passed'] and second['review_passed'],
        'latest_observation':latest,'counts':state['counts'],'broker_eligible':False,'orders_sent':0,'auto_activation':False,
        'limitations':['Tick outcomes are simulated; no actual fills or protected broker position are established.',
            'Model-only paper lane; full final-conviction, visual, macro and execution-policy parity remain unverified.']}
    save_signed(directory,'paper_checkpoint',state);atomic_json(directory/'paper_status.json',report)
    return report


def ensure(storage,state,*,can_start,now,start=subprocess.Popen):
    storage=Path(storage);pointer=storage/'smc_validation_active.json'
    if not pointer.exists():return {'state':'not_configured'}
    directory=Path(read(pointer)['run_dir']).resolve();directory.relative_to(storage.resolve());m=signed(directory,'manifest')
    if m.get('broker_eligible') is not False or m.get('schema')!='atlas_smc_validation_v1':raise ValueError('invalid_paper_boundary')
    if pd.Timestamp(now)>=pd.Timestamp(m['deadline']):return {'state':'deadline_reached'}
    try:
        with observation_lock(directory/'watch.lock'):pass
    except RuntimeError:return {'state':'existing_smc_paper_observer_running'}
    report=read(directory/'paper_status.json') if (directory/'paper_status.json').exists() else {}
    if report.get('state') in {'blocked_review_required','completed_review_required','deadline_review_required'}:return {'state':report['state']}
    if not can_start:return {'state':'waiting_for_backend_and_operator'}
    attempts=state.setdefault('smc_validation_starts',[]);attempts[:]=[t for t in attempts if now.timestamp()-t<3600]
    if len(attempts)>=3:return {'state':'restart_budget_exhausted'}
    validate(directory)
    with (directory/'stdout.log').open('a') as out,(directory/'stderr.log').open('a') as err:
        env=dict(os.environ);env['STORAGE_DIR']=str(storage.resolve())
        child=start([sys.executable,str(directory/'frozen_source/tools/smc_validation.py'),'watch','--run-dir',str(directory)],
            cwd=directory/'frozen_source',env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    attempts.append(now.timestamp());return {'state':'smc_paper_observer_launched','pid':child.pid}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['init','history','watch','once']);p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--model',choices=['smc_composite_v1','smc_pullback_v2','smc_retest_v3','smc_framework_v4','smc_event_retest_v5','smc_sweep_reclaim_v5'],default='smc_composite_v1');p.add_argument('--reuse-inputs',type=Path)
    p.add_argument('--no-activate',action='store_true');p.add_argument('--reuse-costs',action='store_true');a=p.parse_args()
    if a.mode=='init':initialize(a.run_dir,a.model,a.reuse_inputs,activate=not a.no_activate,reuse_costs=a.reuse_costs);return
    if a.mode=='history':run_history(a.run_dir);return
    with observation_lock(a.run_dir/'watch.lock'),patch.object(mt5,'order_send',deny):
        while True:
            try:result=once(a.run_dir,datetime.now(timezone.utc))
            except Exception as exc:
                result={'state':'blocked_review_required','checked_at':datetime.now(timezone.utc).isoformat(),'reason':str(exc),'broker_eligible':False,'orders_sent':0}
                atomic_json(a.run_dir/'paper_status.json',result)
            if a.mode=='once' or result['state']!='collecting_paper':return
            time.sleep(60)


if __name__=='__main__':main()
