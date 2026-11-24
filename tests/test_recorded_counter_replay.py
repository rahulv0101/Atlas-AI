from tools.replay_recorded_loss_counter import replay_counter


def test_counter_uses_entry_fill_clock_not_later_execution_log():
    def deal(ticket,position,entry,time,profit=0):
        return dict(ticket=ticket,order=position if entry==0 else ticket,position_id=position,entry=entry,
            type=0 if entry==0 else 1,time_utc=time,volume=.01,profit=profit,commission=0,swap=0,fee=0,
            comment='AAI_Dabcdef_Semax')
    protocol={'start_utc':'2026-11-22T22:00:00Z','end_utc':'2026-11-23T22:00:00Z',
        'settings':{'max_consecutive_losses':3},'limits':{'loss_streak':2},'actual_deals':[
            deal(1,10,0,'2026-11-23T08:01:40Z'),deal(2,10,1,'2026-11-23T08:01:50Z',-17.78),
            deal(3,20,0,'2026-11-23T08:04:10Z'),deal(4,20,1,'2026-11-23T08:04:11Z',-17.27)]}
    records=[{'at':at,'status':{'execution':{'broker_order_id':str(order)},
              'chosen':{'strategy':'ema_crossover','stop_loss_points':100}}}
             for order,at in [(10,'2026-11-23T08:01:43Z'),(20,'2026-11-23T08:04:14Z')]]
    result=replay_counter(protocol,records)
    assert [d['loss_streak_before_entry'] for d in result['decisions']]==[0,1]
    assert all(d['counter_would_admit'] for d in result['decisions'])
    assert result['recorded_net_for_admitted_positions']==-35.05
    assert result['end_loss_streak']==2 and result['counter_would_block_further_entry']
    assert result['actual_first_two_losses_prevented_by_counter']==0


def test_repaired_single_loss_counter_blocks_second_entry_via_cooldown(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from types import SimpleNamespace
    import atlas_ai.trader as trader_module
    from atlas_ai.risk.risk_manager import RiskSnapshot

    class Clock(datetime):
        current = datetime(2026, 11, 23, 8, 1, 51, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(trader_module, 'datetime', Clock)
    trader = trader_module.AtlasTrader.__new__(trader_module.AtlasTrader)
    trader.settings = SimpleNamespace(max_consecutive_losses=3, max_daily_drawdown=.03,
                                     max_trades_per_day=8)
    snapshot = RiskSnapshot(equity=120721.68, balance=120721.68, daily_loss_pct=0,
                            weekly_loss_pct=0, open_positions=0, spread_points=20,
                            consecutive_losses=1)
    state = {'consecutive_losses': 1, 'cooldown_until': ''}
    # Isolate the repaired counter's effect; no archived-memory hindsight.
    out = trader._evaluate_safety_layer(
        snapshot=snapshot, regime={'name': 'trend', 'volatility_pct': .03},
        context_snapshot={'vix_regime': 'normal'}, guard_state=state,
        loss_memory={'recent_outcomes': []})
    assert out['cooldown_active'] and out['cooldown_level'] == 'short'
    assert datetime.fromisoformat(state['cooldown_until']) == Clock.current + timedelta(minutes=12)
    Clock.current = datetime(2026, 11, 23, 8, 4, 10, 833000, tzinfo=timezone.utc)
    assert trader._guard_block_reason(state).startswith('Cooldown active')
