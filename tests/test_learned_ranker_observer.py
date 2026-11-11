from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import Settings
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.learned_ranker import METHOD, feature_names
from tools import learn_candidate_ranker as tool
from tools.guarded_research_audit import safe_settings


NOW = datetime(2026, 11, 11, 10, tzinfo=timezone.utc)


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    directory = tmp_path / "experiment"; directory.mkdir()
    frozen = directory / "frozen_source"; frozen.mkdir()
    (frozen / "helper.py").write_text("# frozen fixture\n")
    source = tmp_path / "source"; source.mkdir()
    times = pd.date_range(NOW-timedelta(hours=1), periods=61, freq="min").tz_localize(None)
    frame = pd.DataFrame({"time": times, "open": np.arange(61)/10+100,
                          "close": np.arange(61)/10+100.05, "high": np.arange(61)/10+100.2,
                          "low": np.arange(61)/10+99.8, "tick_volume": 100., "spread": 2.})
    frame.to_csv(source / "observed_candles.csv", index=False)
    (directory / "candles.csv").write_text("frozen training data")
    atomic_json(directory / "candidates.json", [])
    settings = Settings(0, "", "", backtest_max_hold_bars=12)
    manifest = {"schema": "atlas_learned_candidate_ranker_v1", "method": METHOD,
                "frozen_at": (NOW-timedelta(minutes=28)).isoformat(),
                "future_holdout_start": (NOW-timedelta(minutes=28)).isoformat(),
                "warmup_start": (NOW-timedelta(hours=2)).isoformat(),
                "deadline": (NOW+timedelta(days=10)).isoformat(),
                "settings": safe_settings(settings), "forward_source_run": str(source),
                "strategies": ["a"], "daily_paper_limit": 6,
                "spec": asdict(BrokerSpec(.01, .01, 1., 1., .01, 1., .01, 2)),
                "variant": asdict(ExitVariant("current", .05, 3.)),
                "source_hashes": {"helper.py": tool.digest(frozen / "helper.py")},
                "environment": tool.environment_versions(),
                "broker_eligible": False, "orders_sent": 0, "auto_promotion": False}
    model = {"state": "fitted_research_only", "feature_names": feature_names(["a"]),
             "coefficients": [1.] + [0.] * (len(feature_names(["a"]))-1),
             "broker_eligible": False, "orders_sent": 0}
    tool.save_signed(directory, "manifest", manifest); tool.save_signed(directory, "model", model)
    tool.save_signed(directory, "historical_report", {"historical_review_passed": False})
    tool.save_signed(directory, "inputs", {name: tool.digest(directory/name) for name in ("candles.csv", "candidates.json")})
    signal = {"strategy": "a", "side": "buy", "confidence": .5,
              "stop_loss_points": 100., "take_profit_points": 150.}
    candidate = {"index": 33, "available_at": (NOW-timedelta(minutes=26)).isoformat(), "signals": [signal]}
    generate = Mock(return_value=([candidate], {}, ["a"]))
    monkeypatch.setattr(tool, "cache_candidates", generate)
    monkeypatch.setattr(tool, "fit", Mock(side_effect=AssertionError("forward retraining forbidden")))
    return directory, source, frame, generate


def test_forward_uses_only_new_closed_bars_and_never_retrains_or_dispatches(experiment):
    directory, _, frame, generate = experiment
    result = tool.once(directory, NOW)
    assert result["state"] == "collecting_frozen_model_paper"
    assert result["learner_paper_trades"] == result["baseline_paper_trades"] == 1
    assert result["historical_review_passed"] is False
    assert not result["first_stage_passed"] and not result["broker_eligible"] and result["orders_sent"] == 0
    # The last source candle has not closed at NOW; it must not reach the generator.
    supplied = generate.call_args.args[0]
    assert len(supplied) == len(frame)-1
    generate.return_value = ([], {}, ["a"])
    again = tool.once(directory, NOW)
    assert again["learner_paper_trades"] == 1


def test_revised_forward_candles_block_without_reset(experiment):
    directory, source, frame, generate = experiment
    tool.once(directory, NOW)
    before = (directory / "forward_integrity.json").read_bytes()
    frame.loc[0, "close"] += .01
    frame.to_csv(source / "observed_candles.csv", index=False)
    with pytest.raises(ValueError, match="observed_candles_revised"):
        tool.once(directory, NOW)
    assert (directory / "forward_integrity.json").read_bytes() == before


@pytest.mark.parametrize("target", ["model.json", "candles.csv", "frozen_source/helper.py"])
def test_model_data_and_source_tampering_stop_forward_observation(experiment, target):
    directory, _, _, generate = experiment
    path = directory / target; path.write_bytes(path.read_bytes()+b"changed")
    with pytest.raises(ValueError): tool.once(directory, NOW)
    generate.assert_not_called()
