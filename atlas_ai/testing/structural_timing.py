"""Reconstruct bounded structural timing evidence; research only.

No raw strategy label can approve evidence. Closed OHLC, all-four confluence,
first-episode freshness and actual directional confirmation must agree.
"""
import math
from contextlib import contextmanager
from unittest.mock import patch
import pandas as pd
from atlas_ai.data.top_down import closed_bars
from atlas_ai.strategies.smc_research_confluence import entry_gate
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.smc_composite import structure

RULES = {'scope': 'research_only_not_live_policy', 'maximum_anchor_age_M5_bars': 3,
         'turning': 'first_closed_directional_body_at_least_0.55_range_beyond_previous_bar_and_setup_confirmation_level',
         'location': 'independently_reconstructed_first_FVG_visit_or_five_bar_sweep_reclaim',
         'all_four_confluence': True, 'second_visit_or_prior_confirmation': 'reject',
         'risk_threshold_confidence_and_volatility_changes': False}

RESEARCH_NAMES = {'smc_structural_timing_fvg_v8', 'smc_structural_timing_sweep_v8'}


@contextmanager
def research_features(lookup, audit):
    """Explicit per-process adapter; unrelated strategies retain exact features."""
    from atlas_ai.trader import AtlasTrader
    original = AtlasTrader._derive_runtime_chart_features

    def supplemented(self, *, df, chosen, regime):
        base = original(self, df=df, chosen=chosen, regime=regime)
        name = getattr(chosen, 'strategy', '')
        if name not in RESEARCH_NAMES:
            return base
        at = pd.Timestamp(df.time.iloc[-1])
        if at.tzinfo is None:
            at = at.tz_localize('UTC')
        key = (name, (at+pd.Timedelta(minutes=5)).isoformat())
        row = lookup.get(key)
        if row is None:
            return base
        evidence = verify(df, row['context'], row['quote'], row['anchor'], row['anchor_at'], row['now'])
        audit[key] = evidence
        if not evidence['passed']:
            return {**base, 'structural_timing_evidence': evidence}
        return {**base, 'range_location_state': base['location_state'], 'range_momentum_state': base['momentum_state'],
                **evidence['fields'], 'structural_timing_evidence': evidence}

    with patch.object(AtlasTrader, '_derive_runtime_chart_features', supplemented):
        yield


def verify(frame, context, quote, anchor, anchor_at, now):
    result = {'passed': False, 'fields': {}, 'reason': 'structural_evidence_unavailable'}

    def reject(reason):
        return {**result, 'reason': reason}

    try:
        now, anchor_at = pd.Timestamp(now), pd.Timestamp(anchor_at)
        at, evaluated = pd.Timestamp(quote['at']), pd.Timestamp(context['evaluated_at'])
        if any(t.tzinfo is None for t in [now, anchor_at, at, evaluated]):
            return reject('aware_evidence_required')
        if not 0 <= (now-anchor_at).total_seconds() <= 900:
            return reject('anchor_not_fresh')
        if not 0 <= (now-at).total_seconds() <= 30 or not 0 <= (now-evaluated).total_seconds() <= 120:
            return reject('quote_or_context_not_fresh')
        side = anchor['candidate']['side']
        if not entry_gate(context, side)['passed']:
            return reject('all_four_alignment_required')
        sign = 1 if side == 'buy' else -1
        name = anchor['candidate']['strategy']
        allowed = {'smc_aligned_micro_sweep_v7', 'smc_aligned_fvg_v7'}
        if name not in allowed or not anchor['setup_id'].startswith(name+':'+side+':'):
            return reject('unsupported_or_mismatched_anchor')
        source_at = pd.Timestamp(anchor['setup_id'].split(':'+side+':', 1)[1])
        f = closed_bars(frame, 'M5', now).tail(90).reset_index(drop=True)
        times = pd.to_datetime(f.time, utc=True)
        if len(f) < 60 or times.iloc[-1]+pd.Timedelta(minutes=5) != now:
            return reject('latest_closed_M5_bar_required')
        if not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all():
            return reject('recent_M5_gap')
        if any(not math.isfinite(float(v)) or float(v) <= 0 for col in ['open', 'high', 'low', 'close'] for v in f[col]):
            return reject('invalid_OHLC')
        if ((f.high < f[['open', 'close', 'low']].max(axis=1)) | (f.low > f[['open', 'close', 'high']].min(axis=1))).any():
            return reject('inconsistent_OHLC')
        matches = list(f.index[times == source_at])
        if len(matches) != 1:
            return reject('setup_bar_not_in_closed_history')
        index = matches[0]
        point, bid, ask = (float(quote[k]) for k in ['point', 'bid', 'ask'])
        stop = float(anchor['stop_reference'])
        if not all(math.isfinite(v) and v > 0 for v in [point, bid, ask, stop]) or ask < bid:
            return reject('invalid_quote_or_stop')
        a = float(atr(f).iloc[-1])
        entry = ask if sign == 1 else bid
        if not math.isfinite(a) or a <= 0 or abs(entry-float(f.close.iloc[-1])) > .25*a:
            return reject('quote_away_from_confirmed_close')
        since_anchor = f.loc[times >= anchor_at-pd.Timedelta(minutes=5)]
        if side == 'buy' and since_anchor.low.min() <= stop:
            return reject('original_stop_breached')

        def directional(i, threshold):
            row, prior = f.iloc[i], f.iloc[i-1]
            span = float(row.high-row.low)
            opposite = float(prior.high if sign == 1 else prior.low)
            return (span > 0 and sign*float(row.close-row.open) > 0
                    and abs(float(row.close-row.open))/span >= .55
                    and sign*(float(row.close)-threshold) > 0
                    and sign*(float(row.close)-opposite) > 0)

        if name == 'smc_aligned_micro_sweep_v7':
            if index < 5 or index >= len(f)-1:
                return reject('closed_sweep_and_reclaim_required')
            bar = f.iloc[index]
            prior = f.iloc[index-5:index]
            level = float(prior.low.min() if sign == 1 else prior.high.max())
            extreme = float(bar.low if sign == 1 else bar.high)
            claimed = anchor['sweep']
            if not math.isclose(float(claimed['level']), level, abs_tol=point*.1) or not math.isclose(float(claimed['extreme']), extreme, abs_tol=point*.1):
                return reject('claimed_sweep_does_not_match_candles')
            span = float(bar.high-bar.low)
            wick = float(min(bar.open, bar.close)-bar.low if sign == 1 else bar.high-max(bar.open, bar.close))
            swept = bar.low < level < bar.close if sign == 1 else bar.high > level > bar.close
            later = f.iloc[index+1:]
            breached = (later.low <= extreme).any() if sign == 1 else (later.high >= extreme).any()
            protected = stop < extreme if sign == 1 else stop > extreme+(ask-bid)
            if not swept or span <= 0 or wick/span < .42 or breached or not protected:
                return reject('sweep_or_original_protection_invalid')
            threshold = float(bar.high if sign == 1 else bar.low)
            location = 'sweep_rejection'
            first_allowed = index+1
        else:
            if index < 32 or index+2 >= len(f):
                return reject('confirmed_FVG_and_retest_required')
            bar = f.iloc[index]
            pre = structure(f.iloc[:index])
            level = pre['last_swing_high' if sign == 1 else 'last_swing_low']
            lo, hi = (float(f.high.iloc[index-1]), float(f.low.iloc[index+1])) if sign == 1 else (float(f.high.iloc[index+1]), float(f.low.iloc[index-1]))
            claimed = anchor['FVG']
            if not math.isclose(float(claimed['low']), lo, abs_tol=point*.1) or not math.isclose(float(claimed['high']), hi, abs_tol=point*.1):
                return reject('claimed_FVG_does_not_match_candles')
            before_atr = float(atr(f).iloc[index-1])
            span = float(bar.high-bar.low)
            crossed = level is not None and (f.close.iloc[index-1] <= level < bar.close if sign == 1 else f.close.iloc[index-1] >= level > bar.close)
            if not (crossed and math.isfinite(before_atr) and before_atr > 0 and span > 0
                    and sign*float(bar.close-bar.open) >= 1.25*before_atr
                    and abs(float(bar.close-bar.open))/span >= .6
                    and hi-lo >= max(2*point, .05*before_atr)):
                return reject('FVG_structure_not_reconstructed')
            visits = f.iloc[index+2:]
            touched = list(visits.index[(visits.low <= hi) & (visits.high >= lo)])
            if not touched or len(f)-1-touched[0] > 3:
                return reject('first_FVG_visit_not_fresh')
            first_allowed = touched[0]
            episode = f.iloc[first_allowed:]
            if (episode.close <= lo).any() if sign == 1 else (episode.close >= hi).any():
                return reject('FVG_close_invalidated')
            departed = False
            for row in episode.itertuples():
                touch = row.low <= hi and row.high >= lo
                if departed and touch:
                    return reject('second_FVG_visit')
                if row.low > hi if sign == 1 else row.high < lo:
                    departed = True
            protected = stop < min(lo, float(episode.low.min())) if sign == 1 else stop > max(hi, float(episode.high.max()))+(ask-bid)
            if not protected:
                return reject('FVG_original_protection_invalid')
            threshold = (lo+hi)/2
            location = 'fresh_retest'
        if not directional(len(f)-1, threshold):
            return reject('directional_body_and_structure_turn_not_confirmed')
        if any(directional(i, threshold) for i in range(max(1, first_allowed), len(f)-1)):
            return reject('structural_confirmation_already_occurred')
        return {'passed': True, 'reason': 'closed_structural_location_and_turn_verified',
                'fields': {'location_state': location, 'momentum_state': 'turning'},
                'evidence': {'side': side, 'anchor_at': anchor_at.isoformat(), 'setup_bar_at': source_at.isoformat(),
                             'confirmation_at': now.isoformat(), 'body_ratio_minimum': .55, 'first_confirmation': True,
                             'location_source': 'reconstructed_closed_OHLC', 'broker_eligible': False}}
    except (KeyError, TypeError, ValueError, OverflowError, IndexError):
        return reject('invalid_or_incomplete_structural_evidence')
