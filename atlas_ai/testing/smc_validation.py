"""Cost-aware multi-timeframe SMC diagnostics. No execution adapter."""
from collections import Counter
from dataclasses import asdict
from bisect import bisect_right
import math
import pandas as pd
from atlas_ai.data.top_down import collect,TIMEFRAMES
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.smc_composite import evaluate
from atlas_ai.testing.historical_broker import simulate,ExitVariant
from atlas_ai.execution.session_control import DayTradingSessionControl
from tools.cost_aware_strategy_audit import metrics

METHOD={"history_days":180,"split_fractions":[.6,.2,.2],"minimum_stage_trades":30,
    "minimum_stage_days":2,"minimum_profit_factor":1.1,"maximum_drawdown_r":6.,
    "slippage_points_each_side":3.,"forward_stage_sizes":[30,30],"daily_paper_limit":6,
    "authority":"paper_only_no_auto_activation","historical_quotes":"next_M5_open_plus_previous_closed_bar_spread_proxy",
    "historical_management":"existing_M5_bar_simulator_stop_first","forward_management":"observed_bid_ask_ticks",
    "hold_minutes":60}


def paper_progress(storage):
    import json,hashlib
    from pathlib import Path
    try:
        storage=Path(storage);pointer=storage/'smc_validation_active.json'
        if not pointer.exists():return {'state':'not_configured','broker_eligible':False}
        directory=Path(json.loads(pointer.read_text())['run_dir']).resolve();directory.relative_to(storage.resolve())
        raw=(directory/'manifest.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=(directory/'manifest.sha256').read_text().strip():raise ValueError('manifest_changed')
        manifest=json.loads(raw)
        if manifest.get('broker_eligible') is not False:raise ValueError('invalid_boundary')
        path=directory/'paper_status.json';status=json.loads(path.read_text()) if path.exists() else {}
        return {**{k:status.get(k) for k in ['state','checked_at','paper_trades','pending','incomplete_tick_cases']},
            'first_stage_trades':status.get('first_stage',{}).get('trades',0),
            'validation_stage_trades':status.get('validation_stage',{}).get('trades',0),
            'model':manifest.get('model','smc_composite_v1'),'broker_eligible':False}
    except Exception:return {'state':'unavailable_review_required','broker_eligible':False}


class HistoricalFeed:
    def __init__(self,frames):
        self.frames=frames
        self.times={tf:list(pd.to_datetime(f.time,utc=True)) for tf,f in frames.items()}
        self.now=None
    def get_rates_for_timeframe(self,tf,bars=90):
        # An opening candle at now is allowed in the source; collect discards
        # it. No later candle or future pivot can reach the decision.
        end=bisect_right(self.times[tf],self.now)
        return self.frames[tf].iloc[max(0,end-bars-1):end].copy()


def stage(rows):
    m=metrics(rows)
    m['net_cash']=sum(r['net_cash'] for r in rows)
    m['review_passed']=(m['trades']>=30 and m['days']>=2 and (m['mean_r'] or 0)>0
        and ((m['profit_factor'] or 0)>=1.1 or m['wins']==m['trades']) and m['max_drawdown_r']<=6)
    return m


def historical(frames,settings,spec,limits,start,end,*,progress=lambda **kw:None,evaluator=evaluate):
    f=frames['M5'].reset_index(drop=True);times=pd.to_datetime(f.time,utc=True)
    execution=f.copy();execution['spread']=f.spread.shift(1)
    feed=HistoricalFeed({tf:frames[tf] for tf in TIMEFRAMES})
    boundaries=[start+(end-start)*.6,start+(end-start)*.8,end]
    rows=[];counts=Counter();calendar=DayTradingSessionControl();busy=-1
    day=None;day_count=0;streak=0;day_cash=0.;balance=settings.backtest_initial_balance
    horizon=12;context_key=None;cached_context=None
    for i in range(80,len(f)-horizon):
        now=times.iloc[i]+pd.Timedelta(minutes=5)
        if now<start or now>=end:continue
        if i<=busy:counts['open_paper_position']+=1;continue
        if day!=now.date():day=now.date();day_count=0;streak=0;day_cash=0.
        if day_count>=min(6,limits['day_trades']) or streak>=min(settings.max_consecutive_losses,limits['loss_streak']):
            counts['daily_trade_or_streak_limit']+=1;continue
        if day_cash<=-balance*limits['daily_loss_percent']/100:
            counts['daily_loss_limit']+=1;continue
        session=calendar._detect_session(now.to_pydatetime())
        if not session.allowed or session.minutes_to_close<70:
            counts['session_or_close_buffer']+=1;continue
        stage_index=next((j for j,b in enumerate(boundaries) if now<b),None)
        if stage_index is None:continue
        entry=i+1;last=entry+horizon-1;finish=times.iloc[last]+pd.Timedelta(minutes=5)
        if finish>boundaries[stage_index]:counts['split_boundary_purge']+=1;continue
        if times.iloc[entry]!=now or not times.iloc[i-79:last+1].diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            counts['input_or_outcome_gap']+=1;continue
        feed.now=now
        key=now.floor('15min')
        if key!=context_key:
            cached_context=collect(feed,now,broker_timezone=settings.mt5_server_timezone or 'UTC');context_key=key
        context={**cached_context,'evaluated_at':now.isoformat()}
        quote={'bid':float(f.open.iloc[entry]),'ask':float(f.open.iloc[entry])+float(execution.spread.iloc[entry])*spec.point,
            'point':spec.point,'at':now.isoformat()}
        result=evaluator(f.iloc[max(0,i-79):i+1],context,quote,now)
        counts['stage:'+result['stage']]+=1
        if i%100==0:progress(bar=i,total=len(f),cases=len(rows),at=now.isoformat())
        if not result.get('candidate'):continue
        signal=TradeSignal(**result['candidate'])
        minimum=max(spec.trade_stops_level,spec.trade_freeze_level)+max(2,round(float(execution.spread.iloc[entry])*.35))
        if min(signal.stop_loss_points,signal.take_profit_points)<minimum:
            counts['broker_minimum_protection']+=1;continue
        risk=abs(spec.cash(-signal.stop_loss_points*spec.point,spec.volume_min))
        if (spec.volume_min>limits['lot_cap'] or risk>balance*settings.max_risk_per_trade
                or spec.margin_per_lot*spec.volume_min>balance):
            counts['minimum_volume_risk_or_margin']+=1;continue
        outcome=simulate(execution,entry,signal,spec.volume_min,spec,settings,
            ExitVariant('current',settings.backtest_break_even_lock_r,3.))
        row={**result,'entry_at':now.isoformat(),'stage_index':stage_index,'net_r':outcome['net_r'],
            'net_cash':outcome['net_cash'],'outcome':outcome,'hypothetical_only':True}
        rows.append(row);busy=last;day_count+=1;day_cash+=outcome['net_cash']
        balance+=outcome['net_cash'];streak=streak+1 if outcome['net_cash']<0 else 0
    stages={name:stage([r for r in rows if r['stage_index']==j]) for j,name in enumerate(['development','validation','holdout'])}
    return {'schema':'smc_multitimeframe_history_v1','stages':stages,'counts':dict(counts),'cases':rows,
        'historical_screen_passed':all(s['review_passed'] for s in stages.values()),
        'broker_eligible':False,'orders_sent':0,'auto_activation':False,
        'limitations':['Historical quote/outcome spread uses the previous closed bar reported spread as a proxy, not actual intrabar tick spreads.',
            'Current frozen fee/currency/margin specification is an approximation for historical dates.',
            'M5 candle outcomes use stop-first ambiguity; exact intrabar management/fills are unverified.',
            'Detector and nominal risk/session checks only; historical macro, visual, final conviction and full execution gates are unavailable.',
            'Chronological splits have no rule tuning here; this remains retrospective evidence, not prospective validation.']}


def advance_ticks(pending,ticks,spec,settings,now):
    """Advance an existing simulated position only from newly observed quotes."""
    from copy import deepcopy
    p=deepcopy(pending);sign=1 if p['side']=='buy' else -1
    sequences=[int(t['time_msc']) for t in ticks]
    if sequences!=sorted(sequences):raise ValueError('unordered_tick_history')
    for tick in ticks:
        seq=int(tick['time_msc'])
        key=f"{tick['bid']}:{tick['ask']}"
        if seq<=p['entry_tick_msc'] or seq<p['last_tick_msc']:continue
        if seq==p['last_tick_msc'] and key in p.get('last_tick_keys',[]):continue
        at=pd.Timestamp(tick['utc'])
        if at>now or at<pd.Timestamp(p['entry_at']):continue
        price=float(tick['bid'] if sign==1 else tick['ask'])
        if not math.isfinite(price) or not price>0:continue
        previous=pd.Timestamp(p.get('last_observed_at',p['entry_at']))
        if (at-previous).total_seconds()>120:p['evidence_complete']=False
        p['last_observed_at']=at.isoformat()
        if seq>p['last_tick_msc']:p['last_tick_keys']=[]
        p['last_tick_msc']=seq;p['last_tick_keys'].append(key)
        elapsed=(at-pd.Timestamp(p['entry_at'])).total_seconds()
        if p['best_r']>=settings.backtest_break_even_r_trigger:
            locked=p['entry_price']+sign*settings.backtest_break_even_lock_r*p['risk_price']
            p['stop']=max(p['stop'],locked) if sign==1 else min(p['stop'],locked)
        if p['best_r']>=settings.backtest_trailing_r_trigger:
            locked=p['entry_price']+sign*max(settings.backtest_break_even_lock_r,p['best_r']-settings.backtest_trailing_buffer_r)*p['risk_price']
            p['stop']=max(p['stop'],locked) if sign==1 else min(p['stop'],locked)
        reason=None
        if sign*(price-p['stop'])<=0:reason='stop_loss'
        elif sign*(price-p['target'])>=0:reason='take_profit'
        elif elapsed>=3600:reason='max_hold'
        elif elapsed>=settings.backtest_stale_exit_bars*300 and p['best_r']<settings.backtest_stale_min_progress_r:reason='stale_exit'
        if reason:
            exit_price=price-sign*3*spec.point
            cash=spec.cash(sign*(exit_price-p['entry_price']),spec.volume_min)-spec.roundtrip_fee_per_lot*spec.volume_min
            return None,{**p,'exit_at':at.isoformat(),'entry_at':p['entry_at'],'net_cash':cash,
                'net_r':cash/p['initial_risk_cash'],'exit_reason':reason,'simulated_exit_price':exit_price,'broker_fill':False}
        p['best_r']=max(p['best_r'],sign*(price-p['entry_price'])/p['risk_price'])
    return p,None
