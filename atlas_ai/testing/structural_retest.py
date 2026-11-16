"""Fixed closed-M5 structural entry hypothesis; no executable registration."""
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars,entry_gate
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.smc_composite import structure,entry_geometry

NAME='m5_structural_retest_v1'
RULES={'pivot_confirmation_bars':2,'maximum_break_age_bars':6,'minimum_break_body_ratio':.5,
       'minimum_contiguous_recent_bars':20,
       'minimum_contiguous_recent_bars':20,
       'retest_band_atr':.1,'structural_buffer_atr':.1,'quote_proximity_atr':.25,
       'minimum_target_R_before_costs':2.,'assumed_entry_slippage_points':3.,
       'context':'D1_H4_H1_M15_directional_confluence','execution_authority':'none',
       'stop':'beyond_first_retest_wick_and_broken_level_band; never shrunk_to_budget'}


def evaluate(frame,context,quote,now):
    result={'strategy':NAME,'mode':'research_only','broker_eligible':False,'orders_sent':0,
            'auto_promotion':False,'candidate':None,'stage':'input_validation','reason':'unavailable'}
    def wait(stage,reason,**extra):return {**result,'stage':stage,'reason':reason,**extra}
    try:
        now=pd.Timestamp(now);f=closed_bars(frame,'M5',now).tail(80).reset_index(drop=True)
        if len(f)<60:return wait('input_validation','need_60_closed_M5_candles')
        times=pd.to_datetime(f.time,utc=True)
        if not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all():return wait('input_validation','recent_M5_gap')
        point,bid,ask=[float(quote[k]) for k in ['point','bid','ask']]
        at=pd.Timestamp(quote['at']);captured=pd.Timestamp(context['evaluated_at'])
        if (not all(math.isfinite(x) and x>0 for x in [point,bid,ask]) or ask<bid
            or at.tzinfo is None or not -2<=(now-at).total_seconds()<=30
            or captured.tzinfo is None or not 0<=(now-captured).total_seconds()<=120):
            raise ValueError('invalid_or_stale_quote_context')
        side=context.get('bias')
        if not entry_gate(context,side)['passed']:return wait('higher_timeframe_confluence','all_four_higher_timeframes_required')
        if not all(math.isfinite(float(x)) and float(x)>0 for col in ['open','high','low','close'] for x in f[col]):
            raise ValueError('invalid_prices')
        if ((f.high<f[['open','close','low']].max(axis=1))|(f.low>f[['open','close','high']].min(axis=1))).any():raise ValueError('invalid_OHLC')
    except (KeyError,TypeError,ValueError,OverflowError) as exc:return wait('input_validation',str(exc))
    result.update(side=side,evaluated_at=now.isoformat(),trigger_bar_utc=times.iloc[-1].isoformat())
    sign=1 if side=='buy' else -1;vol=atr(f);last=f.iloc[-1]
    best=wait('structure_break','await_confirmed_swing_break')
    for b in range(len(f)-2,max(32,len(f)-7)-1,-1):
        pre=structure(f.iloc[:b].reset_index(drop=True))
        level=pre['last_swing_high' if sign==1 else 'last_swing_low']
        if level is None:continue
        previous=float(f.close.iloc[b-1]);close=float(f.close.iloc[b])
        crossed=previous<=level<close if sign==1 else previous>=level>close
        if not crossed:continue
        bar=f.iloc[b];span=float(bar.high-bar.low);body=sign*float(bar.close-bar.open)
        a=float(vol.iloc[b-1])
        if span<=0 or body/span<.5 or not math.isfinite(a) or a<=0:continue
        band=max(2*point,.1*a);later=f.iloc[b+1:]
        touches=(later.low<=level+band)&(later.high>=level-band)
        touched=list(later.index[touches])
        if not touched:best=wait('first_retest','await_first_level_retest');continue
        first=touched[0]
        if first!=len(f)-1:best=wait('first_retest','first_visit_already_used_or_unconfirmed');continue
        if (sign*(later.iloc[:-1].close-level)<-band).any():best=wait('first_retest','level_failed_before_retest');continue
        if sign*float(last.close-last.open)<=0 or sign*(float(last.close)-level)<=0:
            best=wait('first_retest','first_touch_has_no_directional_rejection');continue
        extreme=min(float(last.low),level-band) if sign==1 else max(float(last.high),level+band)
        market_entry=ask if sign==1 else bid
        # Geometry and replay use the same adverse entry assumption. It must
        # not move the simulated stop inside the recorded invalidation.
        entry=market_entry+sign*RULES['assumed_entry_slippage_points']*point
        try:geometry=entry_geometry(NAME,side,entry,float(last.close),point,ask-bid,a,extreme,context['evidence'])
        except (KeyError,TypeError,ValueError,OverflowError):return wait('input_validation','invalid_higher_timeframe_target_evidence')
        if geometry['candidate'] is None:best={**result,**geometry};continue
        return {**result,**geometry,'stage':'candidate_ready','reason':'confirmed_break_then_first_structural_retest',
                'setup_id':NAME+':'+side+':'+times.iloc[b].isoformat(),
                'break_bar_utc':times.iloc[b].isoformat(),'broken_level':level,'retest_band':band,
                'retest_extreme':float(last.low if sign==1 else last.high),'market_quote_entry':market_entry,
                'invalidation_basis':RULES['stop']}
    return best
