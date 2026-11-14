"""Two predeclared entry hypotheses, never broker strategies."""
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars
from atlas_ai.strategies.smc_framework import context_observation
from atlas_ai.strategies.smc_composite import structure,entry_geometry
from atlas_ai.strategies.smc_retest import first_retest
from atlas_ai.strategies.indicators import atr

MODELS=('smc_event_retest_v5','smc_sweep_reclaim_v5')
RULES={'context':'D1_H4_direction_H1_M15_pullback_recent_M5_zone_reference',
    'event_retest':{'impulse_before_break_bars':2,'minimum_impulse_atr':1.25,'minimum_body_ratio':.6,
        'maximum_break_age_bars':10,'prior_M5_direction':'may_oppose_HTF','entry':'first_FVG_or_order_block_retest',
        'stop':'selected_zone_and_first_visit_episode_extreme_plus_existing_buffer'},
    'sweep_reclaim':{'liquidity_lookback':20,'minimum_sweep_wick_ratio':.42,'maximum_confirmation_delay_bars':3,
        'confirmation':'first_directional_close_beyond_sweep_candle_opposite_extreme','minimum_body_ratio':.35,
        'stop':'sweep_extreme_plus_existing_buffer'},
    'minimum_reward_risk_before_costs':2.,'execution_authority':'none','automatic_promotion':False}


def prepare(frame,context,quote,now,name):
    base=context_observation(frame,context,quote,now)
    keys=['mode','broker_eligible','orders_sent','auto_promotion','side','setup_context','trigger_bar_utc','evaluated_at','quote_at']
    report={k:base[k] for k in keys if k in base}
    report.update(strategy=name,schema='atlas_smc_entry_research_v5',rules=RULES,candidate=None)
    if not base.get('setup_context',{}).get('passed') or base['stage'] in {'input_validation','premium_discount'}:
        return None,{**report,'stage':base['stage'],'reason':base['reason']}
    f=closed_bars(frame,'M5',now).tail(80).reset_index(drop=True)
    return f,report


def event_retest(frame,context,quote,now):
    name=MODELS[0];f,report=prepare(frame,context,quote,now,name)
    if f is None:return report
    side=report['side'];sign=1 if side=='buy' else -1
    times=pd.to_datetime(f.time,utc=True);vol=atr(f);point=float(quote['point'])
    entry=float(quote['ask'] if sign==1 else quote['bid']);spread=float(quote['ask'])-float(quote['bid'])
    best={**report,'stage':'structure_reclaim','reason':'await_confirmed_structure_break_with_recent_impulse'}
    for b in range(len(f)-2,max(32,len(f)-11)-1,-1):
        start=b-2;pre=structure(f.iloc[:start].reset_index(drop=True))
        level=pre['last_swing_high' if sign==1 else 'last_swing_low']
        opposite=pre['last_swing_low' if sign==1 else 'last_swing_high']
        if level is None or opposite is None:continue
        crossed=(f.close.iloc[b-1]<=level<f.close.iloc[b] if sign==1 else f.close.iloc[b-1]>=level>f.close.iloc[b])
        if not crossed:continue
        impulses=[]
        for d in range(start,b+1):
            bar=f.iloc[d];a=float(vol.iloc[d-1]);span=float(bar.high-bar.low);body=sign*float(bar.close-bar.open)
            if math.isfinite(a) and a>0 and span>0 and body>=1.25*a and body/span>=.6:impulses.append(d)
        if not impulses:best={**best,'stage':'displacement','reason':'no_directional_impulse_in_pre_break_window'};continue
        for d in impulses:
            a=float(vol.iloc[d-1]);zones=[];formations={}
            lo,hi=(float(f.high.iloc[d-1]),float(f.low.iloc[d+1])) if sign==1 else (float(f.high.iloc[d+1]),float(f.low.iloc[d-1]))
            if hi-lo>=max(2*point,.05*a):zones.append(('FVG',lo,hi));formations['FVG']={'low':lo,'high':hi}
            candidates=[i for i in range(max(0,d-5),d) if sign*float(f.close.iloc[i]-f.open.iloc[i])<0]
            if candidates:
                ob=f.iloc[candidates[-1]];lo,hi=float(ob.low),float(ob.high)
                zones.append(('order_block',lo,hi));formations['order_block']={'low':lo,'high':hi}
            activation=max(b+1,d+2)
            if activation>=len(f):continue
            # A zone used before the structure break is not a fresh entry.
            fresh=[]
            for zone in zones:
                z,lo,hi=zone;formed_at=d+2 if z=='FVG' else d+1;prior=f.iloc[formed_at:activation]
                if prior.empty or not ((prior.low<=hi)&(prior.high>=lo)).any():fresh.append(zone)
            if not fresh:best={**best,'stage':'entry_zone','reason':'no_fresh_zone_after_structure_confirmation'};continue
            global_extreme=min(opposite,float(f.low.iloc[d:b+1].min())) if sign==1 else max(opposite,float(f.high.iloc[d:b+1].max()))
            retest=first_retest(f.iloc[activation:],fresh,side,global_extreme)
            if not retest['valid_zones']:
                best={**best,'stage':'M5_retest','reason':retest['reason'],'retest_evidence':retest};continue
            zone=retest['valid_zones'][0];z,lo,hi=zone
            age=retest['zones'][z]['bars_since_touch'];episode=f.tail(age+1)
            extreme=min(lo,float(episode.low.min())) if sign==1 else max(hi,float(episode.high.max()))
            geometry=entry_geometry(name,side,entry,float(f.close.iloc[-1]),point,spread,a,extreme,context['evidence'])
            if geometry['candidate'] is None:best={**best,**geometry};continue
            return {**report,**geometry,**formations,'stage':'candidate_ready','reason':'structure_then_fresh_zone_confirmation',
                'setup_id':name+':'+side+':'+times.iloc[b].isoformat(),'family':'event_retest',
                'structure_shift':{'type':'BOS' if pre['bias']==side else 'CHOCH' if pre['bias'] in {'buy','sell'} else 'confirmed_structure_reclaim',
                    'bar_utc':times.iloc[b].isoformat(),'broken_swing':level,'prior_structure':pre['bias']},
                'displacement_bar_utc':times.iloc[d].isoformat(),'retest_zone':z,'retest_evidence':retest,
                'invalidation_basis':'selected_zone_plus_actual_first_visit_extreme'}
    return best


def sweep_reclaim(frame,context,quote,now):
    name=MODELS[1];f,report=prepare(frame,context,quote,now,name)
    if f is None:return report
    side=report['side'];sign=1 if side=='buy' else -1;last=f.iloc[-1];times=pd.to_datetime(f.time,utc=True)
    point=float(quote['point']);entry=float(quote['ask'] if sign==1 else quote['bid']);spread=float(quote['ask'])-float(quote['bid']);vol=atr(f)
    best={**report,'stage':'sweep_reclaim','reason':'await_sweep_and_first_directional_reclaim_close'}
    for s in range(len(f)-2,max(20,len(f)-4)-1,-1):
        bar=f.iloc[s];prior=f.iloc[s-20:s];level=float(prior.low.min() if sign==1 else prior.high.max());span=float(bar.high-bar.low)
        wick=float(min(bar.open,bar.close)-bar.low if sign==1 else bar.high-max(bar.open,bar.close))
        swept=bar.low<level<bar.close if sign==1 else bar.high>level>bar.close
        if not swept or span<=0 or wick/span<.42:continue
        extreme=float(bar.low if sign==1 else bar.high);later=f.iloc[s+1:]
        if ((later.low<=extreme).any() if sign==1 else (later.high>=extreme).any()):continue
        confirm=float(bar.high if sign==1 else bar.low)
        def ready(r):
            rspan=float(r.high-r.low)
            return (rspan>0 and sign*float(r.close-r.open)>0 and abs(float(r.close-r.open))/rspan>=.35
                and (r.close>confirm if sign==1 else r.close<confirm))
        if any(ready(f.iloc[i]) for i in range(s+1,len(f)-1)):continue
        if not ready(last):continue
        a=float(vol.iloc[s-1])
        if not math.isfinite(a) or a<=0:continue
        geometry=entry_geometry(name,side,entry,float(last.close),point,spread,a,extreme,context['evidence'])
        if geometry['candidate'] is None:best={**best,**geometry};continue
        return {**report,**geometry,'stage':'candidate_ready','reason':'sweep_followed_by_first_reclaim_confirmation',
            'setup_id':name+':'+side+':'+times.iloc[s].isoformat(),'family':'sweep_reclaim',
            'sweep':{'bar_utc':times.iloc[s].isoformat(),'liquidity_level':level},
            'confirmation':{'type':'sweep_candle_extreme_reclaim','level':confirm,'bar_utc':times.iloc[-1].isoformat()}}
    return best
