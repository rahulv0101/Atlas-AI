from atlas_ai.learning.online_allocator import OnlineAllocator
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.models import TradeSignal
from collections import Counter


def test_allocator_prefers_confidence_initially():
    allocator = OnlineAllocator()
    s1 = TradeSignal("a", "buy", 0.9, 100, 150)
    s2 = TradeSignal("b", "buy", 0.2, 100, 150)
    chosen = allocator.choose([s1, s2])
    assert chosen.strategy == "a"


def test_allocator_update_changes_stats():
    allocator = OnlineAllocator()
    allocator.update("ema_crossover", 12.0)
    allocator.update("ema_crossover", -5.0)

    stats = allocator.stats()["ema_crossover"]
    assert stats.wins == 2
    assert stats.losses == 2
    assert stats.pnl == 7.0


def test_allocator_persists_state_with_store(tmp_path):
    store = KnowledgeStore(str(tmp_path))
    allocator = OnlineAllocator(store=store)
    allocator.update("breakout", 10.0)

    reloaded = OnlineAllocator(store=store)
    stats = reloaded.stats()["breakout"]
    assert stats.wins == 2
    assert stats.losses == 1
    assert stats.pnl == 10.0


def test_allocator_choose_respects_score_overrides():
    allocator = OnlineAllocator()
    s1 = TradeSignal("a", "buy", 0.9, 100, 150)
    s2 = TradeSignal("b", "buy", 0.2, 100, 150)
    chosen = allocator.choose([s1, s2], score_overrides={"a": 0.1, "b": 0.9})
    assert chosen.strategy == "b"


def test_allocator_preserves_evolved_rule_signature_for_overrides():
    allocator = OnlineAllocator()
    s1 = TradeSignal("evolved_rule(fast=22,slow=52,rsi_buy=34.0,rsi_sell=57.0)", "flat", 0.0, 100, 150)
    s2 = TradeSignal("momentum_continuation", "buy", 0.3, 100, 150)
    chosen = allocator.choose(
        [s1, s2],
        score_overrides={
            "evolved_rule(fast=22,slow=52,rsi_buy=34.0,rsi_sell=57.0)": 0.0,
            "momentum_continuation": 0.9,
        },
    )
    assert chosen.strategy == "momentum_continuation"


def test_enabled_strategies_have_no_name_based_EMA_bonus():
    names=('ema_crossover','pullback_trend','momentum_continuation','gold_micro_impulse',
           'gold_breakout_retest','gold_liquidity_sweep')
    allocator=OnlineAllocator()
    scores=[allocator.score_signal(TradeSignal(name,'buy',.8,100,150)) for name in names]
    assert len(set(scores))==1
    # Learning evidence still matters after removal of the fixed preference.
    allocator.update('ema_crossover',-10.)
    assert allocator.score_signal(TradeSignal('ema_crossover','buy',.8,100,150)) < scores[0]


def test_equal_score_choices_are_order_independent_and_not_always_EMA():
    signals=[TradeSignal(name,'buy',.8,100,150) for name in
             ('ema_crossover','pullback_trend','momentum_continuation')]
    a,b=OnlineAllocator(),OnlineAllocator()
    left=[a.choose(signals).strategy for _ in range(120)]
    right=[b.choose(list(reversed(signals))).strategy for _ in range(120)]
    assert left==right
    assert set(left)=={s.strategy for s in signals}
    assert all(20 < count < 70 for count in Counter(left).values())
    assert a.last_selection['reason']=='equal_score_seeded_draw'


def test_exploration_includes_every_candidate_tied_at_boundary():
    class Exploring:
        def random(self): return 0.
        def choice(self, pool):
            assert len(pool)==5
            return pool[-1]
    allocator=OnlineAllocator();allocator.set_exploration(.04);allocator._rng=Exploring()
    signals=[TradeSignal(name,'buy',.8,100,150) for name in ('e','d','c','b','a')]
    assert allocator.choose(signals).strategy=='e'
    assert allocator.last_selection['reason']=='configured_exploration'


def test_EMA_must_win_on_score_instead_of_fixed_bonus():
    allocator=OnlineAllocator()
    ema=TradeSignal('ema_crossover','buy',.8,100,150)
    pullback=TradeSignal('pullback_trend','buy',.84,100,150)
    assert allocator.choose([ema,pullback]).strategy=='pullback_trend'
    ema.confidence=.9
    assert allocator.choose([ema,pullback]).strategy=='ema_crossover'
