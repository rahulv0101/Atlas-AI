"""Account-scoped durable index of guarded demo execution references."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from atlas_ai.execution.automation_state_store import AutomationStateStore
from atlas_ai.learning.evidence_provenance import is_manual_broker_test
from atlas_ai.strategy_aliases import canonical_strategy_name


class GuardedDecisionIndex:
    def __init__(self, settings):
        fingerprint = hashlib.sha256(f"{settings.hfm_login}|{settings.hfm_server}".encode()).hexdigest()[:24]
        self.path = Path(settings.storage_dir) / "decision_index" / (fingerprint + ".jsonl")
        self.lock = AutomationStateStore(self.path)

    def _events(self):
        if not self.path.exists():
            return []
        events=[]
        for line in self.path.read_text(encoding="utf-8").splitlines():
            row=json.loads(line)
            if row.get("type")!="decision_sample" or not isinstance(row.get("meta"),dict):
                raise ValueError("invalid_decision_index")
            events.append(row)
        return events

    def events(self):
        with self.lock._locked():
            return self._events()

    def record(self, meta):
        if (meta.get("request_origin")!="trader_guarded" or meta.get("execution_mode")!="demo"
                or meta.get("execution_success") is not True or is_manual_broker_test(meta)
                or meta.get("forced_demo_entry") or meta.get("forced_learning_probe")):
            return False
        strategy=canonical_strategy_name(meta.get("strategy",""))
        decision=str(meta.get("decision_id", ""))
        refs={}
        for key in ("broker_order_id","order_id","deal_id"):
            raw=str(meta.get(key, "") or "")
            if raw.isdigit() and int(raw)>0:
                refs[key]=raw
        if not decision or strategy=="unknown" or not refs:
            return False
        safe={"decision_id":decision,"strategy":strategy,"request_origin":"trader_guarded",
              "execution_mode":"demo","execution_success":True,**refs}
        with self.lock._locked():
            if any(e["meta"]==safe for e in self._events()):
                return False
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open("a",encoding="utf-8") as stream:
                stream.write(json.dumps({"time":datetime.now(timezone.utc).isoformat(),"type":"decision_sample","meta":safe})+"\n")
                stream.flush();os.fsync(stream.fileno())
        return True
