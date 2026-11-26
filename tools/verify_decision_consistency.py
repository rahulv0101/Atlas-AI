"""Read-only cross-check of one backend scan, dashboard APIs and its journal event."""
import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from atlas_ai.decision_record import validate_record


def verify(storage, url):
    storage = Path(storage)
    last = None
    for _ in range(3):
        status = json.loads((storage / 'status.json').read_text(encoding='utf-8'))
        decision_id = status.get('decision_id')
        observations = {}
        errors = []
        if not validate_record(status)['verified']:
            errors.append({'backend': validate_record(status)})
        for endpoint in ('status/compact', 'status', 'status/full'):
            with urllib.request.urlopen(url.rstrip('/') + '/api/' + endpoint, timeout=30) as response:
                payload = json.load(response)
            result = validate_record(payload)
            observations[endpoint] = {'validation': result, 'decision_ref': payload.get('decision_ref'),
                                      'current_execution': payload.get('current_execution')}
            if not result['verified'] or payload.get('decision_ref') != status.get('decision_ref'):
                errors.append({'endpoint': endpoint, 'validation': result})
        # A scan may advance while separate HTTP requests are in flight. Retry;
        # never declare differing generations to be a single verified snapshot.
        after = json.loads((storage / 'status.json').read_text(encoding='utf-8'))
        if after.get('decision_ref') != status.get('decision_ref'):
            last = {'verified': False, 'reason': 'scan_advanced_during_verification'}
            continue
        with (storage / 'events.jsonl').open(encoding='utf-8') as fh:
            events = [json.loads(line) for line in deque(fh, maxlen=100) if line.strip()]
        matches = [row for row in events if (row.get('meta') or {}).get('decision_id') == decision_id
                   and (row.get('meta') or {}).get('current_execution')]
        if not matches or any(row['meta'].get('decision_ref') != status.get('decision_ref') for row in matches):
            errors.append({'journal': 'missing_or_mismatched_scan_record'})
        return {'verified': not errors, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                'decision_id': decision_id, 'decision_ref': status.get('decision_ref'),
                'decision_snapshot': status.get('decision_snapshot'), 'current_execution': status.get('current_execution'),
                'api_observations': observations, 'matching_journal_events': len(matches), 'errors': errors,
                'scope': 'One current scan across backend, API projections and journal. No forced order; natural filled lifecycle not demonstrated by this check.'}
    return last


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, default=ROOT/'storage')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.storage, args.url)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['verified'] else 1)


if __name__ == '__main__':
    main()
