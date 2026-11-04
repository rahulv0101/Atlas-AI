"""The source checkout and installed wheel share one knowledge directory."""
from pathlib import Path


def knowledge_root() -> Path:
    return Path(__file__).resolve().parents[1] / "knowledge"
