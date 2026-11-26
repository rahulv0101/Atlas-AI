"""Separate H1-direction/M5-entry hypotheses. No broker registration or authority."""
from copy import deepcopy
from atlas_ai.data.top_down import entry_gate
from atlas_ai.strategies.smc_composite import evaluate as sequence
from atlas_ai.strategies.smc_retest import first_retest
from atlas_ai.strategies import smc_entry_models as original

MODELS = ('smc_h1_event_retest_v6', 'smc_h1_sweep_reclaim_v6')
CONTEXT_RULES = {
    'direction_timeframes': ['H1'], 'entry_timeframe': 'M5',
    'context_only_timeframes': ['D1', 'H4', 'M15'],
    'entry_location': 'Explicit closed-M5 event/zone retest or sweep/reclaim; no rolling HTF half-range veto.',
    'other_timeframe_ranges': 'Retained as liquidity targets; valid range data remains required for risk geometry.',
    'execution_authority': 'none', 'automatic_promotion': False,
}


def h1_setup(context, quote):
    side = (context.get('details') or {}).get('H1')
    gate = entry_gate(context, side)
    return {**gate, 'side': side, 'context_policy': 'h1_direction_m5_event_v6',
            'stage': 'setup_context_ready' if gate['passed'] else 'higher_timeframe_confluence',
            'direction_timeframes': ['H1'], 'setup_timeframes': ['M5']}


def context_observation(frame, context, quote, now):
    # Reuse all existing input/quote/range checks. Only the explicitly declared
    # direction/setup policy differs; never invent D1/H4 agreement or ranges.
    return sequence(frame, context, quote, now, setup_policy=h1_setup, retest_policy=first_retest)


def evaluate_model(name, frame, context, quote, now):
    if name not in MODELS:
        raise ValueError('unknown_h1_research_model')
    fn = original.event_retest if name == MODELS[0] else original.sweep_reclaim
    result = deepcopy(fn(frame, context, quote, now, context_provider=context_observation))
    old_name = result.get('strategy', '')
    result.update(strategy=name, schema='atlas_smc_h1_research_v6', broker_eligible=False,
                  orders_sent=0, auto_promotion=False,
                  rules={**deepcopy(original.RULES), 'context': deepcopy(CONTEXT_RULES)})
    if result.get('candidate'):
        result['candidate']['strategy'] = name
    if result.get('setup_id') and old_name:
        result['setup_id'] = result['setup_id'].replace(old_name + ':', name + ':', 1)
    return result


def event_retest(frame, context, quote, now):
    return evaluate_model(MODELS[0], frame, context, quote, now)


def sweep_reclaim(frame, context, quote, now):
    return evaluate_model(MODELS[1], frame, context, quote, now)
