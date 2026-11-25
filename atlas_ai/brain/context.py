"""Pinned informational evidence and a common read-only reasoning bundle."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

REASONING_EVENT_LIMIT = 160


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def evidence_receipt(status, runtime, events, learning_state, comparison=None):
    chosen = status.get('chosen') or {}
    identity = {k: status.get(k) for k in ('decision_id', 'updated_at', 'symbol', 'timeframe')}
    identity['decision_id'] = status.get('decision_id') or (status.get('execution') or {}).get('decision_id')
    identity['chosen'] = {k: chosen.get(k) for k in ('strategy', 'side', 'confidence')}
    if not identity['updated_at']: identity['unversioned_status'] = fingerprint(status)
    return {'schema': 'atlas_reasoning_evidence_v1', 'decision_key': fingerprint(identity)[:24],
            'backend_decision_id': identity['decision_id'],
            'status_updated_at': status.get('updated_at'),
            'status_fingerprint': fingerprint(status), 'runtime_fingerprint': fingerprint(runtime),
            'events_fingerprint': fingerprint(events), 'learning_fingerprint': fingerprint(learning_state),
            'comparison_fingerprint': fingerprint(comparison or {}),
            'cross_file_atomicity_verified': False,
            'note': 'One captured evidence set per informational request; separate source files are not an atomic broker snapshot.'}


class SnapshotSource:
    """Capture each read once, return independent copies, delegate other APIs."""
    def __init__(self, source):
        self.original = source
        self.failures = {}
        def read(name, default, **kwargs):
            loader = getattr(source, name, None)
            if loader is None: return deepcopy(default)
            try: return deepcopy(loader(**kwargs) or default)
            except Exception as exc:
                self.failures[name] = type(exc).__name__
                return deepcopy(default)
        self.status = read('load_status', {})
        self.runtime = read('load_runtime_flags', {})
        self.events = read('load_events', [], limit=REASONING_EVENT_LIMIT)
        self.learning = read('load_learning_state', {})
        if callable(getattr(source, 'load_comparison_from_status', None)):
            self.comparison = read('load_comparison_from_status', {}, status=deepcopy(self.status))
        else:
            self.comparison = read('load_comparison', {})
        self.confirmed_outcomes = read('load_broker_confirmed_outcomes', [])
        self.receipt = {**evidence_receipt(self.status, self.runtime, self.events, self.learning, self.comparison),
                        'captured_at': datetime.now(timezone.utc).isoformat(), 'read_failures': self.failures}
        self.receipt['confirmed_outcomes_fingerprint'] = fingerprint(self.confirmed_outcomes)

    def load_status(self): return deepcopy(self.status)
    def load_runtime_flags(self): return deepcopy(self.runtime)
    def load_learning_state(self): return deepcopy(self.learning)
    def load_comparison(self): return deepcopy(self.comparison)
    def load_broker_confirmed_outcomes(self): return deepcopy(self.confirmed_outcomes)
    def load_events(self, limit=160): return deepcopy(self.events[-limit:])
    def __getattr__(self, name): return getattr(self.original, name)


def build_reasoning_bundle(*, status, runtime, events, learning_state, knowledge_payload,
                           adaptation_summary=None, execution_ready=None):
    from atlas_ai.brain.adaptation import build_adaptation_summary
    from atlas_ai.brain.cognitive_core import build_cognitive_core
    from atlas_ai.decision_support import build_evidence_separation
    adaptation = adaptation_summary if adaptation_summary is not None else build_adaptation_summary(status, events)
    separation = build_evidence_separation(status, runtime)
    # Dashboard readiness may restrict a reported permission, never grant one.
    if execution_ready is False:
        separation = {**separation, 'execution_permission': 'not_allowed'}
    cognitive = build_cognitive_core(status=status, runtime=runtime, events=events,
        learning_state=learning_state, knowledge_payload=knowledge_payload,
        adaptation_summary=adaptation, evidence_separation=separation)
    return {'adaptation': adaptation, 'evidence_separation': separation, 'cognitive_core': cognitive,
            'evidence_receipt': evidence_receipt(status, runtime, events, learning_state)}
