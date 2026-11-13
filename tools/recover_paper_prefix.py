"""Restore only a byte-exact, previously signed CSV prefix after interrupted publication."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from atlas_ai.atomic_files import atomic_json, replace_with_retry
from tools.observe_cost_research import observer_lock


def digest(data): return hashlib.sha256(data).hexdigest()


def recover(directory, *, apply=False):
    directory = Path(directory)
    with observer_lock(directory / "observer.lock"):
        manifest = (directory / "manifest.json").read_bytes()
        if digest(manifest) != (directory / "manifest.sha256").read_text().strip():
            raise ValueError("unverified_paper_manifest")
        expected = json.loads((directory / "artifacts.json").read_text())
        if set(expected) != {"observed_candles.csv", "signals.json"}:
            raise ValueError("unsupported_paper_artifacts")
        if digest((directory / "signals.json").read_bytes()) != expected["signals.json"]:
            raise ValueError("signals_changed_requires_independent_recovery")
        path = directory / "observed_candles.csv"; data = path.read_bytes()
        if digest(data) == expected[path.name]: return {"state": "already_verified", "orders_sent": 0}
        hashed = hashlib.sha256(); length = 0; recovered = None
        for line in data.splitlines(keepends=True):
            hashed.update(line); length += len(line)
            if hashed.hexdigest() == expected[path.name]:
                recovered = data[:length]; break
        if recovered is None:
            raise ValueError("no_exact_previously_verified_prefix")
        result = {"state": "verified_prefix_available", "before_sha256": digest(data),
                  "restored_sha256": digest(recovered), "uncommitted_suffix_bytes": len(data)-len(recovered),
                  "orders_sent": 0, "broker_eligible": False}
        if not apply: return result
        folder = directory / "recovery" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        folder.mkdir(parents=True, exist_ok=False)
        for name in ("observed_candles.csv", "signals.json", "outcomes.json", "status.json", "artifacts.json"):
            if (directory / name).exists(): (folder / name).write_bytes((directory / name).read_bytes())
        temporary = folder / "verified_prefix.csv"
        temporary.write_bytes(recovered)
        replace_with_retry(temporary, path)
        if digest(path.read_bytes()) != expected[path.name]: raise ValueError("prefix_restore_verification_failed")
        result.update(state="previously_verified_prefix_restored", backup=str(folder))
        atomic_json(folder / "recovery.json", result)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True); parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(recover(args.run_dir, apply=args.apply), indent=2))
