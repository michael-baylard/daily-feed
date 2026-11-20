"""JSON memory for the last Chicago day, page hashes, seen ids, and stream titles."""

from __future__ import annotations

import json
from pathlib import Path

_KEYS = ("last_run_day", "hashes", "seen_ids", "seen_titles", "twitch_titles", "twitch_posts")


def empty_state() -> dict:
    return {
        "last_run_day": None,
        "hashes": {},
        "seen_ids": [],
        "seen_titles": [],
        "twitch_titles": {},
        "twitch_posts": {},
    }


def load_state(path) -> dict:
    """Return the saved state, or the empty shape when the file is missing."""
    file = Path(path)
    if not file.is_file():
        return empty_state()
    raw = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("state must be a JSON object")
    state = empty_state()
    last = raw.get("last_run_day")
    state["last_run_day"] = None if last in (None, "") else str(last)
    hashes = raw.get("hashes") or {}
    titles = raw.get("twitch_titles") or {}
    posts = raw.get("twitch_posts") or {}
    seen = raw.get("seen_ids") or []
    remembered = raw.get("seen_titles") or []
    if (
        not isinstance(hashes, dict)
        or not isinstance(titles, dict)
        or not isinstance(posts, dict)
        or not isinstance(seen, list)
        or not isinstance(remembered, list)
    ):
        raise ValueError("state lists and maps are the wrong shape")
    state["hashes"] = {str(key): str(value) for key, value in hashes.items()}
    state["twitch_titles"] = {str(key): str(value) for key, value in titles.items()}
    state["twitch_posts"] = {str(key): str(value) for key, value in posts.items()}
    state["seen_ids"] = [str(gid) for gid in seen]
    state["seen_titles"] = [str(title) for title in remembered if str(title).strip()]
    return state


def save_state(path, state) -> None:
    """Write the state object. Creates parent directories."""
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = empty_state()
    last = state.get("last_run_day")
    if last is None or last == "":
        payload["last_run_day"] = None
    elif hasattr(last, "isoformat") and not isinstance(last, str):
        payload["last_run_day"] = last.isoformat()
    else:
        payload["last_run_day"] = str(last)
    payload["hashes"] = dict(state.get("hashes") or {})
    payload["seen_ids"] = [str(gid) for gid in (state.get("seen_ids") or [])]
    payload["seen_titles"] = [str(title) for title in (state.get("seen_titles") or []) if str(title).strip()]
    payload["twitch_titles"] = dict(state.get("twitch_titles") or {})
    payload["twitch_posts"] = dict(state.get("twitch_posts") or {})
    text = json.dumps({key: payload[key] for key in _KEYS}, indent=2) + "\n"
    file.write_text(text, encoding="utf-8")
