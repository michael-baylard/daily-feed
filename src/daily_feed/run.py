"""Build the day's posts from a locked watchlist.

Steam, TVMaze, and Twitch updates are parsed from payloads already in hand.
A model is used only for a movie or publisher page whose content hash
changed. ``page_prompts`` is that request. Nothing here calls a model or
the network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from daily_feed.discord_md import render
from daily_feed.hashing import content_hash
from daily_feed.models import Kind, Update, WatchItem
from daily_feed.order import sort_updates
from daily_feed.prompt import build_prompt
from daily_feed.safety import assert_no_pings
from daily_feed.schedule import local_day
from daily_feed.sources import (
    page_update,
    steam_news_update,
    tvmaze_episode_update,
    twitch_update,
)


def collect(
    items: list[WatchItem], fetched: dict, state: dict, now: datetime
) -> list[Update]:
    """New updates for items on the list, oldest release first.

    Keys in ``fetched`` whose slug is not on the list are ignored.
    """
    hashes = state.get("hashes") or {}
    seen_ids = {str(gid) for gid in (state.get("seen_ids") or [])}
    twitch_titles = state.get("twitch_titles") or {}
    updates: list[Update] = []
    for item in items:
        data = fetched.get(item.slug)
        if not isinstance(data, dict):
            continue
        update = _one(item, data, hashes, seen_ids, twitch_titles, now)
        if update is not None:
            updates.append(update)
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


def render_day(updates: list[Update]) -> list[str]:
    """Discord markdown in the given order. Each message is ping-checked."""
    messages: list[str] = []
    for update in updates:
        text = render(update)
        assert_no_pings(text)
        messages.append(text)
    return messages


def remember(state: dict, updates: list[Update], fetched: dict, now: datetime) -> dict:
    """State after a completed run. Does not write the file or post.

    The Chicago date is consumed even when nothing was new. Steam gids at
    or before the posted item are remembered so older patches are not
    walked backwards on the next day.
    """
    stored = {
        "last_run_day": local_day(now).isoformat(),
        "hashes": dict(state.get("hashes") or {}),
        "seen_ids": [str(gid) for gid in (state.get("seen_ids") or [])],
        "twitch_titles": dict(state.get("twitch_titles") or {}),
    }
    seen = set(stored["seen_ids"])
    for update in updates:
        data = fetched.get(update.slug) if isinstance(fetched.get(update.slug), dict) else {}
        if update.source == "page":
            page_text = data.get("page_text") if isinstance(data, dict) else ""
            stored["hashes"][update.slug] = content_hash(page_text if isinstance(page_text, str) else "")
        elif update.source == "twitch":
            stored["twitch_titles"][update.slug] = update.lines[0] if update.lines else update.title
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


def _one(
    item: WatchItem,
    data: dict,
    hashes: dict,
    seen_ids: set[str],
    twitch_titles: dict,
    now: datetime,
) -> Update | None:
    if item.kind == Kind.person:
        if "twitch" not in data:
            return None
        return twitch_update(item, data.get("twitch"), twitch_titles.get(item.slug))

    if item.kind in (Kind.movie, Kind.publisher):
        if "page_text" not in data or not isinstance(data.get("page_text"), str):
            return None
        url = data.get("page_url") or (item.urls[0] if item.urls else "")
        return page_update(
            item,
            data["page_text"],
            hashes.get(item.slug),
            str(url),
            _as_utc(now),
        )

    if item.steam_app_id is not None and isinstance(data.get("steam"), dict):
        return steam_news_update(item, data["steam"], seen_ids)

    episode = data.get("episode")
    if item.tvmaze_id is not None and isinstance(episode, dict):
        return tvmaze_episode_update(item, episode, local_day(now))
    return None


def _as_utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
