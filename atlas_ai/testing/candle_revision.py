"""Compare actual broker candle fields, not CSV formatting or derived indicators."""
import math
import pandas as pd

FIELDS=('open','high','low','close','tick_volume','spread','real_volume')


def candle_map(frame):
    times=pd.to_datetime(frame.time,utc=True)
    if times.duplicated().any() or not times.is_monotonic_increasing:
        raise ValueError('ordered_unique_candles_required')
    result={}
    for i,at in enumerate(times):
        row={}
        for field in FIELDS:
            if field not in frame:raise ValueError('missing_broker_field:'+field)
            value=float(frame.iloc[i][field])
            if not math.isfinite(value):raise ValueError('invalid_broker_field:'+field)
            row[field]=value
        result[at.isoformat()]=row
    return result


def revision_audit(previous,current):
    old,new=candle_map(previous),candle_map(current)
    overlap=sorted(old.keys() & new.keys())
    changed=[]
    for at in overlap:
        fields={k:{'previous':old[at][k],'current':new[at][k]} for k in FIELDS if old[at][k]!=new[at][k]}
        if fields:changed.append({'bar_utc':at,'fields':fields})
    return {'overlapping_bars':len(overlap),'changed_bars':len(changed),'first_changes':changed[:10],
        'compatible_overlap':bool(overlap) and not changed,
        'derived_columns_excluded':['atr_price'],'note':'No overlap is unknown, not proof of unchanged history.'}
