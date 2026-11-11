"""Initialize or inspect Atlas's read-only seven-day activity review."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from atlas_ai.config.settings import load_settings
from atlas_ai.testing.activity_review import initialize, review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "report"))
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    settings = load_settings(); now = datetime.now(timezone.utc)
    if args.mode == "init":
        if args.journal is None: parser.error("--journal required for init")
        result = initialize(settings.storage_dir, settings, args.journal, now)
    else:
        result = review(settings.storage_dir, settings, now)
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
