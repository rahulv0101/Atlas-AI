"""One fixed closed-M5 retest hypothesis; no live registration or authority."""
from contextlib import contextmanager
from unittest.mock import patch
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars, entry_gate
from atlas_ai.strategies.indicators import atr

RULES = {'authority': 'research_only', 'direction': 'fresh H1 must match candidate',
         'level_lookback': 5, 'maximum_break_age_bars': 3,
         'break_body_fraction': .55, 'break_minimum_range_ATR': .75,
         'retest_touch_buffer_ATR': .10, 'maximum_level_breach_ATR': .25,
         'confirmation_body_fraction': .40, 'confirmation_close_outer_fraction': .35,
         'confirmation_clearance_ATR': .05, 'prior_retest': 'reject',
         'targets_stops_confidence_thresholds_risk_and_execution_changes': False}


def verify(frame, context, side, now):
    def no(reason): return {'passed': False, 'reason': reason, 'broker_eligible': False}
    if not entry_gate(context or {}, side)['passed']: return no('H1_direction_not_confirmed')
    try:
        now = pd.Timestamp(now)
        if now.tzinfo is None: return no('aware_clock_required')
        evaluated = pd.Timestamp(context['evaluated_at'])
        if evaluated.tzinfo is None or not 0 <= (now-evaluated).total_seconds() <= 900:
            return no('stale_or_future_H1_context')
        f = closed_bars(frame, 'M5', now).tail(60).reset_index(drop=True)
        times = pd.to_datetime(f.time, utc=True)
        if times.iloc[-1]+pd.Timedelta(minutes=5) != now: return no('latest_closed_M5_required')
        if not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all(): return no('M5_gap')
        for c in ('open', 'high', 'low', 'close'):
            if any(not math.isfinite(float(v)) or float(v) <= 0 for v in f[c]): return no('invalid_OHLC')
        if ((f.high < f[['open', 'close', 'low']].max(axis=1)) |
                (f.low > f[['open', 'close', 'high']].min(axis=1))).any(): return no('inconsistent_OHLC')
        sign = 1 if side == 'buy' else -1
        last = f.iloc[-1]
        volatility = atr(f)
        # Most recent eligible break only: no fallback to an older consumed level.
        for k in range(len(f)-2, len(f)-5, -1):
            before, bar = f.iloc[k-5:k], f.iloc[k]
            level = float(before.high.max() if sign == 1 else before.low.min())
            a = float(volatility.iloc[k-1])
            if not math.isfinite(a) or a <= 0: return no('invalid_ATR')
            span = float(bar.high-bar.low)
            if not (span >= .75*a and sign*float(bar.close-bar.open) >= .55*span
                    and sign*(float(bar.close)-level) > .05*a): continue
            # Must break from the original side, rather than an already-established move.
            if sign*(float(f.close.iloc[k-1])-level) > 0: continue
            def touches(row):
                return float(row.low) <= level+.1*a if sign == 1 else float(row.high) >= level-.1*a
            if any(touches(row) for _, row in f.iloc[k+1:-1].iterrows()): return no('prior_retest_consumed')
            if not touches(last): return no('no_first_retest_touch')
            extreme = float(last.low if sign == 1 else last.high)
            if sign*(extreme-level) < -.25*a: return no('level_breached')
            body = sign*float(last.close-last.open)
            last_span = float(last.high-last.low)
            close_position = ((float(last.high-last.close) if sign == 1 else float(last.close-last.low))
                              / last_span) if last_span > 0 else 1.
            if not (body >= .4*last_span and last_span > 0 and close_position <= .35
                    and sign*(float(last.close)-level) >= .05*a
                    and sign*(float(last.close)-float(f.close.iloc[-2])) > 0):
                return no('directional_turn_not_confirmed')
            return {'passed': True, 'reason': 'first_closed_structural_retest_and_directional_turn',
                    'fields': {'location_state': 'fresh_retest', 'momentum_state': 'turning'},
                    'side': side, 'level': level, 'break_at': times.iloc[k].isoformat(),
                    'confirmation_at': times.iloc[-1].isoformat(), 'broker_eligible': False}
        return no('no_fresh_directional_break')
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        return no('invalid_or_incomplete_evidence')


@contextmanager
def overlay(contexts, audit):
    """Per-process research adapter; preserves original features without verified evidence."""
    from atlas_ai.trader import AtlasTrader
    original = AtlasTrader._derive_runtime_chart_features

    def derive(self, *, df, chosen, regime):
        base = original(self, df=df, chosen=chosen, regime=regime)
        if str(self.settings.timeframe).upper() != 'M5': return base
        at = pd.Timestamp(df.time.iloc[-1])
        at = at.tz_localize('UTC') if at.tzinfo is None else at.tz_convert('UTC')
        now = at+pd.Timedelta(minutes=5)
        result = verify(df, contexts.get(now.isoformat(), {}), chosen.side, now)
        audit[(now.isoformat(), chosen.strategy, chosen.side)] = result
        if not result['passed']: return base
        return {**base, 'range_location_state': base['location_state'],
                'range_momentum_state': base['momentum_state'], **result['fields'],
                'structural_timing_evidence': result}

    with patch.object(AtlasTrader, '_derive_runtime_chart_features', derive):
        yield
