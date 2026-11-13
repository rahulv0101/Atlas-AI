"""Independent first-visit zones with bounded closed-candle confirmation."""
from atlas_ai.strategies.smc_composite import evaluate as sequence
from atlas_ai.strategies.smc_pullback import setup_context,CONTEXT_RULES

NAME="smc_retest_v3"
RETEST_RULES={"confirmation_bars_after_first_touch":2,"zone_visits":"independent_FVG_and_order_block",
    "prior_confirmation_consumes_setup":True,"setup_extreme_wick_invalidates":True,
    "second_visit_after_leaving_zone":"reject","execution_authority":"none"}


def rejection(bar,side,lo,hi):
    sign=1 if side=='buy' else -1
    return (bar.high>bar.low and sign*float(bar.close-bar.open)>0
        and abs(float(bar.close-bar.open))/float(bar.high-bar.low)>=.35
        and (bar.close>=(lo+hi)/2 if sign==1 else bar.close<=(lo+hi)/2))


def first_retest(bars,zones,side,extreme):
    f=bars.reset_index(drop=True);sign=1 if side=='buy' else -1
    result={'valid_zones':[],'zones':{},'reason':'await_first_zone_touch_and_rejection'}
    if f.empty:return result
    if ((f.low<=extreme).any() if sign==1 else (f.high>=extreme).any()):
        return {**result,'reason':'setup_extreme_breached_before_confirmation'}
    for name,lo,hi in zones:
        touches=[i for i,r in enumerate(f.itertuples()) if r.low<=hi and r.high>=lo]
        if not touches:result['zones'][name]={'state':'untouched'};continue
        first=touches[0];departed=False
        for i in range(first,len(f)):
            row=f.iloc[i];age=i-first;touch=row.low<=hi and row.high>=lo
            state='awaiting_rejection'
            if (row.close<=lo if sign==1 else row.close>=hi):state='zone_close_invalidated'
            elif age>2:state='confirmation_window_expired'
            elif i>first and touch and departed:state='second_visit_rejected'
            if state!='awaiting_rejection':
                result['zones'][name]={'state':state,'bars_since_touch':age};break
            if rejection(row,side,lo,hi):
                if i<len(f)-1:
                    return {**result,'valid_zones':[],'reason':'setup_already_confirmed_on_prior_bar'}
                result['valid_zones'].append([name,lo,hi])
                result['zones'][name]={'state':'first_visit_confirmed','bars_since_touch':age};break
            if (row.low>hi if sign==1 else row.high<lo):departed=True
            result['zones'][name]={'state':state,'bars_since_touch':age}
    if result['valid_zones']:result['reason']='first_zone_visit_confirmed'
    return result


def evaluate(frame,context,quote,now):
    result=sequence(frame,context,quote,now,setup_policy=setup_context,retest_policy=first_retest)
    result['strategy']=NAME;result['schema']='atlas_smc_retest_v3'
    result['rules']={**result['rules'],'context':dict(CONTEXT_RULES),'retest':dict(RETEST_RULES)}
    if result.get('candidate'):
        result['candidate']['strategy']=NAME
        result['setup_id']=NAME+':'+result['side']+':'+result['sweep']['bar_utc']
    return result
