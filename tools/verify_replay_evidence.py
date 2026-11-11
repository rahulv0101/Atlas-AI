"""Verify the captured publication archive without connecting to the broker."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.testing.decision_archive import verify

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage",type=Path,default=ROOT/"storage")
    args=parser.parse_args(argv)
    try:result=verify(args.storage/"replay_evidence")
    except (OSError,ValueError,KeyError) as exc:
        result={"state":"verification_failed","error":type(exc).__name__,"valid":False,"replay_ready":False}
    print(json.dumps(result,indent=2))
    return 0 if result.get("valid") is True else 2 if result.get("state")=="writer_busy_retry" else 1


if __name__=="__main__":raise SystemExit(main())
