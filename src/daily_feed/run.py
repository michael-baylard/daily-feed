"""Build the day's posts from a locked watchlist.

Payloads are already in hand. A long body is condensed to two lines.
``page_prompts`` is the request for a page whose hash changed.
Nothing here opens a socket.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

from daily_feed.discord_md import render
from daily_feed.gate import allow_post
from daily_feed.hashing import content_hash
from daily_feed.models import Kind, Update, WatchItem
from daily_feed.order import sort_updates
from daily_feed.prompt import build_prompt
from daily_feed.safety import assert_no_pings
from daily_feed.select import relevant
from daily_feed.schedule import due, local_day
from daily_feed.sources import (
    article_update,
    article_updates,
    countdown_update,
    page_update,
    steam_news_update,
    steam_news_updates,
    tvmaze_episode_update,
    twitch_update,
)
from daily_feed.summarize import conduct_lines, describe, mask_slur


def collect(
    items: list[WatchItem],
    fetched: dict,
    state: dict,
    now: datetime,
    since: datetime | None = None,
    force: bool = False,
) -> list[Update]:
    """New updates for items on the list, oldest release first.

    Keys in ``fetched`` whose slug is not on the list are ignored.
    ``since`` keeps every unseen item in that window, up to eight a row.
    ``force`` opens the daily gate when a repost has to ignore the stamped day.
    """
    hashes = state.get("hashes") or {}
    seen_ids = {str(gid) for gid in (state.get("seen_ids") or [])}
    twitch_titles = state.get("twitch_titles") or {}
    twitch_posts = state.get("twitch_posts") or {}
    day_due = force or due(now, _state_day(state.get("last_run_day")))
    updates: list[Update] = []
    for item in items:
        data = fetched.get(item.slug)
        if not isinstance(data, dict):
            data = {}
        updates.extend(
            _ones(item, data, hashes, seen_ids, twitch_titles, twitch_posts, now, day_due, since)
        )
    return sort_updates(updates)


def page_prompts(
    items: list[WatchItem], updates: list[Update], fetched: dict
) -> list[str]:
    """Prompts for page-source updates only.

    Steam, TVMaze, and Twitch never appear here. A page whose hash did not
    change never becomes an update, so it is not prompted either.
    """
    by_slug = {item.slug: item for item in items}
    prompts: list[str] = []
    for update in updates:
        if update.source != "page":
            continue
        item = by_slug.get(update.slug)
        if item is None:
            continue
        data = fetched.get(update.slug) or {}
        page_text = data.get("page_text") if isinstance(data, dict) else ""
        prompts.append(build_prompt(item, page_text if isinstance(page_text, str) else ""))
    return prompts


def worth_sending(update: Update) -> bool:
    """A post needs a real line. A bare page name is held back.

    A countdown title is the line. Twitch uses the stream title the same way.
    """
    if update.source in {"twitch", "countdown"}:
        return bool(update.title.strip())
    return any(line.strip() for line in update.lines)


def render_day(updates: list[Update]) -> list[str]:
    """Discord markdown in the given order. Each message is ping-checked."""
    messages: list[str] = []
    for update in updates:
        text = render(update)
        assert_no_pings(text)
        messages.append(text)
    return messages


def remember(
    state: dict,
    updates: list[Update],
    fetched: dict,
    now: datetime,
    stamp_day: bool = True,
) -> dict:
    """State after a completed run. Does not write the file or post.

    The Chicago date is consumed even when nothing was new. Steam gids at
    or before the posted item are remembered so older patches are not
    walked backwards on the next day.
    """
    stored = {
        "last_run_day": local_day(now).isoformat() if stamp_day else state.get("last_run_day"),
        "hashes": dict(state.get("hashes") or {}),
        "seen_ids": [str(gid) for gid in (state.get("seen_ids") or [])],
        "twitch_titles": dict(state.get("twitch_titles") or {}),
        "twitch_posts": dict(state.get("twitch_posts") or {}),
    }
    seen = set(stored["seen_ids"])
    for update in updates:
        data = fetched.get(update.slug) if isinstance(fetched.get(update.slug), dict) else {}
        if update.source == "page":
            page_text = data.get("page_text") if isinstance(data, dict) else ""
            stored["hashes"][update.slug] = content_hash(page_text if isinstance(page_text, str) else "")
        elif update.source == "twitch":
            stored["twitch_titles"][update.slug] = update.lines[0] if update.lines else update.title
            stored["twitch_posts"][update.slug] = _as_utc(now).isoformat()
        elif update.source in {"newswire", "nfl", "conduct"} and update.url:
            seen.add(update.url)
        elif update.source == "steam" and isinstance(data, dict):
            posted = int(update.published_at.timestamp())
            payload = data.get("steam") if isinstance(data.get("steam"), dict) else {}
            appnews = payload.get("appnews") if isinstance(payload, dict) else {}
            newsitems = appnews.get("newsitems") if isinstance(appnews, dict) else []
            for news in newsitems or []:
                if not isinstance(news, dict):
                    continue
                gid = str(news.get("gid", "")).strip()
                if not gid:
                    continue
                try:
                    stamp = int(news.get("date") or 0)
                except (TypeError, ValueError):
                    stamp = 0
                if stamp <= posted or news.get("url") == update.url:
                    seen.add(gid)
    stored["seen_ids"] = sorted(seen)
    return stored


_PAGE_KINDS = {
    Kind.movie,
    Kind.publisher,
    Kind.tool,
    Kind.athlete,
    Kind.league,
    Kind.match,
    Kind.person,
}


def _ones(
    item: WatchItem,
    data: dict,
    hashes: dict,
    seen_ids: set[str],
    twitch_titles: dict,
    twitch_posts: dict,
    now: datetime,
    day_due: bool,
    since: datetime | None,
) -> list[Update]:
    if item.twitch_login:
        update = _twitch(item, data, twitch_titles, twitch_posts, now)
        return [update] if update is not None else []

    if item.kind is Kind.movie:
        countdown = countdown_update(item, local_day(now))
        if countdown is not None:
            posted = _daily(countdown, day_due)
            return [posted] if posted is not None else []

    articles = data.get("articles")
    if isinstance(articles, list) and articles:
        source = str(data.get("article_source") or "page")
        if since is None:
            chosen = [article_update(item, articles, seen_ids, source)]
        else:
            chosen = article_updates(item, articles, seen_ids, source, since, limit=80)
        chosen = [update for update in chosen if update is not None and relevant(update)]
        if since is not None and source == "nfl":
            bears = [update for update in chosen if update.focus == "bears"]
            rest = [update for update in chosen if update.focus != "bears"]
            chosen = [*bears[-5:], *rest[-3:]]
        elif since is not None:
            chosen = chosen[-8:]
        return [posted for posted in (_daily(_short(update), day_due) for update in chosen) if posted is not None]

    if item.kind in _PAGE_KINDS:
        update = _page(item, data, hashes, now, day_due)
        return [update] if update is not None else []

    if item.steam_app_id is not None and isinstance(data.get("steam"), dict):
        if since is None:
            chosen = [steam_news_update(item, data["steam"], seen_ids)]
        else:
            chosen = steam_news_updates(item, data["steam"], seen_ids, since)
        return [posted for posted in (_daily(_short(update), day_due) for update in chosen) if posted is not None]

    episode = data.get("episode")
    if item.tvmaze_id is not None and isinstance(episode, dict):
        update = _daily(tvmaze_episode_update(item, episode, local_day(now)), day_due)
        return [update] if update is not None else []
    if item.kind is Kind.game and item.urls:
        update = _page(item, data, hashes, now, day_due)
        return [update] if update is not None else []
    return []


def _page(item: WatchItem, data: dict, hashes: dict, now: datetime, day_due: bool) -> Update | None:
    if "page_text" not in data or not isinstance(data.get("page_text"), str):
        return None
    url = data.get("page_url") or (item.urls[0] if item.urls else "")
    return _daily(
        page_update(
            item,
            data["page_text"],
            hashes.get(item.slug),
            str(url),
            _as_utc(now),
        ),
        day_due,
    )


def _needs_model(update: Update) -> bool:
    """A news card with no short description has to be written by the model.

    NFL always goes through Grok so the line is written in the feed's voice.
    A missing key leaves a short NFL sentence as the source wrote it.
    """
    if update.source not in {"steam", "newswire", "nfl", "conduct"}:
        return False
    raw = "\n".join(update.lines).strip()
    if not raw:
        return False
    if update.source == "nfl":
        return True
    if len(raw) > 180:
        return True
    return raw.casefold() == update.title.casefold()


def _short(update: Update | None) -> Update | None:
    """Ask Grok what happened. Twitch titles and countdowns stay as written."""
    if update is None:
        return update
    if update.source == "conduct":
        update = replace(update, lines=tuple(mask_slur(line) for line in update.lines))
    if not _needs_model(update):
        return update
    note = ""
    if update.source == "conduct":
        note = (
            "If the text includes a word blanked with asterisks, keep that quote in the summary. "
            "Do not fill the asterisks in. If the person denied it, say so."
        )
    raw = "\n".join(update.lines)
    lines = (
        describe(update.title, raw, update.name, note=note)
        if note
        else describe(update.title, raw, update.name)
    )
    if update.source == "conduct":
        lines = conduct_lines(raw, lines)
    elif not lines and len(raw) <= 180 and raw.casefold() != update.title.casefold():
        lines = update.lines
    return replace(update, lines=lines)


def _daily(update: Update | None, day_due: bool) -> Update | None:
    if update is None:
        return None
    if not allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=day_due,
        changed=True,
        text=update.title,
    ):
        return None
    return update


def _state_day(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _twitch(
    item: WatchItem,
    data: dict,
    twitch_titles: dict,
    twitch_posts: dict,
    now: datetime,
) -> Update | None:
    """Post only when this login is live and the stream title changed."""
    del twitch_posts, now
    if "twitch" not in data:
        return None
    live = data.get("twitch")
    is_live = isinstance(live, dict)
    previous = twitch_titles.get(item.slug)
    title = str(live.get("title") or "").strip() if is_live else ""
    changed = bool(title) and title != str(previous or "").strip()
    if not allow_post(
        has_twitch=True,
        live=is_live,
        hour_due=True,
        day_due=False,
        changed=changed,
        text=title,
    ):
        return None
    return twitch_update(item, live if is_live else None, previous)


def _parse_stamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
