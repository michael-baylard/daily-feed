"""Pure checkers over text that was already fetched. No HTTP."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from daily_feed.hashing import changed
from daily_feed.models import Update, WatchItem

_BRACKETS = re.compile(r"\[[^\]]*\]")


def steam_news_update(
    item: WatchItem, payload: dict, seen_ids: set[str]
) -> Update | None:
    """Newest Steam news item whose gid is not in ``seen_ids``.

    ``payload`` matches ISteamNews: appnews.newsitems[]. Returns None when
    the item has no steam_app_id or every gid was already seen.
    """
    if item.steam_app_id is None:
        return None
    seen = {str(gid) for gid in seen_ids}
    newest: dict | None = None
    newest_stamp = -1
    for news in _newsitems(payload):
        gid = str(news.get("gid", "")).strip()
        if not gid or gid in seen:
            continue
        stamp = _unix(news.get("date"))
        if newest is None or stamp >= newest_stamp:
            newest = news
            newest_stamp = stamp
    if newest is None:
        return None
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=str(newest.get("title") or ""),
        published_at=datetime.fromtimestamp(newest_stamp, tz=timezone.utc),
        url=str(newest.get("url") or ""),
        lines=_steam_lines(str(newest.get("contents") or "")),
        source="steam",
    )


def tvmaze_episode_update(
    item: WatchItem, episode: dict, today: date
) -> Update | None:
    """An episode that airs on ``today``. Other airdates return None."""
    if item.tvmaze_id is None:
        return None
    if not isinstance(episode, dict):
        return None
    airdate = str(episode.get("airdate") or "")
    if airdate != today.isoformat():
        return None
    title = f"Season {episode.get('season')}, Episode {episode.get('number')}"
    name = episode.get("name")
    lines = (str(name),) if isinstance(name, str) and name.strip() else ()
    published = datetime.fromisoformat(f"{airdate}T00:00:00+00:00")
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=title,
        published_at=published,
        url=str(episode.get("url") or ""),
        lines=lines,
        source="tvmaze",
    )


def page_update(
    item: WatchItem,
    page_text: str,
    previous_hash: str | None,
    url: str,
    published_at: datetime,
) -> Update | None:
    """A movie or publisher page whose fingerprint changed.

    Lines stay empty. The model would write them later. A matching hash
    returns None, so the model is not asked.
    """
    if not changed(previous_hash, page_text):
        return None
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=item.name,
        published_at=published_at,
        url=url,
        lines=(),
        source="page",
    )


def twitch_update(
    item: WatchItem, live: dict | None, previous_title: str | None
) -> Update | None:
    """One line for this streamer only. Offline, a different login, or the same title returns None."""
    if live is None or item.twitch_login is None:
        return None
    if not isinstance(live, dict):
        return None
    user_login = str(live.get("user_login") or "")
    if user_login.casefold() != item.twitch_login.casefold():
        return None
    title = str(live.get("title") or "")
    if title == previous_title:
        return None
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=title,
        published_at=_parse_utc(str(live.get("started_at") or "")),
        url=f"https://www.twitch.tv/{item.twitch_login}",
        lines=(title,),
        source="twitch",
    )


def _newsitems(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    appnews = payload.get("appnews")
    if not isinstance(appnews, dict):
        return []
    raw = appnews.get("newsitems") or []
    if not isinstance(raw, list):
        return []
    return [news for news in raw if isinstance(news, dict)]


def _unix(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _steam_lines(contents: str) -> tuple[str, ...]:
    cleaned = _BRACKETS.sub("", contents)
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) == 3:
            break
    return tuple(lines)


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
