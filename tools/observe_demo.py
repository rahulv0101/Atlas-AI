"""Bounded, read-only collection of demo decision evidence; no command routing."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import time


def snapshot(storage):
    status = json.loads((Path(storage) / "status.json").read_text(encoding="utf-8-sig"))
    execution = dict(status.get("execution", {}) or {})
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "decision_at": status.get("updated_at"), "action": status.get("action"),
        "message": status.get("message"), "chosen": status.get("chosen"),
        "signal_generation": status.get("signal_generation"),
        "strategy_evidence": status.get("strategy_evidence"),
        "timing_discipline": status.get("timing_discipline"),
        "market_data_clock": status.get("market_data_clock"),
        "freshness_runtime": status.get("freshness_runtime"),
        "execution": {key: execution.get(key) for key in ("success", "decision_id", "broker_order_id", "broker_status", "filled_quantity", "comment")},
        "open_positions_reported": dict(status.get("risk", {}) or {}).get("open_positions"),
        "policy": "Read-only observation; reported status is not independent broker confirmation.",
    }


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-dir", type=Path, default=root / "storage")
    parser.add_argument("--minutes", type=int, default=120)
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.minutes <= 1440 or not 10 <= args.interval_seconds <= 300:
        parser.error("Use 1–1440 minutes and a 10–300 second interval")
    folder = args.storage_dir / "demo_observations"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"observation_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.jsonl"
    deadline = time.monotonic() + args.minutes * 60
    last_decision = None
    with output.open("x", encoding="utf-8", buffering=1) as stream:
        while time.monotonic() < deadline:
            try:
                row = snapshot(args.storage_dir)
                if row["decision_at"] != last_decision:
                    stream.write(json.dumps(row) + "\n")
                    last_decision = row["decision_at"]
            except (OSError, ValueError) as exc:
                stream.write(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), "error": type(exc).__name__}) + "\n")
            time.sleep(min(args.interval_seconds, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    main()
