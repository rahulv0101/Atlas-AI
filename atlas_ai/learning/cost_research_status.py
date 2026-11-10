"""Read-only UI adapter for isolated cost research; no trading authority."""
import json
from pathlib import Path


def load_cost_research_status(base):
    path=Path(base)/"cost_research/latest.json"
    try:
        if path.stat().st_size>16384:raise ValueError("oversized_research_summary")
        raw=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw,dict) or raw.get("broker_eligible") is not False or raw.get("orders_sent")!=0:
            raise ValueError("invalid_research_boundary")
        return {key:raw.get(key) for key in ("state","checked_at","run_id","forward_start","observer_pid","latest_bar_at","data_fresh",
            "comparisons","paper_outcomes","training_qualified","orders_sent","broker_eligible","error")}
    except FileNotFoundError:return {"state":"not_started","orders_sent":0,"broker_eligible":False}
    except (OSError,ValueError,TypeError):return {"state":"summary_unavailable","orders_sent":0,"broker_eligible":False}
