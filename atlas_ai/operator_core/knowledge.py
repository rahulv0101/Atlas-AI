from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from atlas_ai.knowledge_paths import knowledge_root


class KnowledgeBase:
    def __init__(self, root: Path | None = None) -> None:
        base = root or knowledge_root()
        self.root = Path(base)

    def load(self, name: str) -> dict[str, Any]:
        path = self.root / f"{name}.json"
        if not path.exists():
            return {}
        try:
            return dict(json.loads(path.read_text(encoding="utf-8")) or {})
        except Exception:
            return {}

