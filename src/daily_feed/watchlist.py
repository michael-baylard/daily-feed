"""Load and save the YAML watchlist."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml

from daily_feed.models import Kind, WatchItem, Watchlist
from daily_feed.slug import to_slug


def load_watchlist(path: str | Path) -> Watchlist:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValueError("watchlist must be a mapping")
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("items must be a list")
    return Watchlist(items=[_load_item(raw) for raw in raw_items])


def save_watchlist(path: str | Path, watchlist: Watchlist) -> None:
    payload = {"items": [_dump_item(item) for item in watchlist.items]}
    text = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    Path(path).write_text(text, encoding="utf-8")


def _load_item(raw: object) -> WatchItem:
    if not isinstance(raw, dict):
        raise ValueError("watch item must be a mapping")
    name = raw.get("name")
    if name is None or not str(name).strip():
        raise ValueError("missing name")
    name = str(name).strip()
    kind_raw = raw.get("kind")
    if kind_raw is None or not str(kind_raw).strip():
        raise ValueError("missing kind")
    slug_raw = raw.get("slug")
    slug = str(slug_raw).strip() if slug_raw not in (None, "") else ""
    return WatchItem(
        kind=Kind(str(kind_raw).strip()),
        name=name,
        slug=slug or to_slug(name),
        urls=_urls(raw.get("urls")),
        steam_app_id=_optional_int(raw.get("steam_app_id")),
        tvmaze_id=_optional_int(raw.get("tvmaze_id")),
        twitch_login=_optional_text(raw.get("twitch_login")),
        trailer_on=_optional_date(raw.get("trailer_on")),
        releases_on=_optional_date(raw.get("releases_on")),
    )


def _urls(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("urls must be a list")
    return tuple(url for url in (str(item).strip() for item in raw) if url)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("expected int")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError("expected int") from exc
    raise ValueError("expected int")


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError("expected YYYY-MM-DD") from exc
    raise ValueError("expected YYYY-MM-DD")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dump_item(item: WatchItem) -> dict[str, object]:
    return {
        "kind": item.kind.value,
        "name": item.name,
        "slug": item.slug,
        "urls": list(item.urls),
        "steam_app_id": item.steam_app_id,
        "tvmaze_id": item.tvmaze_id,
        "twitch_login": item.twitch_login,
        "trailer_on": item.trailer_on.isoformat() if item.trailer_on else None,
        "releases_on": item.releases_on.isoformat() if item.releases_on else None,
    }
