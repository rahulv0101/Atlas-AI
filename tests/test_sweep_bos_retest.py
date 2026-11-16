from copy import deepcopy
import pandas as pd
import pytest
from test_aligned_smc import context
from atlas_ai.testing.sweep_bos_retest import NAME, evaluate, research_features


def sequence(side='buy'):
    now = pd.Timestamp('2026-11-13T12:00Z')
    f = pd.DataFrame({'time': pd.date_range(end=now-pd.Timedelta(minutes=5), periods=80, freq='5min'),
                      'open': 100.2, 'close': 100.3, 'high': 100.5, 'low': 100.})
    f.loc[60, 'high'] = 101.
    values = {74: [100.2, 100.4, 99.2, 100.3], 75: [100.3, 102.1, 100.2, 102.],
        76: [101.8, 102., 101.4, 101.7], 77: [101.7, 101.8, 101.3, 101.5],
        78: [101.5, 101.6, 101.2, 101.3], 79: [101.04, 101.9, 100.98, 101.85]}
    for i, row in values.items():
        f.loc[i, ['open', 'high', 'low', 'close']] = row
    if side == 'sell':
        old = f.copy()
        f['open'], f['close'], f['high'], f['low'] = 220-old.open, 220-old.close, 220-old.low, 220-old.high
    close = float(f.close.iloc[-1])
    return f, context(side, now), {'bid': close-.02, 'ask': close+.02, 'point': .01, 'at': now.isoformat()}, now


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_complete_sequence_uses_original_extreme_and_exact_2R(side):
    f,c,q,now = sequence(side)
    before = f.copy()
    r = evaluate(f,c,q,now)
    assert r['candidate'], r
    assert r['candidate']['side'] == side and r['candidate']['strategy'] == NAME
    assert r['candidate']['take_profit_points'] == 2*r['candidate']['stop_loss_points']
    assert r['stop_reference'] < 99.2 if side == 'buy' else r['stop_reference'] > 120.8
    assert r['broker_eligible'] is False and r['orders_sent'] == 0
    pd.testing.assert_frame_equal(f,before)
    future = f.tail(1).assign(time=now, high=9999., low=1., close=9999.)
    assert evaluate(pd.concat([f,future],ignore_index=True),c,q,now) == r


@pytest.mark.parametrize('failure', ['sweep', 'BOS', 'retest', 'protection', 'prior_visit', 'context', 'target', 'stale', 'gap'])
def test_incomplete_or_used_sequences_never_emit(failure):
    f,c,q,now = sequence()
    if failure == 'sweep': f.loc[74, 'low'] = 100.1
    elif failure == 'BOS': f.loc[75, ['high','close']] = [100.8,100.7]
    elif failure == 'retest': f.loc[79, ['open','low']] = [101.4,101.3]
    elif failure == 'protection': f.loc[77,'low'] = 99.
    elif failure == 'prior_visit': f.loc[77,['open','low','close']] = [101.05,100.98,101.5]
    elif failure == 'context': c['details']['H4'] = 'sell'
    elif failure == 'target': c['evidence']['M15']['recent_high'] = 102.5
    elif failure == 'stale': q['at'] = (now-pd.Timedelta(minutes=1)).isoformat()
    elif failure == 'gap': f.loc[70,'time'] += pd.Timedelta(seconds=1)
    assert evaluate(f,c,q,now)['candidate'] is None


def test_research_adapter_reconstructs_and_restores_without_broker_inventory_changes():
    from atlas_ai.trader import AtlasTrader
    from atlas_ai.models import TradeSignal
    from atlas_ai.config.settings import Settings
    from atlas_ai.strategies.inventory import base_inventory
    f,c,q,now = sequence()
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = Settings(1,'test','Demo',timeframe='M5')
    r = evaluate(f,c,q,now)
    chosen = TradeSignal(**r['candidate'])
    original = AtlasTrader._derive_runtime_chart_features
    lookup = {now.isoformat(): {'context': c,'quote': q}}
    with research_features(lookup):
        fields = trader._derive_runtime_chart_features(df=f,chosen=chosen,regime={})
        assert fields['location_state'] == 'fresh_retest' and fields['momentum_state'] == 'turning'
        bad = deepcopy(c)
        bad['details']['H1'] = 'sell'
        lookup[now.isoformat()]['context'] = bad
        assert 'sequence_evidence' not in trader._derive_runtime_chart_features(df=f,chosen=chosen,regime={})
    assert AtlasTrader._derive_runtime_chart_features is original
    assert NAME not in {s.name for s in base_inventory('M5',top_down=True)}
