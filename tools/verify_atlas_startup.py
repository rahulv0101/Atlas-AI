"""Inspect local post-reboot startup evidence; never restart Windows or Atlas."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from atlas_ai.startup_verification import verify

if __name__ == "__main__":
    print(json.dumps(verify(ROOT / "storage"), indent=2))
