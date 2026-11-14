"""Two explicit SMC archetypes; one context, protection and risk boundary."""
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars
from atlas_ai.strategies.smc_retest import evaluate as reversal,first_retest,RETEST_RULES
from atlas_ai.strategies.smc_composite import structure,entry_geometry,evaluate as sequence
from atlas_ai.strategies.smc_pullback import CONTEXT_RULES,setup_context
from atlas_ai.strategies.indicators import atr

NAME='smc_framework_v4'
FRAMEWORK_RULES={'families':['sweep_reversal','BOS_continuation'],'priority':'complete_sweep_reversal_then_complete_BOS_continuation',
    'continuation_requires_sweep':False,'continuation_requires_aligned_pre_structure':True,
    'continuation_max_BOS_age_bars':10,'entry_zone':'first_FVG_or_order_block_retest',
    'minimum_zones':1,'execution_authority':'none','auto_promotion':False}
FRAMEWORK_RULES['reaction_location']='recent_12_closed_M5_bar_extreme_reached_H1_or_M15_zone_before_entry'


def context_observation(frame,context,quote,now):
    try:
        closed=closed_bars(frame,'M5',now).tail(80)
        side=context.get('details',{}).get('D1')
        recent=closed.tail(12);column='low' if side=='buy' else 'high'
        index=recent[column].idxmin() if side=='buy' else recent[column].idxmax()
        reference={'price':float(recent.loc[index,column]),'bar_utc':pd.to_datetime(recent.loc[index,'time'],utc=True).isoformat(),
            'basis':'recent_closed_M5_pullback_extreme_against_current_closed_HTF_ranges'}
        def policy(ctx,q):return setup_context(ctx,q,reaction_reference=reference)
        left=sequence(frame,context,quote,now,setup_policy=policy,retest_policy=first_retest)
    except (KeyError,TypeError,ValueError,OverflowError):
        left=reversal(frame,context,quote,now)
    return left


def evaluate(frame,context,quote,now):
    left=context_observation(frame,context,quote,now)
    result={**left,'strategy':NAME,'schema':'atlas_smc_framework_v4',
        'rules':{**left['rules'],'context':{**CONTEXT_RULES,'location':'recent_M5_pullback_reference_in_H1_or_M15_half'},
            'retest':dict(RETEST_RULES),'framework':dict(FRAMEWORK_RULES)},'family':'sweep_reversal'}
    if left.get('candidate'):
        result['candidate']={**left['candidate'],'strategy':NAME}
        result['setup_id']=NAME+':sweep:'+left['side']+':'+left['sweep']['bar_utc']
        return result
    # Continuation must pass exactly the same input freshness/context gates.
    if not left.get('setup_context',{}).get('passed') or left['stage'] in {'input_validation','premium_discount'}:
        return result
    f=closed_bars(frame,'M5',now).tail(80).reset_index(drop=True)
    side=left['side'];sign=1 if side=='buy' else -1
    point=float(quote['point']);entry=float(quote['ask'] if sign==1 else quote['bid']);spread=float(quote['ask'])-float(quote['bid'])
    volatility=atr(f);times=pd.to_datetime(f.time,utc=True)
    best={**result,'family':'BOS_continuation','stage':'continuation_BOS','reason':'await_aligned_BOS_displacement',
        'family_statuses':{'sweep_reversal':{'stage':left['stage'],'reason':left['reason']}}}
    for d in range(len(f)-3,max(30,len(f)-11)-1,-1):
        pre=structure(f.iloc[:d].reset_index(drop=True))
        level=pre['last_swing_high' if sign==1 else 'last_swing_low']
        if pre['bias']!=side or level is None:continue
        bar=f.iloc[d];a=float(volatility.iloc[d-1]);span=float(bar.high-bar.low);body=sign*float(bar.close-bar.open)
        crossed=(f.close.iloc[d-1]<=level<bar.close if sign==1 else f.close.iloc[d-1]>=level>bar.close)
        if not (crossed and math.isfinite(a) and a>0 and span>0 and body>=1.25*a and body/span>=.6):continue
        zones=[];formation={}
        gap_lo,gap_hi=(float(f.high.iloc[d-1]),float(f.low.iloc[d+1])) if sign==1 else (float(f.high.iloc[d+1]),float(f.low.iloc[d-1]))
        if gap_hi-gap_lo>=max(2*point,.05*a):
            zones.append(('FVG',gap_lo,gap_hi));formation['FVG']={'low':gap_lo,'high':gap_hi}
        opposites=[i for i in range(max(0,d-5),d) if sign*float(f.close.iloc[i]-f.open.iloc[i])<0]
        if opposites:
            ob=f.iloc[opposites[-1]];lo,hi=float(ob.low),float(ob.high)
            zones.append(('order_block',lo,hi));formation['order_block']={'low':lo,'high':hi}
            extreme=lo if sign==1 else hi
        else:extreme=float(bar.low if sign==1 else bar.high)
        if not zones:
            best={**best,'stage':'continuation_zone','reason':'BOS_has_no_FVG_or_order_block'};continue
        retest=first_retest(f.iloc[d+2:],zones,side,extreme)
        if not retest['valid_zones']:
            best={**best,'stage':'continuation_retest','reason':retest['reason'],'retest_evidence':retest,
                'structure_shift':{'type':'BOS','bar_utc':times.iloc[d].isoformat(),'broken_swing':level},**formation};continue
        geometry=entry_geometry(NAME,side,entry,float(f.close.iloc[-1]),point,spread,a,extreme,context['evidence'])
        if geometry['candidate'] is None:
            best={**best,**geometry};continue
        return {**result,**geometry,**formation,'family':'BOS_continuation','stage':'candidate_ready',
            'reason':'complete_continuation_sequence_observed','retest_zone':retest['valid_zones'][0][0],'retest_evidence':retest,
            'setup_id':NAME+':BOS:'+side+':'+times.iloc[d].isoformat(),
            'structure_shift':{'type':'BOS','bar_utc':times.iloc[d].isoformat(),'broken_swing':level,'prior_structure':pre['bias']},
            'family_statuses':{'sweep_reversal':{'stage':left['stage'],'reason':left['reason']}}}
    return best
