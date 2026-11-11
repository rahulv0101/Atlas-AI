from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.learned_ranker import (METHOD, compare, examples, feature_frame, feature_names,
                                            features, fit, predict, review_passed, training_rows)
from tools import learned_ranker_supervision as supervision


NOW = datetime(2026, 11, 11, 10, tzinfo=timezone.utc)


def row(at, value=1., confidence=.5, strategy="a", entry=1):
    return {"at": at.isoformat(), "horizon_end": (at+timedelta(minutes=12)).isoformat(),
            "strategy": strategy, "side": "buy", "confidence": confidence,
            "features": [1., float(strategy == "a")], "net_r": value, "net_cash": value*10,
            "entry_bar": entry, "exit_bar": entry+2, "initial_risk_cash": 10.}


def model():
    return {"state": "fitted_research_only", "coefficients": [-1., 2.], "broker_eligible": False, "orders_sent": 0}


def test_learning_is_deterministic_and_never_grants_authority():
    rows = [row(NOW+timedelta(days=i//30, minutes=13*(i%30)), value=1. if i%2 else -1.,
                strategy="a" if i%2 else "b", entry=i*20) for i in range(360)]
    fitted = fit(rows, ["intercept", "is_a"])
    assert fitted == fit(rows, ["intercept", "is_a"])
    assert fitted["state"] == "fitted_research_only" and fitted["dates"] == 12
    assert predict(fitted, [1., 1.]) > predict(fitted, [1., 0.])
    assert fitted["broker_eligible"] is False and fitted["orders_sent"] == 0


def test_insufficient_history_is_not_a_fitted_model():
    assert fit([row(NOW)], ["intercept", "is_a"])["state"] == "insufficient_training_evidence"


def test_overlapping_groups_are_not_counted_as_independent_training():
    rows = [row(NOW), row(NOW, strategy="b"), row(NOW+timedelta(minutes=1)),
            row(NOW+timedelta(minutes=12))]
    assert len(training_rows(rows)) == 3


def test_ranker_selects_expected_return_and_can_abstain_without_changing_inputs():
    rows = [row(NOW, value=-1., strategy="b", confidence=.9),
            row(NOW, value=1., strategy="a", confidence=.2),
            row(NOW+timedelta(minutes=20), value=-1., strategy="b", entry=20)]
    before = repr(rows); result = compare(rows, model())
    assert result["baseline"]["net_r"] == -2 and result["learner"]["net_r"] == 1
    assert result["learner"]["abstentions"] == 1 and repr(rows) == before
    assert result["learner"]["trade_list"][0]["strategy"] == "a"


def test_nominal_paper_portfolios_are_nonoverlapping_and_bounded_per_day():
    rows = [row(NOW+timedelta(minutes=i), entry=i+1) for i in range(20)]
    result = compare(rows, model(), daily_limit=2)
    assert result["learner"]["trades"] == result["baseline"]["trades"] == 2
    trades = result["learner"]["trade_list"]
    assert trades[1]["entry_bar"] > trades[0]["exit_bar"]


def frames():
    times = pd.date_range(NOW, periods=60, freq="min").tz_localize(None)
    return pd.DataFrame({"time": times, "open": np.arange(60)/10+100,
                         "close": np.arange(60)/10+100.05, "high": np.arange(60)/10+100.2,
                         "low": np.arange(60)/10+99.8, "tick_volume": 100., "spread": 2.})


def test_features_cannot_see_future_prices_and_available_time_is_checked():
    frame = frames(); signal = {"strategy": "a", "side": "buy", "confidence": .5}
    item = {"index": 30, "available_at": (NOW+timedelta(minutes=31)).isoformat(), "regime": {"name": "trend"}}
    original = features(feature_frame(frame), item, signal, ["a"], .01)
    frame.loc[31:, ["open", "high", "low", "close", "tick_volume"]] = 99999.
    assert original == features(feature_frame(frame), item, signal, ["a"], .01)
    assert len(original) == len(feature_names(["a"]))
    with pytest.raises(ValueError, match="available_time"):
        features(feature_frame(frame), {**item, "available_at": NOW.isoformat()}, signal, ["a"], .01)


def test_labels_crossing_split_and_gaps_are_purged_and_costs_are_used():
    from atlas_ai.config.settings import Settings
    settings = Settings(0, "", "", backtest_max_hold_bars=12)
    spec = BrokerSpec(.01, .01, 1., 1., .01, 1., .01, 2, roundtrip_fee_per_lot=5.)
    frame = frames(); signal = {"strategy": "a", "side": "buy", "confidence": .5,
                               "stop_loss_points": 100., "take_profit_points": 150.}
    item = {"index": 30, "available_at": (NOW+timedelta(minutes=31)).isoformat(), "signals": [signal]}
    rows, excluded = examples(frame, [item], settings, spec, ExitVariant("current", .05, 3.), ["a"],
                              end=(NOW+timedelta(minutes=35)).isoformat())
    assert rows == [] and excluded["purged_boundary_horizon"] == 1
    costly, _ = examples(frame, [item], settings, spec, ExitVariant("current", .05, 3.), ["a"])
    cheap, _ = examples(frame, [item], settings, spec, ExitVariant("current", .05, 0.), ["a"])
    assert costly[0]["net_cash"] < cheap[0]["net_cash"]
    frame.loc[35, "time"] += pd.Timedelta(seconds=1)
    rows, excluded = examples(frame, [item], settings, spec, ExitVariant("current", .05, 3.), ["a"])
    assert not rows and excluded["gapped_horizon"] == 1


def test_bad_numeric_predictions_are_rejected():
    with pytest.raises(ValueError): predict(model(), [1., float("nan")])


def test_small_winning_sample_cannot_pass_review():
    assert not review_passed(compare([row(NOW)], model()))


def test_supervision_respects_sleep_deadline_and_restart_limit(tmp_path, monkeypatch):
    directory = tmp_path / "run"; directory.mkdir()
    from atlas_ai.atomic_files import atomic_json
    atomic_json(tmp_path / "learned_ranker_active.json", {"run_dir": str(directory)})
    manifest = {"broker_eligible": False, "orders_sent": 0, "auto_promotion": False,
                "deadline": (NOW+timedelta(days=1)).isoformat()}
    monkeypatch.setattr(supervision, "signed", lambda _, name: manifest if name == "manifest" else model())
    start = Mock(side_effect=AssertionError("must not launch"))
    assert supervision.ensure_learning(tmp_path, {}, can_start=False, now=NOW, start=start)["state"] == "waiting_for_backend_and_operator_awake"
    assert supervision.ensure_learning(tmp_path, {}, can_start=True, now=NOW+timedelta(days=2), start=start)["state"] == "deadline_reached"
    state = {"learning_starts": [NOW.timestamp()]*3}
    assert "budget_exhausted" in supervision.ensure_learning(tmp_path, state, can_start=True, now=NOW, start=start)["state"]


def test_frozen_source_validation_happens_before_worker_launch(tmp_path, monkeypatch):
    from atlas_ai.atomic_files import atomic_json
    directory = tmp_path / "run"; directory.mkdir()
    atomic_json(tmp_path / "learned_ranker_active.json", {"run_dir": str(directory)})
    manifest = {"broker_eligible": False, "orders_sent": 0, "auto_promotion": False,
                "deadline": (NOW+timedelta(days=1)).isoformat()}
    monkeypatch.setattr(supervision, "signed", lambda _, name: manifest if name == "manifest" else model())
    monkeypatch.setattr(supervision, "validate", Mock(side_effect=ValueError("source changed")))
    start = Mock(side_effect=AssertionError("must not launch"))
    with pytest.raises(ValueError, match="source changed"):
        supervision.ensure_learning(tmp_path, {}, can_start=True, now=NOW, start=start)
    start.assert_not_called()


def test_cache_ast_allows_reporting_changes_but_detects_generation_changes(tmp_path):
    from tools.learn_candidate_ranker import signal_cache_ast
    first = tmp_path / "first.py"; second = tmp_path / "second.py"
    first.write_text("def cache_candidates(): return 1\ndef replay(): return 'naive'\n")
    second.write_text("def cache_candidates(): return 1\ndef replay(): return 'utc'\n")
    assert signal_cache_ast(first) == signal_cache_ast(second)
    second.write_text("def cache_candidates(): return 2\ndef replay(): return 'utc'\n")
    assert signal_cache_ast(first) != signal_cache_ast(second)
