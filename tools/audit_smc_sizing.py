"""Read-only sizing attribution for a completed, immutable entry comparison."""
import argparse
import json
from pathlib import Path
from statistics import median

from atlas_ai.testing.historical_broker import BrokerSpec
from tools.learn_candidate_ranker import digest, save_signed, signed


def minimum_lot_check(stop_points, spec, balance, risk_fraction, lot_cap):
    risk = abs(spec.cash(-stop_points * spec.point, spec.volume_min))
    return {
        "risk_cash": risk,
        "risk_budget_cash": balance * risk_fraction,
        "risk_budget_exceeded": risk > balance * risk_fraction,
        "lot_cap_exceeded": spec.volume_min > lot_cap,
        "margin_exceeded": spec.margin_per_lot * spec.volume_min > balance,
    }


def audit(directory):
    report = signed(directory, "report")
    receipt = signed(directory, "prediction_receipt")
    if digest(directory / "predictions.jsonl") != receipt["sha256"]:
        raise ValueError("predictions_changed")
    if report["protocol_sha256"] != digest(directory / "protocol.json"):
        raise ValueError("protocol_changed")
    manifests = {name: signed(directory / name, "manifest") for name in report["models"]}
    checks = {name: [] for name in manifests}
    with (directory / "predictions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            for name, value in json.loads(line)["predictions"].items():
                if value.get("stage") != "candidate_ready":
                    continue
                m = manifests[name]
                checks[name].append(minimum_lot_check(
                    value["candidate"]["stop_loss_points"], BrokerSpec(**m["spec"]),
                    m["settings"]["backtest_initial_balance"],
                    m["settings"]["max_risk_per_trade"], m["limits"]["lot_cap"]))
    models = {}
    for name, rows in checks.items():
        risks = [r["risk_cash"] for r in rows]
        models[name] = {
            "complete_signals": len(rows),
            **{key: sum(r[key] for r in rows) for key in
               ["risk_budget_exceeded", "lot_cap_exceeded", "margin_exceeded"]},
            "minimum_risk_cash": min(risks) if risks else None,
            "median_risk_cash": median(risks) if risks else None,
            "maximum_risk_cash": max(risks) if risks else None,
            "risk_budget_cash": rows[0]["risk_budget_cash"] if rows else None,
        }
    result = {
        "schema": "atlas_smc_sizing_audit_v1", "models": models,
        "report_sha256": digest(directory / "report.json"),
        "prediction_sha256": receipt["sha256"], "broker_eligible": False,
        "basis": "Each complete prediction at frozen initial simulation balance; not a portfolio replay or actual account balance. Costs remain those of the frozen reference. Counts can overlap; no policy changes.",
    }
    save_signed(directory, "sizing_audit", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(json.dumps(audit(parser.parse_args().directory), indent=2))
