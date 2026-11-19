"""Plain-text friend requests, merged onto a watchlist."""

from __future__ import annotations

from daily_feed.models import Kind, WatchItem, Watchlist
from daily_feed.slug import to_slug

_KINDS = {
    "game": Kind.game,
    "show": Kind.show,
    "movie": Kind.movie,
    "publisher": Kind.publisher,
    "person": Kind.person,
    "streamer": Kind.person,
}


def parse_request(text: str) -> list[WatchItem]:
    if not text or not text.strip():
        return []
    items: list[WatchItem] = []
    for record in _records(text.lstrip("\ufeff")):
        item = _parse_record(record)
        if item is not None:
            items.append(item)
    return items


def merge_inbox(
    watchlist: Watchlist, new_items: list[WatchItem]
) -> tuple[Watchlist, list[WatchItem]]:
    """Keep existing rows. Append a row only when its kind and slug are new."""
    seen = {(item.kind, item.slug) for item in watchlist.items}
    added: list[WatchItem] = []
    for item in new_items:
        key = (item.kind, item.slug)
        if key in seen:
            continue
        seen.add(key)
        added.append(item)
    return Watchlist(items=[*watchlist.items, *added]), added


def _records(text: str) -> list[str]:
    chunks: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.strip() == "---":
            chunks.append([])
            continue
        chunks[-1].append(line)
    return ["\n".join(lines) for lines in chunks]


def _parse_record(record: str) -> WatchItem | None:
    fields: dict[str, list[str]] = {}
    for line in record.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        fields.setdefault(key.strip().lower(), []).append(value.strip())
    if not fields:
        return None
    kind_raw = _first(fields, "type")
    name = _first(fields, "name")
    if not kind_raw:
        raise ValueError("missing type")
    if not name:
        raise ValueError("missing name")
    kind = _KINDS.get(kind_raw.lower())
    if kind is None:
        raise ValueError(f"unknown type: {kind_raw}")
    urls = tuple(url for url in fields.get("url", []) if url)
    return WatchItem(
        kind=kind,
        name=name,
        slug=to_slug(name),
        urls=urls,
        steam_app_id=_optional_int(fields, "steam_app_id"),
        tvmaze_id=_optional_int(fields, "tvmaze_id"),
        twitch_login=_twitch_login(_first(fields, "twitch")),
    )


def _first(fields: dict[str, list[str]], key: str) -> str:
    for value in fields.get(key, []):
        if value:
            return value
    return ""


def _optional_int(fields: dict[str, list[str]], key: str) -> int | None:
    raw = _first(fields, key)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an int") from exc


def _twitch_login(value: str) -> str | None:
    if not value:
        return None
    login = to_slug(value.lstrip("@")).replace("_", "")
    return login or None
