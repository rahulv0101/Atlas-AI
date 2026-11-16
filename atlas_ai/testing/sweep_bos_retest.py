"""One fixed closed-M5 sequence hypothesis. No broker registration or tuning."""
from contextlib import contextmanager
from unittest.mock import patch
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars, entry_gate, TIMEFRAMES
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.smc_composite import structure, entry_geometry
from atlas_ai.strategies.smc_retest import first_retest

NAME = 'smc_sweep_bos_retest_v10'
RULES = {'direction': 'D1_H4_H1_M15_all_aligned', 'sweep_lookback': 20,
    'maximum_sweep_age_bars': 12, 'minimum_sweep_wick_ratio': .42,
    'BOS': 'first_close_through_swing_confirmed_before_sweep_within_next_3_bars',
    'displacement_ATR': 1.25, 'displacement_body_ratio': .6,
    'retest': 'first_visit_to_broken_swing_plus_minus_max_2_points_or_0.1_prior_ATR',
    'maximum_BOS_to_entry_bars': 6, 'touch_confirmation_bars': 2,
    'rejection': 'body_at_least_0.55_range_close_beyond_zone_and_previous_opposite_extreme',
    'earlier_weak_retest_confirmation': 'consumes_setup', 'stop': 'beyond_sweep_and_entire_episode_extreme_plus_original_buffer',
    'target_R_before_costs': 2., 'target': 'only_if_nearest_HTF_liquidity_permits_2R',
    'entry_slippage_points': 3., 'confidence': .65, 'parameter_search': False,
    'broker_eligible': False, 'auto_promotion': False}


def evaluate(frame, context, quote, now):
    base = {'strategy': NAME, 'candidate': None, 'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False}
    def wait(stage, reason):
        return {**base, 'stage': stage, 'reason': reason}
    try:
        now = pd.Timestamp(now)
        f = closed_bars(frame, 'M5', now).tail(80).reset_index(drop=True)
        times = pd.to_datetime(f.time, utc=True)
        if len(f) < 60 or times.iloc[-1]+pd.Timedelta(minutes=5) != now or not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            raise ValueError('fresh_contiguous_closed_M5_required')
        if any(not math.isfinite(float(v)) or float(v) <= 0 for c in ['open', 'high', 'low', 'close'] for v in f[c]):
            raise ValueError('invalid_prices')
        if ((f.high < f[['open', 'close', 'low']].max(axis=1)) | (f.low > f[['open', 'close', 'high']].min(axis=1))).any():
            raise ValueError('invalid_OHLC')
        side = context.get('bias')
        if not entry_gate(context, side)['passed']:
            return wait('higher_timeframe_confluence', 'all_four_higher_timeframes_required')
        at, captured = pd.Timestamp(quote['at']), pd.Timestamp(context['evaluated_at'])
        if any(t.tzinfo is None for t in [now, at, captured]) or not 0 <= (now-at).total_seconds() <= 30 or not 0 <= (now-captured).total_seconds() <= 120:
            raise ValueError('fresh_aware_evidence_required')
        bid, ask, point = (float(quote[k]) for k in ['bid', 'ask', 'point'])
        if not all(math.isfinite(v) and v > 0 for v in [bid, ask, point]) or ask < bid:
            raise ValueError('invalid_quote')
        for tf in TIMEFRAMES:
            e = context['evidence'][tf]
            if e['status'] != 'available' or not 0 < float(e['recent_low']) < float(e['recent_high']) < math.inf:
                raise ValueError('invalid_HTF_targets')
        sign = 1 if side == 'buy' else -1
        vol = atr(f)
        best = wait('liquidity_sweep', 'await_reclaimed_20_bar_liquidity_sweep')
        for s in range(len(f)-3, max(21, len(f)-13)-1, -1):
            sweep, prior = f.iloc[s], f.iloc[s-20:s]
            level = float(prior.low.min() if sign == 1 else prior.high.max())
            span = float(sweep.high-sweep.low)
            wick = float(min(sweep.open, sweep.close)-sweep.low if sign == 1 else sweep.high-max(sweep.open, sweep.close))
            reclaimed = sweep.low < level < sweep.close if sign == 1 else sweep.high > level > sweep.close
            if not reclaimed or span <= 0 or wick/span < .42:
                continue
            broken = structure(f.iloc[:s])['last_swing_high' if sign == 1 else 'last_swing_low']
            if broken is None:
                best = wait('structure_break', 'no_swing_confirmed_before_sweep')
                continue
            extreme = float(sweep.low if sign == 1 else sweep.high)
            later = f.iloc[s+1:]
            if (later.low <= extreme).any() if sign == 1 else (later.high >= extreme).any():
                best = wait('protection', 'sweep_extreme_breached')
                continue
            best = wait('structure_break', 'await_displacement_through_pre_sweep_swing')
            for d in range(s+1, min(s+4, len(f)-1)):
                bar = f.iloc[d]
                crossed = f.close.iloc[d-1] <= broken < bar.close if sign == 1 else f.close.iloc[d-1] >= broken > bar.close
                if not crossed:
                    continue
                a = float(vol.iloc[d-1])
                body, rspan = sign*float(bar.close-bar.open), float(bar.high-bar.low)
                if not math.isfinite(a) or a <= 0 or rspan <= 0 or body < 1.25*a or body/rspan < .6:
                    best = wait('structure_break', 'first_swing_break_lacked_displacement')
                    break
                if len(f)-1-d > 6:
                    best = wait('retest', 'BOS_retest_window_expired')
                    break
                width = max(2*point, .1*a)
                lo, hi = broken-width, broken+width
                visit = first_retest(f.iloc[d+1:], [('broken_swing', lo, hi)], side, extreme)
                if not visit['valid_zones']:
                    best = wait('retest', visit['reason'])
                    break
                last, previous = f.iloc[-1], f.iloc[-2]
                span = float(last.high-last.low)
                boundary = max(hi, float(previous.high)) if sign == 1 else min(lo, float(previous.low))
                if span <= 0 or sign*float(last.close-last.open) <= 0 or abs(float(last.close-last.open))/span < .55 or sign*(float(last.close)-boundary) <= 0:
                    best = wait('rejection', 'await_directional_zone_and_previous_bar_reclaim')
                    break
                episode = f.iloc[s:]
                protection = float(episode.low.min() if sign == 1 else episode.high.max())
                entry = (ask if sign == 1 else bid)+sign*3*point
                geometry = entry_geometry(NAME, side, entry, float(last.close), point, ask-bid, a, protection, context['evidence'])
                if not geometry.get('candidate'):
                    return {**base, **geometry}
                signal = {**geometry['candidate'], 'take_profit_points': 2*geometry['candidate']['stop_loss_points']}
                return {**base, **geometry, 'candidate': signal, 'stage': 'candidate_ready',
                    'reason': 'sweep_BOS_first_retest_rejection_confirmed', 'setup_id': NAME+':'+side+':'+times.iloc[s].isoformat(),
                    'target_reference': entry+sign*signal['take_profit_points']*point,
                    'reward_risk_before_fees_slippage': 2.,
                    'sequence': {'sweep_at': times.iloc[s].isoformat(), 'sweep_level': level,
                        'BOS_at': times.iloc[d].isoformat(), 'broken_swing': broken, 'zone': [lo, hi],
                        'confirmation_at': now.isoformat(), 'retest': visit},
                    'structural_fields': {'location_state': 'fresh_retest', 'momentum_state': 'turning'}}
        return best
    except (KeyError, TypeError, ValueError, OverflowError, IndexError) as exc:
        return wait('input_validation', str(exc))


@contextmanager
def research_features(lookup):
    """Reconstruct evidence for this exact hypothesis in the isolated process."""
    from atlas_ai.trader import AtlasTrader
    original = AtlasTrader._derive_runtime_chart_features
    def supplemented(self, *, df, chosen, regime):
        base = original(self, df=df, chosen=chosen, regime=regime)
        if chosen.strategy != NAME:
            return base
        now = pd.Timestamp(df.time.iloc[-1])+pd.Timedelta(minutes=5)
        evidence = lookup.get(now.isoformat())
        if evidence is None:
            return base
        result = evaluate(df, evidence['context'], evidence['quote'], now)
        if not result.get('candidate') or result['candidate']['side'] != chosen.side:
            return base
        return {**base, 'range_location_state': base['location_state'], 'range_momentum_state': base['momentum_state'],
                **result['structural_fields'], 'sequence_evidence': result['sequence']}
    with patch.object(AtlasTrader, '_derive_runtime_chart_features', supplemented):
        yield
