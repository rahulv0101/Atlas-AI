"""Audit existing confidence reductions without changing learning or trading state."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.testing.confidence_penalty_audit import audit


def run(storage, settings):
    paths = [storage/"learning_state.json", storage/"status.json"]
    before = [path.read_bytes() for path in paths]
    result = audit(settings, json.loads(before[0]), json.loads(before[1]))
    after = [path.read_bytes() for path in paths]
    result["source_sha256"] = {path.name: hashlib.sha256(data).hexdigest() for path,data in zip(paths,before)}
    result["source_files_stable_during_audit"] = before == after
    result["audit_code_sha256"] = hashlib.sha256((ROOT/"atlas_ai/testing/confidence_penalty_audit.py").read_bytes()).hexdigest()
    result["policy_code_sha256"] = hashlib.sha256((ROOT/"atlas_ai/trader.py").read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(); settings = load_settings()
    result = run(Path(settings.storage_dir), settings)
    output = args.output or Path(settings.storage_dir)/"audits/confidence_penalty_audit.json"
    atomic_json(output, result)
    print(json.dumps({"report": str(output), "historical_source": result["historical_count_source"],
        "lesson_sources": result["retained_lesson_memory"]["effective_sources"],
        "candidates_replayed": len(result["candidates"]),
        "published_score_matches": sum(row["replay_matches_published"] for row in result["candidates"]),
        "sources_stable": result["source_files_stable_during_audit"], "policy_changes": []}, indent=2))


if __name__ == "__main__": main()
