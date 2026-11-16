"""Two fixed aligned M5 hypotheses. Research only; OHLC patterns are heuristics."""
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars, entry_gate, TIMEFRAMES
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.smc_composite import structure, entry_geometry
from atlas_ai.strategies.smc_retest import first_retest

MODELS = ('smc_aligned_fvg_v7', 'smc_aligned_micro_sweep_v7')
RULES = {'direction': 'all_four_D1_H4_H1_M15_must_agree',
         'HTF_countertrend_close_requirement': False,
         'local_setup': 'M5_structure_zone_or_local_liquidity_sweep; no invented_HTF_pullback',
         'FVG': {'maximum_break_age_bars': 8, 'pivot_confirmation_each_side': 2,
                 'minimum_displacement_atr': 1.25, 'minimum_body_ratio': .6,
                 'minimum_gap': 'max_2_points_or_0.05_ATR', 'entry': 'first_fresh_FVG_retest',
                 'protection': 'beyond_entire_gap_and_first_visit_episode_extreme_plus_original_buffer'},
         'sweep': {'local_liquidity_lookback': 5, 'minimum_wick_ratio': .42,
                   'maximum_reclaim_delay_bars': 3, 'minimum_reclaim_body_ratio': .35,
                   'entry': 'first_directional_close_beyond_sweep_candle_opposite_extreme',
                   'protection': 'beyond_actual_sweep_extreme_plus_original_buffer'},
         'entry_slippage_points': 3., 'minimum_target_R_before_costs': 2.,
         'execution_authority': 'none', 'auto_promotion': False}


def detect(frame, context, quote, now):
    """No account balance, outcome labels or mutable state enters detection."""
    def wait(name, stage, reason):
        return {'strategy': name, 'candidate': None, 'stage': stage, 'reason': reason,
                'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False}
    try:
        now = pd.Timestamp(now)
        f = closed_bars(frame, 'M5', now).tail(80).reset_index(drop=True)
        times = pd.to_datetime(f.time, utc=True)
        if len(f) < 60 or times.iloc[-1]+pd.Timedelta(minutes=5) != now:
            raise ValueError('latest_60_closed_M5_candles_required')
        if not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            raise ValueError('recent_M5_gap')
        if any(not math.isfinite(float(v)) or float(v) <= 0 for col in ['open', 'high', 'low', 'close'] for v in f[col]):
            raise ValueError('invalid_M5_prices')
        side = context.get('bias')
        if not entry_gate(context, side)['passed']:
            return {name: wait(name, 'higher_timeframe_confluence', 'all_four_higher_timeframes_required') for name in MODELS}
        bid, ask, point = (float(quote[k]) for k in ['bid', 'ask', 'point'])
        at, evaluated = pd.Timestamp(quote['at']), pd.Timestamp(context['evaluated_at'])
        if any(t.tzinfo is None for t in [now, at, evaluated]) or not 0 <= (now-at).total_seconds() <= 30 or not 0 <= (now-evaluated).total_seconds() <= 120:
            raise ValueError('stale_or_unaware_evidence')
        if not all(math.isfinite(v) and v > 0 for v in [bid, ask, point]) or ask < bid:
            raise ValueError('invalid_quote')
        for tf in TIMEFRAMES:
            e = context['evidence'][tf]
            if e.get('status') != 'available' or not 0 < float(e['recent_low']) < float(e['recent_high']):
                raise ValueError('invalid_HTF_target_evidence')
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return {name: wait(name, 'input_validation', str(exc)) for name in MODELS}
    sign = 1 if side == 'buy' else -1
    entry = (ask if sign == 1 else bid)+sign*RULES['entry_slippage_points']*point
    vol = atr(f)
    last = f.iloc[-1]
    result = {MODELS[0]: wait(MODELS[0], 'structure_FVG', 'await_aligned_BOS_FVG_first_retest'),
              MODELS[1]: wait(MODELS[1], 'micro_sweep', 'await_local_liquidity_sweep_and_reclaim')}

    def geometry(name, extreme, a, key, **extra):
        g = entry_geometry(name, side, entry, float(last.close), point, ask-bid, a, extreme, context['evidence'])
        base = {'strategy': name, 'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False}
        if not g.get('candidate'):
            return {**base, **g}
        return {**base, **g, 'stage': 'candidate_ready', 'reason': 'aligned_natural_structure_observed',
                'setup_id': name+':'+side+':'+times.iloc[key].isoformat(), **extra}

    for d in range(len(f)-3, max(32, len(f)-9)-1, -1):
        level = structure(f.iloc[:d])['last_swing_high' if sign == 1 else 'last_swing_low']
        if level is None:
            continue
        bar = f.iloc[d]
        a = float(vol.iloc[d-1])
        span, body = float(bar.high-bar.low), sign*float(bar.close-bar.open)
        crossed = f.close.iloc[d-1] <= level < bar.close if sign == 1 else f.close.iloc[d-1] >= level > bar.close
        if not (crossed and math.isfinite(a) and a > 0 and span > 0 and body >= 1.25*a and body/span >= .6):
            continue
        lo, hi = (float(f.high.iloc[d-1]), float(f.low.iloc[d+1])) if sign == 1 else (float(f.high.iloc[d+1]), float(f.low.iloc[d-1]))
        if hi-lo < max(2*point, .05*a):
            continue
        extreme = float(bar.low if sign == 1 else bar.high)
        retest = first_retest(f.iloc[d+2:], [('FVG', lo, hi)], side, extreme)
        if not retest['valid_zones']:
            result[MODELS[0]] = wait(MODELS[0], 'FVG_retest', retest['reason'])
            continue
        age = retest['zones']['FVG']['bars_since_touch']
        episode = f.tail(age+1)
        protection = min(lo, float(episode.low.min())) if sign == 1 else max(hi, float(episode.high.max()))
        result[MODELS[0]] = geometry(MODELS[0], protection, a, d, FVG={'low': lo, 'high': hi},
                                    broken_swing=level, retest_evidence=retest)
        if result[MODELS[0]].get('candidate'):
            break
    for s in range(len(f)-2, max(5, len(f)-4)-1, -1):
        bar = f.iloc[s]
        prior = f.iloc[s-5:s]
        level = float(prior.low.min() if sign == 1 else prior.high.max())
        span = float(bar.high-bar.low)
        wick = float(min(bar.open, bar.close)-bar.low if sign == 1 else bar.high-max(bar.open, bar.close))
        swept = bar.low < level < bar.close if sign == 1 else bar.high > level > bar.close
        if not swept or span <= 0 or wick/span < .42:
            continue
        extreme = float(bar.low if sign == 1 else bar.high)
        later = f.iloc[s+1:]
        if (later.low <= extreme).any() if sign == 1 else (later.high >= extreme).any():
            continue
        threshold = float(bar.high if sign == 1 else bar.low)
        def confirms(row):
            rspan = float(row.high-row.low)
            return (rspan > 0 and sign*float(row.close-row.open) > 0 and abs(float(row.close-row.open))/rspan >= .35
                    and sign*(float(row.close)-threshold) > 0)
        if any(confirms(f.iloc[j]) for j in range(s+1, len(f)-1)) or not confirms(last):
            continue
        a = float(vol.iloc[s-1])
        if not math.isfinite(a) or a <= 0:
            continue
        result[MODELS[1]] = geometry(MODELS[1], extreme, a, s, sweep={'level': level, 'extreme': extreme})
        if result[MODELS[1]].get('candidate'):
            break
    return result
