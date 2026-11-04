from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from atlas_ai.knowledge_paths import knowledge_root


class BrainKnowledge:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else knowledge_root()
        self._cache: dict[str, Any] = {}
        self._signatures: dict[str, tuple[int, int] | None] = {}

    def load(self, name: str) -> dict[str, Any]:
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ValueError("Knowledge names must identify a file within the knowledge directory")
        path = self.root / f"{name}.json"
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            signature = None
        if name in self._cache and self._signatures.get(name) == signature:
            return deepcopy(self._cache[name])
        self._signatures[name] = signature
        if signature is None:
            self._cache[name] = {}
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig")) or {}
            if isinstance(data, dict):
                validated = self._validate(name, data)
                self._cache[name] = validated
                return deepcopy(validated)
            if name == "blockers_catalog" and isinstance(data, list):
                validated = {"entries": data}
                self._cache[name] = validated
                return deepcopy(validated)
        except Exception:
            pass
        self._cache[name] = {}
        return {}

    def _validate(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        if name == "system_overview":
            data.setdefault("identity", "Atlas")
            data.setdefault("purpose", "Trading assistant and system monitor")
            data.setdefault("core_functions", [])
            data.setdefault("modes", ["paper", "live", "hold"])
            data.setdefault("constraints", [])
        elif name == "market_knowledge":
            data.setdefault("concepts", [])
        elif name == "strategy_knowledge":
            data.setdefault("strategies", [])
        elif name == "risk_policy":
            data.setdefault("rules", [])
        elif name == "readiness_rules":
            data.setdefault("criteria", [])
        elif name == "blockers_catalog":
            if "entries" not in data:
                if isinstance(data.get("blockers"), list):
                    data["entries"] = data["blockers"]
                elif isinstance(data.get("common_blockers"), list):
                    data["entries"] = [{"name": str(x), "meaning": str(x)} for x in data["common_blockers"]]
                else:
                    data["entries"] = []
        elif name == "experiment_history":
            data.setdefault("experiments", [])
        elif name == "lessons_learned":
            data.setdefault("lessons", [])
        elif name == "operator_teaching_examples":
            data.setdefault("examples", [])
        elif name == "worker_neurons":
            data.setdefault("coordination_model", "workers_as_evidence_neurons")
            data.setdefault("workers", [])
            data.setdefault("brain_contract", [])
            data.setdefault("safety_boundary", [])
        elif name == "glossary":
            if "terms" not in data and data:
                terms = [{"term": k, "definition": str(v)} for k, v in data.items()]
                data = {"terms": terms}
            else:
                data.setdefault("terms", [])
        return data

    def get_market_concept(self, name: str) -> dict[str, Any] | None:
        target = str(name or "").strip().lower()
        for item in list(self.load("market_knowledge").get("concepts", []) or []):
            if str(item.get("name", "")).lower() == target:
                return dict(item)
        return None

    def get_strategy(self, name: str) -> dict[str, Any] | None:
        target = str(name or "").strip().lower()
        for item in list(self.load("strategy_knowledge").get("strategies", []) or []):
            if str(item.get("name", "")).lower() == target:
                return dict(item)
        return None

    def get_risk_rules(self) -> list[str]:
        return [str(x) for x in list(self.load("risk_policy").get("rules", []) or [])]

    def get_blocker_info(self, name: str) -> dict[str, Any] | None:
        target = str(name or "").strip().lower()
        entries = list(self.load("blockers_catalog").get("entries", []) or [])
        for item in entries:
            nm = str(item.get("name", "")).lower()
            if nm == target or (target and target in nm):
                return dict(item)
        return None

    def get_glossary_term(self, term: str) -> dict[str, Any] | None:
        target = str(term or "").strip().lower()
        for item in list(self.load("glossary").get("terms", []) or []):
            if str(item.get("term", "")).lower() == target:
                return dict(item)
        return None
