"""Fixed M5 research proposal. Not registered with the executable trader."""
from copy import deepcopy
from dataclasses import asdict
import math
import pandas as pd
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.distance_units import corrected_atr_signal
from atlas_ai.strategies.indicators import atr

BASE_ELEVATED=.045
BASE_EXTREME=.07


def matched_volatility(m1,m5):
    """Match completed bars over 295 minutes; exclude closures and missing bars."""
    one=m1.copy();five=m5.copy()
    one.index=pd.DatetimeIndex(pd.to_datetime(one.time,utc=True))+pd.Timedelta(minutes=1)
    five.index=pd.DatetimeIndex(pd.to_datetime(five.time,utc=True))+pd.Timedelta(minutes=5)
    if not one.index.is_unique or not five.index.is_unique:raise ValueError('duplicate_candles')
    if not one.index.is_monotonic_increasing or not five.index.is_monotonic_increasing:raise ValueError('unordered_candles')
    minute=one.close.diff().abs().rolling(295).mean()/one.close*100
    coarse=five.close.diff().abs().rolling(59).mean()/five.close*100
    valid_one=one.index.to_series().diff().eq(pd.Timedelta(minutes=1)).rolling(295).sum().eq(295)
    valid_five=five.index.to_series().diff().eq(pd.Timedelta(minutes=5)).rolling(59).sum().eq(59)
    pairs=pd.DataFrame({'m5':coarse,'m1':minute.reindex(five.index),
                        'valid':valid_five & valid_one.reindex(five.index).fillna(False)})
    return pairs[pairs.valid & (pairs.m1>0) & pairs.m5.notna()].drop(columns='valid')


def calibrate(pairs,start,end):
    sample=pairs[(pairs.index>=start)&(pairs.index<end)]
    if len(sample)<1000 or len(set(sample.index.date))<10:
        raise ValueError('at_least_1000_pairs_and_10_dates_required')
    scale=float((sample.m5/sample.m1).median())
    if not math.isfinite(scale) or not 1<=scale<=5:raise ValueError('normalization_outside_declared_1_to_5_bounds')
    return {'scale':scale,'elevated_pct':BASE_ELEVATED*scale,'extreme_pct':BASE_EXTREME*scale,
            'pairs':len(sample),'dates':len(set(sample.index.date)),
            'method':'median_M5_to_M1_absolute_move_ratio_matched_295_minute_windows_no_outcome_optimization'}


def volatility_policy(context,regime,calibration):
    vix=str(context.get('vix_regime',context.get('vix_state','')) or '').lower().strip()
    value=float(regime.get('volatility_pct',0) or 0)
    if vix in {'extreme','panic'} or value>=calibration['extreme_pct']:
        return {'volatility_state':'extreme','volatility_action':'block_new_entries','volatility_reason':'research M5 extreme volatility'}
    if vix in {'high','elevated','stress','fear'} or value>=calibration['elevated_pct']:
        return {'volatility_state':'elevated','volatility_action':'reduce_aggressiveness','volatility_reason':'research M5 elevated volatility'}
    return {'volatility_state':'normal','volatility_action':'allow','volatility_reason':'research M5 volatility within bounds'}


def proposal_candidates(frame,rows,point):
    result=deepcopy(rows);vol=atr(frame);counts={'directional_before':0,'directional_after':0,'closed_candle_confirmation_rejections':0}
    for row in result:
        i=row['index'];at=pd.Timestamp(frame.time.iloc[i]);at=at.tz_localize('UTC') if at.tzinfo is None else at.tz_convert('UTC')
        if i<14 or i>=len(frame)-1 or pd.Timestamp(row['available_at'])!=at+pd.Timedelta(minutes=5):
            raise ValueError('invalid_closed_M5_prediction')
        candle=frame.iloc[i];previous=frame.close.iloc[i-1]
        signals=[]
        for raw in row['signals']:
            signal=TradeSignal(**raw)
            if signal.side in {'buy','sell'} and signal.confidence>0:
                counts['directional_before']+=1
                confirms=(candle.close>candle.open and candle.close>previous) if signal.side=='buy' else (candle.close<candle.open and candle.close<previous)
                if confirms:
                    signal=corrected_atr_signal(signal,float(vol.iloc[i]),point);counts['directional_after']+=1
                else:
                    signal.side='flat';signal.confidence=0.;counts['closed_candle_confirmation_rejections']+=1
            signals.append(asdict(signal))
        row['signals']=signals
    return result,counts
