"""Quote-side first-bar reconstruction; no claim of fills or full portfolio replay."""
import math
import pandas as pd
from atlas_ai.data.broker_clock import server_timezone


def normalize_ticks(raw,settings):
    f=pd.DataFrame(raw)
    if f.empty:return f
    for key in ['time','time_msc','bid','ask']:
        if key not in f:raise ValueError('missing_tick_field:'+key)
    if not f.time_msc.is_monotonic_increasing:raise ValueError('unordered_ticks')
    if ((f.time_msc//1000-f.time).abs()>1).any():raise ValueError('tick_clock_fields_disagree')
    f['utc']=pd.to_datetime(f.time_msc,unit='ms').dt.tz_localize(server_timezone(settings),ambiguous='raise',nonexistent='raise').dt.tz_convert('UTC')
    for row in f.itertuples():
        if not all(math.isfinite(float(x)) and float(x)>0 for x in [row.bid,row.ask]) or row.ask<row.bid:
            raise ValueError('invalid_bid_ask_history')
    return f


def first_barrier(ticks,side,stop,target):
    if side not in {'buy','sell'}:raise ValueError('direction_required')
    if not all(math.isfinite(x) and x>0 for x in [stop,target]):raise ValueError('invalid_barriers')
    if (side=='buy' and stop>=target) or (side=='sell' and stop<=target):raise ValueError('reversed_barriers')
    quote=ticks.bid if side=='buy' else ticks.ask
    stop_hits=ticks.loc[quote<=stop if side=='buy' else quote>=stop]
    target_hits=ticks.loc[quote>=target if side=='buy' else quote<=target]
    s=stop_hits.utc.iloc[0] if len(stop_hits) else None;t=target_hits.utc.iloc[0] if len(target_hits) else None
    if s is None and t is None:return {'outcome':'open_after_first_bar','stop_first_at':None,'target_first_at':None}
    if s is not None and t is not None and s==t:outcome='same_millisecond_order_unresolved'
    else:outcome='stop_first' if t is None or (s is not None and s<t) else 'target_first'
    return {'outcome':outcome,'stop_first_at':s.isoformat() if s is not None else None,
            'target_first_at':t.isoformat() if t is not None else None}


def candle_coverage(ticks,bar,start,end,point):
    rows=ticks[(ticks.utc>=start)&(ticks.utc<end)]
    if rows.empty:return rows,{'usable':False,'reason':'no_ticks_in_requested_UTC_bar'}
    actual={'open':float(rows.bid.iloc[0]),'high':float(rows.bid.max()),'low':float(rows.bid.min()),'close':float(rows.bid.iloc[-1])}
    errors={k:abs(actual[k]-float(bar[k])) for k in actual}
    delay=(rows.utc.iloc[0]-start).total_seconds();tail=(end-rows.utc.iloc[-1]).total_seconds()
    gaps=rows.utc.diff().dt.total_seconds().dropna();maximum=float(gaps.max()) if len(gaps) else None
    usable=max(errors.values())<=point*1.01 and delay<=10 and tail<=10 and maximum is not None and maximum<=30
    return rows,{'usable':usable,'reason':'bid_candle_matches_and_quote_coverage_bounded' if usable else 'clock_or_tick_coverage_not_verified',
                 'ticks':len(rows),'bid_OHLC_absolute_errors':errors,'first_quote_delay_seconds':delay,
                 'last_quote_gap_seconds':tail,'maximum_quote_gap_seconds':maximum,
                 'note':'Agreement with broker bars is a consistency check, not a guarantee of complete venue history or executable fills.'}
