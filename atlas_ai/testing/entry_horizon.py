"""Fixed research entry/horizon interventions. No live policy or self-tuning."""
from copy import deepcopy
import math
import statistics
import pandas as pd
from atlas_ai.data.top_down import closed_bars
from atlas_ai.strategies.smc_composite import structure

RULES = {'entry': {'M5_trend': 'existing_8_21_close_measure_aligned_for_two_consecutive_closed_bars',
                   'structure': 'close_beyond_prior_confirmed_two_left_two_right_swing'},
         'target': {'target_R_before_costs': 2., 'hold_M5_bars': 12,
                    'reference': 'median_range_of_last_20_nonoverlapping_closed_12_bar_blocks',
                    'minimum_contiguous_blocks': 12, 'feasibility': '2R_distance_not_above_reference_range'},
         'stop_risk_and_management_changes': False, 'parameter_search': False,
         'broker_eligible': False, 'selection': 'only_preregistered_combined_intervention_may_support_hypothesis; never_best_lane_selection'}


def eligible_window(times, i, boundary):
    """Mirror detector's last-20 continuity; older closed levels may span closures."""
    if i < 59 or i+12 >= len(times):
        return False
    now = times.iloc[i]+pd.Timedelta(minutes=5)
    return (times.iloc[i+1] == now
            and times.iloc[i+12]+pd.Timedelta(minutes=5) <= boundary
            and times.iloc[i-19:i+13].diff().dropna().eq(pd.Timedelta(minutes=5)).all())


def entry_check(trader, frame, side, now):
    f = closed_bars(frame, 'M5', pd.Timestamp(now))
    if len(f) < 60:
        return {'passed': False, 'reason': 'need_closed_M5_context'}
    times = pd.to_datetime(f.time, utc=True)
    if times.iloc[-1]+pd.Timedelta(minutes=5) != pd.Timestamp(now) or not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all():
        return {'passed': False, 'reason': 'M5_context_not_fresh_or_contiguous'}
    if side not in {'buy', 'sell'}:
        return {'passed': False, 'reason': 'direction_required'}
    expected = 'uptrend' if side == 'buy' else 'downtrend'
    current = trader._entry_timing_context(f, {})['entry_trend_state']
    previous = trader._entry_timing_context(f.iloc[:-1], {})['entry_trend_state']
    observed = {'current_M5_trend': current, 'previous_M5_trend': previous, 'expected': expected}
    if current != expected or previous != expected:
        return {'passed': False, 'reason': 'await_two_closed_aligned_M5_trends', **observed}
    pre = structure(f.iloc[:-1].tail(80).reset_index(drop=True))
    level = pre['last_swing_high' if side == 'buy' else 'last_swing_low']
    passed = level is not None and (float(f.close.iloc[-1]) > level if side == 'buy' else float(f.close.iloc[-1]) < level)
    return {'passed': passed, 'reason': 'M5_trend_and_structure_confirmed' if passed else 'await_confirmed_M5_swing_break',
            'swing_reference': level, **observed}


def target_plan(signal, frame, point, now):
    """Choose an attainable research target without moving an original stop."""
    original = deepcopy(signal)
    try:
        stop, target = float(signal['stop_loss_points']), float(signal['take_profit_points'])
        if not all(math.isfinite(v) and v > 0 for v in [point, stop, target]) or target+1e-8 < 2*stop:
            raise ValueError('original_geometry_does_not_allow_2R')
        f = closed_bars(frame, 'M5', pd.Timestamp(now)).tail(240).reset_index(drop=True)
        times = pd.to_datetime(f.time, utc=True)
        if f.empty or times.iloc[-1]+pd.Timedelta(minutes=5) != pd.Timestamp(now):
            raise ValueError('latest_closed_M5_required')
        ranges = []
        for end in range(len(f), 11, -12):
            block = f.iloc[end-12:end]
            block_times = times.iloc[end-12:end]
            if not block_times.diff().dropna().eq(pd.Timedelta(minutes=5)).all():
                continue
            values = [float(v) for col in ['high', 'low'] for v in block[col]]
            if not all(math.isfinite(v) and v > 0 for v in values):
                continue
            span = float(block.high.max()-block.low.min())
            if span > 0:
                ranges.append(span)
        if len(ranges) < 12:
            raise ValueError('insufficient_contiguous_past_hour_blocks')
        reference = statistics.median(ranges)
        distance = 2*stop*point
        evidence = {'past_hour_blocks': len(ranges), 'median_past_hour_range': reference,
                    'proposed_target_distance': distance, 'stop_points_unchanged': stop}
        if distance > reference:
            return False, original, '2R_exceeds_typical_past_hour_range', evidence
        return True, {**original, 'take_profit_points': 2*stop}, '2R_fits_past_hour_reference', evidence
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return False, original, str(exc), {}
