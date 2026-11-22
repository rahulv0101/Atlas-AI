"""One frozen research hypothesis; never registered as a broker strategy."""
from copy import deepcopy
from atlas_ai.data.top_down import closed_bars
from atlas_ai.strategies.smc_entry_models import sweep_reclaim

MODEL = 'smc_sweep_followthrough_v6_research'
RULE = 'two_latest_closed_M5_directional_bodies_and_progressing_closes'


def followthrough(frame, side, now):
    bars = closed_bars(frame, 'M5', now).tail(2)
    if len(bars) != 2 or side not in ('buy', 'sell'):
        return False
    sign = 1 if side == 'buy' else -1
    return bool(((bars.close - bars.open) * sign > 0).all()
                and sign * (bars.close.iloc[-1] - bars.close.iloc[-2]) > 0)


def evaluate(frame, context, quote, now):
    result = deepcopy(sweep_reclaim(frame, context, quote, now))
    result.update(strategy=MODEL, research_followthrough_rule=RULE,
                  broker_eligible=False, orders_sent=0, auto_promotion=False)
    if result.get('candidate'):
        if not followthrough(frame, result['side'], now):
            result.update(candidate=None, stage='research_followthrough',
                          reason='two_closed_M5_directional_candles_not_confirmed')
        else:
            result['candidate']['strategy'] = MODEL
            result['setup_id'] = MODEL + ':' + result['setup_id']
    return result
