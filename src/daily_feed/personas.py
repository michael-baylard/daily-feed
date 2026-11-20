"""Who is talking. The card uses that person's voice."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

_DIR = Path(__file__).resolve().parents[2] / "personas"
_SPORTS = {"league", "athlete", "match"}


@cache
def load_persona(persona_id: str) -> dict:
    """The yaml for this voice. An unknown id falls back to the shelf."""
    path = _DIR / f"{persona_id}.yaml"
    if not path.is_file():
        path = _DIR / "shelf.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def persona_for(source: str, kind: str = "", focus: str = "") -> str:
    """Which file speaks for this card."""
    if source == "conduct":
        return "conduct"
    if source == "nfl" or focus == "bears" or kind in _SPORTS:
        return "bears"
    return "shelf"


def voice(persona_id: str) -> str:
    """The instructions and the example, ready for the prompt."""
    data = load_persona(persona_id)
    text = str(data.get("voice") or "").strip()
    example = str(data.get("example") or "").strip()
    if example:
        return f"{text}\nExample: {example}"
    return text
