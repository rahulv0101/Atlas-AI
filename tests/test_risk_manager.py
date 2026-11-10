import pytest
from atlas_ai.config.settings import Settings
from atlas_ai.risk.risk_manager import RiskManager, RiskSnapshot


def _settings(**overrides):
    base = {
        "hfm_login": 1,
        "hfm_password": "x",
        "hfm_server": "demo",
        "max_risk_per_trade": 0.01,
        "max_daily_drawdown": 0.03,
        "max_open_trades": 2,
        "base_lot": 0.01,
    }
    base.update(overrides)
    return Settings(**base)


def test_can_trade_blocks_on_daily_drawdown():
    risk = RiskManager(_settings(max_daily_drawdown=0.03))
    snap = RiskSnapshot(equity=1000, balance=1000, daily_loss_pct=0.03, open_positions=0)
    assert risk.can_trade(snap) is False


def test_can_trade_blocks_on_open_positions_limit():
    risk = RiskManager(_settings(max_open_trades=2))
    snap = RiskSnapshot(equity=1000, balance=1000, daily_loss_pct=0.01, open_positions=2)
    assert risk.can_trade(snap) is False


def test_evaluate_blocks_on_spread_limit():
    risk = RiskManager(_settings())
    snap = RiskSnapshot(equity=1000, balance=1000, daily_loss_pct=0.0, open_positions=0, spread_points=999)
    allowed, reason = risk.evaluate(snap)
    assert allowed is False
    assert "Spread too high" in reason


def test_lot_size_respects_base_lot_and_formula():
    risk = RiskManager(_settings(max_risk_per_trade=0.01, base_lot=0.01))
    lot = risk.lot_size(equity=10000, stop_loss_points=200, tick_value=1)
    assert lot == 0.5

    fallback = risk.lot_size(equity=10000, stop_loss_points=0, tick_value=1)
    assert fallback == 0.0


@pytest.mark.parametrize("equity,stop,tick", [(0, 100, 1), (-1, 100, 1), (100, 0, 1), (100, 100, 0), (100, 100, -1)])
def test_invalid_sizing_inputs_do_not_create_base_lot(equity, stop, tick):
    assert RiskManager(_settings()).lot_size(equity, stop, tick) == 0


def test_small_account_does_not_get_upsized_to_base_lot():
    assert RiskManager(_settings()).lot_size(10, 200, 1) == 0


def test_lot_size_floors_and_accounts_for_tick_size():
    risk = RiskManager(_settings())
    assert risk.lot_size(119, 100, 1) == .01
    assert risk.lot_size(10000, 200, 1, point_size=.01, tick_size=.1) == 5


def test_sub_cent_lot_steps_are_supported_if_broker_allows_them():
    risk = RiskManager(_settings(base_lot=.001))
    assert risk.lot_size(10, 100, 1, volume_step=.001, minimum_volume=.001) == .001


def test_learning_fixed_lot_must_fit_existing_risk_budget():
    risk = RiskManager(_settings(learning_mode=True))
    assert risk.lot_size(10, 200, 1) == 0
    assert risk.lot_size(10000, 200, 1) == .01


@pytest.mark.parametrize("step,minimum,equity", [(.001, .001, 10), (.000001, .000001, .01)])
def test_broker_minimum_overrides_nominal_base_lot_without_raising_risk(step, minimum, equity):
    risk = RiskManager(_settings(base_lot=.01))
    volume = risk.lot_size(equity, 100, 1, volume_step=step, minimum_volume=minimum)
    assert volume == minimum
    assert volume * 100 <= equity * risk.settings.max_risk_per_trade + 1e-12


def test_legacy_sizing_without_broker_metadata_retains_configured_minimum():
    assert RiskManager(_settings(base_lot=.01)).lot_size(10, 100, 1) == 0
