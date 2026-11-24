import pandas as pd
from atlas_ai.data.top_down import POLICY
from atlas_ai.testing.h1_m5_retest_timing import verify


def sample(side='buy'):
    f = pd.DataFrame({'time': pd.date_range('2026-01-02T08:00Z', periods=60, freq='5min'),
                      'open': 100., 'high': 100.3, 'low': 99.7, 'close': 100.})
    f.loc[58, ['open', 'high', 'low', 'close']] = [100., 101., 99.9, 100.9]
    f.loc[59, ['open', 'high', 'low', 'close']] = [100.35, 101.04, 100.25, 100.98]
    if side == 'sell':
        old = f.copy()
        f['open'], f['close'] = 200-old.open, 200-old.close
        f['high'], f['low'] = 200-old.low, 200-old.high
    now = f.time.iloc[-1]+pd.Timedelta(minutes=5)
    ctx = {'policy': POLICY, 'entry_timeframe': 'M5', 'closed_candles_only': True,
           'evaluated_at': now.isoformat(), 'details': {'H1': side},
           'evidence': {'H1': {'status': 'available'}}}
    return f, ctx, now


def test_closed_directional_first_retest_for_both_sides():
    for side in ('buy', 'sell'):
        f, ctx, now = sample(side)
        out = verify(f, ctx, side, now)
        assert out['passed'] and out['fields']['momentum_state'] == 'turning'
        assert out['fields']['location_state'] == 'fresh_retest'
        assert out['broker_eligible'] is False


def test_future_forming_candles_do_not_change_verification():
    f, ctx, now = sample()
    expected = verify(f, ctx, 'buy', now)
    f.loc[60] = [now, 500., 900., 1., 800.]
    assert verify(f, ctx, 'buy', now) == expected


def test_mid_range_weak_or_opposite_H1_cannot_be_promoted():
    f, ctx, now = sample()
    assert not verify(f, ctx, 'sell', now)['passed']
    ctx['evidence']['H1']['status'] = 'unavailable'
    assert not verify(f, ctx, 'buy', now)['passed']
    f, ctx, now = sample()
    f.loc[59, ['open', 'high', 'low', 'close']] = [100.5, 100.9, 100.2, 100.51]
    assert not verify(f, ctx, 'buy', now)['passed']


def test_consumed_retest_and_stale_context_rejected():
    f, ctx, now = sample()
    f.loc[57, ['open', 'high', 'low', 'close']] = f.loc[58, ['open', 'high', 'low', 'close']].values
    f.loc[58, ['open', 'high', 'low', 'close']] = [100.8, 100.9, 100.29, 100.8]
    assert verify(f, ctx, 'buy', now)['reason'] == 'prior_retest_consumed'
    ctx['evaluated_at'] = (now-pd.Timedelta(hours=1)).isoformat()
    assert not verify(f, ctx, 'buy', now)['passed']


def test_research_adapter_preserves_baseline_and_restores_method(monkeypatch):
    from types import SimpleNamespace
    from atlas_ai.trader import AtlasTrader
    from atlas_ai.testing.h1_m5_retest_timing import overlay
    original = lambda self, **kw: {'location_state': 'mid_range', 'momentum_state': 'weak'}
    monkeypatch.setattr(AtlasTrader, '_derive_runtime_chart_features', original)
    trader = AtlasTrader.__new__(AtlasTrader)
    trader.settings = SimpleNamespace(timeframe='M5')
    f, ctx, now = sample()
    chosen = SimpleNamespace(strategy='ema_crossover', side='buy')
    baseline = original(trader)
    with overlay({}, {}):
        assert trader._derive_runtime_chart_features(df=f, chosen=chosen, regime={}) == baseline
    assert AtlasTrader._derive_runtime_chart_features is original
    with overlay({now.isoformat(): ctx}, {}):
        changed = trader._derive_runtime_chart_features(df=f, chosen=chosen, regime={})
        assert changed['momentum_state'] == 'turning' and changed['location_state'] == 'fresh_retest'
        assert changed['range_momentum_state'] == 'weak'
    assert AtlasTrader._derive_runtime_chart_features is original


def test_verified_retest_reaches_shared_timing_gate_without_lowering_thresholds(tmp_path):
    from atlas_ai.config.settings import Settings
    from atlas_ai.memory.knowledge_store import KnowledgeStore
    from atlas_ai.models import TradeSignal
    from atlas_ai.risk.risk_manager import RiskSnapshot
    from atlas_ai.testing.historical_decision import historical_decision
    from atlas_ai.testing.policy_replay import policy_trader
    from atlas_ai.testing.h1_m5_retest_timing import overlay
    f, ctx, now = sample()
    f['tick_volume'] = 100.
    f['real_volume'] = 100.
    f['spread'] = 20.
    cfg = Settings(0, '', '', timeframe='M5', top_down_confluence_enabled=True)
    trader = policy_trader(cfg, KnowledgeStore(str(tmp_path)))
    signal = TradeSignal('ema_crossover', 'buy', .95, 100., 150.)
    snapshot = RiskSnapshot(120000., 120000., 0., 0, 20., 0., 0)
    def decision():
        return historical_decision(trader, signal, [signal], f, {'name': 'trend', 'volatility_pct': .01},
                                   'buy', snapshot, now.to_pydatetime(), higher_context=ctx)
    baseline = decision()
    with overlay({now.isoformat(): ctx}, {}):
        modified = decision()
    assert not baseline['timing_passed']
    assert modified['timing_passed']
    assert modified['threshold'] == baseline['threshold']
