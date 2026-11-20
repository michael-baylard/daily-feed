"""Pure checkers over text that was already fetched. No HTTP."""

from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone

from daily_feed.hashing import changed
from daily_feed.models import Kind, Update, WatchItem
from daily_feed.schedule import days_until

_BRACKETS = re.compile(r"\[[^\]]*\]")
_TAGS = re.compile(r"<[^>]+>")
_IMG = re.compile(r"""<img[^>]+src=["'](https://[^"']+)["']""", re.IGNORECASE)
_WEEK_LIMIT = 8


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
    return _steam_update(item, newest, newest_stamp, str(payload.get("header_image") or ""))


def steam_news_updates(
    item: WatchItem, payload: dict, seen_ids: set[str], since: datetime, limit: int = _WEEK_LIMIT
) -> list[Update]:
    """Unseen official posts at or after ``since``, oldest first."""
    if item.steam_app_id is None:
        return []
    seen = {str(gid) for gid in seen_ids}
    header = str(payload.get("header_image") or "")
    items = _newsitems(payload)
    found: list[Update] = []
    in_window = False
    for news in items:
        gid = str(news.get("gid", "")).strip()
        if not gid:
            continue
        stamp = _unix(news.get("date"))
        published = datetime.fromtimestamp(stamp, tz=timezone.utc)
        if published < since:
            continue
        in_window = True
        if gid in seen:
            continue
        found.append(_steam_update(item, news, stamp, header))
    found.sort(key=lambda update: update.published_at)
    if found:
        return found[-limit:]
    if in_window or not items:
        return []
    latest = max(items, key=lambda news: _unix(news.get("date")))
    gid = str(latest.get("gid", "")).strip()
    if not gid or gid in seen:
        return []
    return [_steam_update(item, latest, _unix(latest.get("date")), header)]


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


def countdown_update(item: WatchItem, today: date) -> Update | None:
    """Daily line for a movie trailer or release, from 7 days out through that day.

    The sooner date is the bold title. A second date in the same window is
    one extra line, and only when it says something different.
    """
    if item.kind is not Kind.movie:
        return None
    events: list[tuple[int, date, str]] = []
    if item.trailer_on is not None:
        trailer_days = days_until(today, item.trailer_on)
        if trailer_days is not None:
            events.append((trailer_days, item.trailer_on, _when("Trailer", trailer_days)))
    if item.releases_on is not None:
        release_days = days_until(today, item.releases_on)
        if release_days is not None:
            events.append((release_days, item.releases_on, _when("In theaters", release_days)))
    if not events:
        return None
    events.sort(key=lambda row: (row[0], row[2]))
    title = events[0][2]
    lines = tuple(phrase for _, _, phrase in events[1:] if phrase.casefold() != title.casefold())
    when = events[0][1]
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=title,
        published_at=datetime(when.year, when.month, when.day, tzinfo=timezone.utc),
        url=item.urls[0] if item.urls else "",
        lines=lines,
        source="countdown",
    )


def twitch_update(
    item: WatchItem, live: dict | None, previous_title: str | None
) -> Update | None:
    """One line for this streamer only, while that login is live and the title is new.

    Offline, a different login, or the same title returns None.
    """
    if live is None or item.twitch_login is None:
        return None
    if not isinstance(live, dict):
        return None
    user_login = str(live.get("user_login") or "")
    if user_login.casefold() != item.twitch_login.casefold():
        return None
    title = str(live.get("title") or "").strip()
    if not title or title == str(previous_title or "").strip():
        return None
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=title,
        published_at=_started_at(str(live.get("started_at") or "")),
        url=f"https://www.twitch.tv/{item.twitch_login}",
        lines=(title,),
        source="twitch",
        image=str(live.get("image") or ""),
    )


def _when(label: str, days: int) -> str:
    if days == 0:
        return f"{label} today"
    if days == 1:
        return f"{label} tomorrow"
    return f"{label} in {days} days"


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


def article_update(
    item: WatchItem, articles: list, seen_ids: set[str], source: str
) -> Update | None:
    """Newest article whose URL is not in ``seen_ids``.

    ``articles`` are dicts with ``title``, ``url``, ``text``, and ``published_at``.
    The body stays on the update. A later step condenses it.
    """
    seen = {str(value) for value in seen_ids}
    newest: dict | None = None
    newest_at: datetime | None = None
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = str(article.get("url") or "").strip()
        title = str(article.get("title") or "").strip()
        published = article.get("published_at")
        if not url or not title or url in seen or not isinstance(published, datetime):
            continue
        if newest is None or newest_at is None or published >= newest_at:
            newest = article
            newest_at = published
    if newest is None or newest_at is None:
        return None
    return _article_update(item, newest, source)


def article_updates(
    item: WatchItem, articles: list, seen_ids: set[str], source: str, since: datetime, limit: int = _WEEK_LIMIT
) -> list[Update]:
    """Unseen articles at or after ``since``, oldest first."""
    seen = {str(value) for value in seen_ids}
    found: list[Update] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = str(article.get("url") or "").strip()
        title = str(article.get("title") or "").strip()
        published = article.get("published_at")
        if not url or not title or url in seen or not isinstance(published, datetime):
            continue
        if published < since:
            continue
        found.append(_article_update(item, article, source))
    found.sort(key=lambda update: update.published_at)
    return found[-limit:]


def _article_update(item: WatchItem, article: dict, source: str) -> Update:
    published = article.get("published_at")
    text = str(article.get("text") or "").strip() or str(article.get("title") or "")
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=str(article.get("title") or ""),
        published_at=published if isinstance(published, datetime) else datetime(1970, 1, 1, tzinfo=timezone.utc),
        url=str(article.get("url") or ""),
        lines=(text,),
        source=source,
        image=_https(str(article.get("image") or "")),
        focus=str(article.get("focus") or ""),
    )


def _steam_update(item: WatchItem, news: dict, stamp: int, header: str) -> Update:
    contents = str(news.get("contents") or "")
    return Update(
        slug=item.slug,
        kind=item.kind,
        name=item.name,
        title=str(news.get("title") or ""),
        published_at=datetime.fromtimestamp(stamp, tz=timezone.utc),
        url=str(news.get("url") or ""),
        lines=_steam_lines(contents),
        source="steam",
        image=_steam_image(contents, header),
    )


def _steam_image(contents: str, header: str) -> str:
    match = _IMG.search(contents)
    if match:
        return match.group(1)
    return _https(header)


def _https(url: str) -> str:
    text = url.strip()
    return text if text.startswith("https://") else ""


def _steam_lines(contents: str) -> tuple[str, ...]:
    plain = html.unescape(_TAGS.sub("", contents))
    cleaned = _BRACKETS.sub("", plain)
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) == 3:
            break
    return tuple(lines)


def _started_at(value: str) -> datetime:
    text = value.strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        return _parse_utc(text)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
