from __future__ import annotations

import time
from collections import Counter
from collections import deque
from dataclasses import dataclass, field, asdict
from copy import deepcopy
import json
import re
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrainTurn:
    query: str
    intent: str
    domain: str
    plan: str
    answer: str
    main_conclusion: str
    supporting_reasons: list[str]
    confidence: float
    entities: list[str]
    timestamp: float
    evidence_receipt: dict[str, Any] = field(default_factory=dict)


class BrainMemory:
    def __init__(self, max_turns: int = 20, *, file_path=None, max_age_seconds=14400) -> None:
        self._turns: deque[BrainTurn] = deque(maxlen=max_turns)
        self.recent_questions: deque[str] = deque(maxlen=max_turns)
        self.recent_conclusions: deque[str] = deque(maxlen=max_turns)
        self.repeated_blockers: Counter[str] = Counter()
        # Legacy compatibility for modules/tests that inspect this attribute directly.
        self.recent_turns = self._turns
        self._file_path = Path(file_path) if file_path is not None else None
        self._max_age_seconds = max_age_seconds
        self._file_stamp = None
        self.persistence_error = None
        self._refresh()

    def _read_rows(self):
        if self._file_path is None or not self._file_path.exists(): return []
        document = json.loads(self._file_path.read_text(encoding='utf-8'))
        if document.get('schema') != 'atlas_operator_conversation_v1':
            raise ValueError('unknown_conversation_schema')
        now = time.time()
        return [row for row in document.get('turns', [])
                if -5 <= now-float(row.get('timestamp', 0)) <= self._max_age_seconds]

    def _refresh(self):
        if self._file_path is None: return
        try:
            stamp = (self._file_path.stat().st_mtime_ns, self._file_path.stat().st_size) if self._file_path.exists() else None
            expired = bool(self._turns) and time.time()-self._turns[0].timestamp > self._max_age_seconds
            if stamp == self._file_stamp and not expired: return
            rows = self._read_rows()[-self._turns.maxlen:]
            turns = [BrainTurn(**row) for row in rows]
            self._turns.clear(); self._turns.extend(turns)
            self.recent_questions.clear(); self.recent_questions.extend(t.query for t in turns)
            self.recent_conclusions.clear(); self.recent_conclusions.extend(t.main_conclusion for t in turns)
            self._file_stamp = stamp
            self.persistence_error = None
        except (OSError, ValueError, TypeError):
            self._turns.clear()
            self.recent_questions.clear(); self.recent_conclusions.clear()
            self.persistence_error = 'conversation_memory_unavailable'

    def _persist_latest(self):
        if self._file_path is None or not self._turns: return
        from atlas_ai.atomic_files import atomic_json
        from atlas_ai.execution.automation_state_store import AutomationStateStore
        row = asdict(self._turns[-1])
        def redact(text):
            text = re.sub(r'AIza[\w-]{20,}|sk-[\w-]{20,}', '[redacted]', str(text))
            return re.sub(r'(?i)((?:api[_ -]?key|password|secret|token)\s*[:=]\s*)\S+', r'\1[redacted]', text)
        # Compact local continuity, never runtime flags or trading controls.
        for key, limit in (('query',500),('answer',1200),('main_conclusion',512)):
            row[key] = redact(row[key])[:limit]
        row['supporting_reasons'] = [redact(x)[:250] for x in row['supporting_reasons'][:3]]
        try:
            with AutomationStateStore(self._file_path)._locked():
                try: rows = self._read_rows()
                except (OSError, ValueError, TypeError): rows = []
                atomic_json(self._file_path, {'schema':'atlas_operator_conversation_v1',
                    'authority':'continuity_only_no_trading_or_command_control',
                    'turns':(rows+[row])[-self._turns.maxlen:]})
            self._file_stamp = None
            self._refresh()
        except (OSError, ValueError, TypeError):
            self.persistence_error = 'conversation_memory_not_persisted'

    def add(
        self,
        *,
        query: str,
        intent: str,
        domain: str,
        plan: str,
        answer: str,
        confidence: float = 0.0,
        evidence_receipt: dict[str, Any] | None = None,
    ) -> None:
        clean_answer = str(answer or "").strip()
        lines = [ln.strip() for ln in clean_answer.splitlines() if ln.strip()]
        main = lines[0] if lines else ""
        reasons = [ln.lstrip("- ").strip() for ln in lines[1:3] if ln.startswith("-")]
        entities = [x for x in ("comparison", "readiness", "blocker", "volatility", "market", "strategy") if x in clean_answer.lower()]
        self._turns.append(
            BrainTurn(
                query=str(query or ""),
                intent=str(intent or ""),
                domain=str(domain or ""),
                plan=str(plan or ""),
                answer=clean_answer,
                main_conclusion=main,
                supporting_reasons=reasons,
                confidence=float(confidence or 0.0),
                entities=entities,
                timestamp=time.time(),
                evidence_receipt=deepcopy(evidence_receipt or {}),
            )
        )
        self.remember_question(query)
        self.remember_conclusion(clean_answer)
        self._persist_latest()

    # Legacy compatibility methods used by operator_assistant/older tests.
    def remember_question(self, query: str) -> None:
        text = " ".join(str(query or "").split())
        if text:
            self.recent_questions.append(text)

    def remember_conclusion(self, conclusion: str) -> None:
        text = " ".join(str(conclusion or "").split())
        if text:
            self.recent_conclusions.append(text)

    def remember_turn(self, turn: Any) -> None:
        self._turns.append(turn)

    def recent_relevant_turns(self, limit: int = 5) -> list[Any]:
        self._refresh()
        relevant = [turn for turn in self._turns if bool(getattr(turn, "follow_up_relevance", True))]
        if not relevant:
            relevant = list(self._turns)
        return relevant[-max(1, int(limit)) :]

    def recent(self, limit: int = 5) -> list[BrainTurn]:
        self._refresh()
        return list(self._turns)[-max(1, int(limit)) :]

    def latest(self) -> BrainTurn | None:
        self._refresh()
        return self._turns[-1] if self._turns else None

    @staticmethod
    def is_follow_up(query: str) -> bool:
        q = str(query or "").strip().lower()
        if not q:
            return False
        compact = q.replace("?", "").strip()
        if compact in {
            "why",
            "why not",
            "what changed",
            "compared to what",
            "is that still true",
            "what do you mean",
            "and the next step",
            "what about that",
            "about that",
            "what about this",
            "about this",
            "explain that",
            "explain that simpler",
            "why does that matter",
            "based on that what next",
            "based on that what should happen next",
        }:
            return True
        return any(
            marker in q
            for marker in (
                "why?",
                "what changed?",
                "compared to what",
                "is that still true",
                "what do you mean",
                "how confident are you",
                "and the next step",
                "what about that",
                "what about this",
                "explain that",
                "why does that matter",
                "based on that",
                "why not",
            )
        )

    def build_follow_up_context(self, query: str) -> str:
        latest = self.latest()
        if latest is None:
            return str(query or "")
        q = str(query or "").strip()
        return (
            f"{q} (follow-up context: prior_query='{latest.query}'; "
            f"prior_intent={latest.intent}; prior_domain={latest.domain}; "
            f"prior_plan={latest.plan}; prior_conclusion='{latest.main_conclusion}')"
        )
