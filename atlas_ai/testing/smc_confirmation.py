"""Bounded, research-only confirmation adapter for frozen SMC v5 observations.

No strategy registration, broker commands, policy mutation, or learned tuning.
"""
from copy import deepcopy
import math
import pandas as pd
from atlas_ai.data.top_down import closed_bars, entry_gate, TIMEFRAMES
from atlas_ai.strategies.indicators import atr

MODELS = {'smc_event_retest_v5': 'smc_event_retest_confirmed_v6',
          'smc_sweep_reclaim_v5': 'smc_sweep_reclaim_confirmed_v6'}
RULES = {'context': 'existing_D1_H4_H1_M15_entry_gate', 'confirmation_delay_closed_M5_bars': 3,
         'pending_limit': 'one_setup_per_model; first_anchor_priority; expiry_consumes_current_bar',
         'bar_updates': 'one_decision_per_closed_bar; duplicates_ignored; unavailable_windows_retire',
         'confirmation': 'existing_shared_timing_gate_and_directional_M5_close_beyond_anchor_close',
         'protection': 'original_buffered_structural_stop_never_tightened; Ask_spread_cannot_reduce_sell_protection',
         'target': 'nearest_current_HTF_liquidity_at_least_2R_before_costs',
         'budget': 'explicit_frozen_nominal_budget_including_roundtrip_fees_and_3_points_slippage_each_side',
         'stale_or_breached_setup': 'retire_no_rearm', 'unavailable_confirmation_windows': 'retire',
         'execution_authority': 'none', 'auto_promotion': False}


def affordable(signal, entry, spec, settings, limits, *, spread_points=0.):
    """Reject unaffordable natural geometry; never manufacture a shorter stop."""
    from atlas_ai.risk.risk_manager import RiskManager
    from atlas_ai.risk.volume import floor_volume
    balance = settings.backtest_initial_balance
    cap = min(.01, limits['lot_cap'], spec.volume_max)
    minimum = max(spec.trade_stops_level, spec.trade_freeze_level) + max(2, round(spread_points*.35))
    if min(signal['stop_loss_points'], signal['take_profit_points']) < minimum:
        return False, 'broker_minimum_protection', {'minimum_protection_points': minimum}
    volume = RiskManager(settings).lot_size(balance, signal['stop_loss_points'], spec.tick_value_loss,
        point_size=spec.point, tick_size=spec.tick_size, volume_step=spec.volume_step, minimum_volume=spec.volume_min)
    volume = floor_volume(min(volume, cap), spec.volume_step)
    stop_risk = abs(spec.cash(-signal['stop_loss_points'] * spec.point, spec.volume_min))
    friction = spec.roundtrip_fee_per_lot * spec.volume_min + abs(spec.cash(-6 * spec.point, spec.volume_min))
    evidence = {'minimum_lot_stop_risk': stop_risk, 'minimum_lot_friction': friction,
                'nominal_risk_budget': balance * settings.max_risk_per_trade}
    if volume < spec.volume_min or stop_risk + friction > evidence['nominal_risk_budget']:
        return False, 'natural_stop_exceeds_minimum_lot_risk_budget', evidence
    if spec.margin_per_lot * spec.volume_min > balance:
        return False, 'minimum_lot_margin_unavailable', evidence
    return True, 'natural_geometry_affordable', evidence


class Confirmation:
    def __init__(self, source_model, *, research_name=None):
        self.source_model = source_model
        self.name = MODELS[source_model] if research_name is None else research_name
        self.pending = None
        self.retired = set()
        self.last_bar = None

    def step(self, raw, frame, context, quote, now, timing_check, budget_check):
        now = pd.Timestamp(now)
        result = {'strategy': self.name, 'mode': 'research_only', 'broker_eligible': False,
                  'auto_promotion': False, 'orders_sent': 0, 'candidate': None}

        def finish(stage, reason, **evidence):
            return {**result, 'stage': stage, 'reason': reason, **evidence}

        def retire():
            if self.pending:
                self.retired.add(self.pending['id'])
            self.pending = None

        try:
            frame = closed_bars(frame, 'M5', now).copy()
            times = pd.to_datetime(frame.time, utc=True)
            if len(frame) < 60 or times.iloc[-1] + pd.Timedelta(minutes=5) != now:
                raise ValueError('latest_closed_M5_bar_required')
            if not times.tail(20).diff().dropna().eq(pd.Timedelta(minutes=5)).all():
                raise ValueError('recent_M5_gap')
            if any(not math.isfinite(float(v)) or float(v) <= 0 for col in ['open', 'high', 'low', 'close'] for v in frame[col]):
                raise ValueError('invalid_M5_prices')
            at = pd.Timestamp(quote['at'])
            captured = pd.Timestamp(context['evaluated_at'])
            if now.tzinfo is None or at.tzinfo is None or captured.tzinfo is None:
                raise ValueError('aware_evidence_required')
            if not 0 <= (now-at).total_seconds() <= 30 or not 0 <= (now-captured).total_seconds() <= 120:
                raise ValueError('stale_quote_or_context')
            bid, ask, point = (float(quote[k]) for k in ['bid', 'ask', 'point'])
            if not all(math.isfinite(x) and x > 0 for x in [bid, ask, point]) or ask < bid:
                raise ValueError('invalid_quote')
            if self.last_bar is not None and now == self.last_bar:
                return finish('input_validation', 'await_new_closed_M5_bar')
            unavailable = self.pending is not None and self.last_bar is not None and now-self.last_bar != pd.Timedelta(minutes=5)
            if self.last_bar is not None and now < self.last_bar:
                raise ValueError('out_of_order_M5_bar')
            if unavailable:
                retire()
            self.last_bar = now
            if unavailable and not raw.get('candidate'):
                return finish('confirmation', 'unavailable_confirmation_window_retired')
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            retire()
            return finish('input_validation', str(exc))

        if self.pending:
            age = (now-self.pending['at']).total_seconds()/300
            if age > RULES['confirmation_delay_closed_M5_bars']:
                retire()
                return finish('confirmation', 'confirmation_window_expired')
        if not self.pending:
            if not raw.get('candidate'):
                return finish('source_setup', 'await_complete_v5_setup')
            side = raw['candidate']['side']
            if not entry_gate(context, side)['passed']:
                return finish('higher_timeframe_confluence', 'all_four_higher_timeframes_required')
            identity = raw['setup_id']
            if identity in self.retired:
                return finish('confirmation', 'setup_already_retired')
            self.pending = {'id': identity, 'at': now, 'side': side,
                            'stop': float(raw['stop_reference']), 'spread': ask-bid,
                            'anchor_close': float(frame.close.iloc[-1]),
                            'signal': deepcopy(raw['candidate'])}
        anchor = self.pending
        side = anchor['side']
        sign = 1 if side == 'buy' else -1
        if not entry_gate(context, side)['passed']:
            retire()
            return finish('higher_timeframe_confluence', 'alignment_lost_before_confirmation')
        last = frame.iloc[-1]
        # Original buffered Bid invalidation is fixed. A widened Ask spread may
        # widen sell protection; a narrower one cannot tighten it.
        bid_stop = anchor['stop'] - (anchor['spread'] if sign == -1 else 0)
        episode = frame.loc[times >= anchor['at'] - pd.Timedelta(minutes=5)]
        breached = episode.low.min() <= bid_stop if sign == 1 else episode.high.max() >= bid_stop
        if breached:
            retire()
            return finish('protection', 'original_structural_protection_breached')
        directional = sign * float(last.close-last.open) > 0 and sign * (float(last.close)-anchor['anchor_close']) >= 0
        timing = timing_check({**anchor['signal'], 'strategy': self.name})
        if not directional or not timing:
            return finish('confirmation', 'await_actual_directional_M5_timing_confirmation')
        entry = round((ask if sign == 1 else bid) + sign * 3 * point, int(quote['digits']))
        stop = anchor['stop'] if sign == 1 else anchor['stop'] + max(0., ask-bid-anchor['spread'])
        stop = round((math.floor(stop/point) if sign == 1 else math.ceil(stop/point))*point, int(quote['digits']))
        risk = sign*(entry-stop)
        volatility = float(atr(frame).iloc[-1])
        if not math.isfinite(volatility) or volatility <= 0 or abs(entry-float(last.close)) > .25*volatility:
            return finish('entry_quote', 'quote_moved_away_from_confirmation_close')
        levels = [float(context['evidence'][tf]['recent_high' if sign == 1 else 'recent_low'])
                  + (ask-bid if sign == -1 else 0) for tf in TIMEFRAMES]
        targets = sorted([v for v in levels if sign*(v-entry) > 0], reverse=sign == -1)
        if risk <= 0 or not targets or sign*(targets[0]-entry)/risk < 2:
            return finish('liquidity_target', 'nearest_HTF_target_below_2R_before_costs')
        signal = {**anchor['signal'], 'strategy': self.name,
                  'stop_loss_points': risk/point, 'take_profit_points': sign*(targets[0]-entry)/point}
        allowed, reason, evidence = budget_check(signal, entry)
        if not allowed:
            return finish('affordability', reason, affordability=evidence)
        identity = anchor['id']
        retire()
        return {**result, 'candidate': signal, 'stage': 'candidate_ready', 'reason': 'aligned_confirmed_affordable',
                'setup_id': self.name+':'+identity, 'entry_reference': entry, 'stop_reference': stop,
                'target_reference': targets[0], 'affordability': evidence,
                'confirmation_at': now.isoformat()}
