"""HTTP for the sources that return real posts. Tests do not import this."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from daily_feed.feeds import (
    espn_articles,
    espn_now_image,
    espn_now_text,
    espn_search_hits,
    is_conduct,
    og_image,
    rockstar_articles,
    twitch_stream,
)
from daily_feed.parallel import run_parallel

_ROCKSTAR = "https://graph.rockstargames.com/"
_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=15"
_BEARS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/chi/news?limit=15"
_SEARCH = "https://site.api.espn.com/apis/search/v2?limit=8&query="
_NOW = "https://now.core.api.espn.com/v1/sports/news/"
_CONDUCT_QUERIES = ("racial slur", "homophobic", "anti-gay slur", "antisemitic")
_STEAM = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
_TWITCH_TOKEN = "https://id.twitch.tv/oauth2/token"
_TWITCH_STREAMS = "https://api.twitch.tv/helix/streams"
_QUERY = '{posts(locale:"en_us",limit:15){results{id created title url subtitle}}}'


def fetch_rockstar() -> list[dict]:
    payload = _json(
        _ROCKSTAR,
        method="POST",
        body=json.dumps({"query": _QUERY}).encode(),
        headers={"Content-Type": "application/json"},
    )
    if not isinstance(payload, dict):
        return []
    articles = rockstar_articles(payload)

    def _picture(article: dict) -> dict:
        html = _text(str(article.get("url") or ""))
        article["image"] = og_image(html)
        return article

    return list(run_parallel(articles, _picture))


def fetch_nfl() -> list[dict]:
    """NFL headlines plus the Chicago Bears team feed.

    nfl.com serves a shell, so this reads ESPN. Bears stories are marked
    ``focus=bears`` so a routine league headline cannot crowd them out.
    """
    general_payload = _json(_NFL)
    bears_payload = _json(_BEARS)
    general = espn_articles(general_payload) if isinstance(general_payload, dict) else []
    bears = espn_articles(bears_payload) if isinstance(bears_payload, dict) else []
    for article in bears:
        article["focus"] = "bears"
    ordered: list[dict] = []
    seen: set[str] = set()
    for article in [*bears, *general]:
        url = str(article.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        ordered.append(article)
    return ordered


def fetch_conduct(now: datetime | None = None) -> list[dict]:
    """ESPN stories from the last 7 days about a reported penalty for a slur or remark.

    The card uses ESPN's words. It does not decide that anyone committed slander.
    """
    clock = now or datetime.now(timezone.utc)
    cutoff = clock - timedelta(days=7)

    def _search(query: str) -> list[dict]:
        payload = _json(_SEARCH + urllib.parse.quote(query))
        if not isinstance(payload, dict):
            return []
        return espn_search_hits(payload)

    seen: set[str] = set()
    recent: list[dict] = []
    for batch in run_parallel(list(_CONDUCT_QUERIES), _search):
        for hit in batch:
            if hit["id"] in seen or hit["published_at"] < cutoff:
                continue
            seen.add(hit["id"])
            recent.append(hit)

    def _story(hit: dict) -> dict | None:
        payload = _json(_NOW + hit["id"])
        text = espn_now_text(payload if isinstance(payload, dict) else {})
        if not is_conduct(hit["title"], text):
            return None
        return {
            "id": hit["id"],
            "title": hit["title"],
            "url": hit["url"],
            "text": text or hit["title"],
            "published_at": hit["published_at"],
            "image": espn_now_image(payload if isinstance(payload, dict) else {}),
        }

    articles = [item for item in run_parallel(recent, _story) if item]
    articles.sort(key=lambda item: item["published_at"], reverse=True)
    return articles[:8]


def fetch_steam(app_id: int) -> dict:
    """Official Steam announcements for one app. No API key."""
    query = urllib.parse.urlencode(
        {
            "appid": app_id,
            "count": 20,
            "maxlength": 800,
            "feeds": "steam_community_announcements",
        }
    )
    payload = _json(f"{_STEAM}?{query}")
    if not isinstance(payload, dict):
        return {}
    payload["header_image"] = _steam_header(app_id)
    return payload


def fetch_streams(logins: list[str]) -> dict[str, dict]:
    """Live Helix streams keyed by login. An empty map when the app secrets are unset."""
    names = [login.strip() for login in logins if login and login.strip()]
    if not names:
        return {}
    client_id = os.environ.get("TWITCH_CLIENT_ID", "").strip()
    secret = os.environ.get("TWITCH_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return {}
    form = urllib.parse.urlencode(
        {"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"}
    ).encode()
    token_payload = _json(
        _TWITCH_TOKEN,
        method="POST",
        body=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
    if not isinstance(token, str) or not token:
        return {}
    query = urllib.parse.urlencode([("user_login", name) for name in names])
    payload = _json(
        f"{_TWITCH_STREAMS}?{query}",
        headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"},
    )
    if not isinstance(payload, dict):
        return {}
    found: dict[str, dict] = {}
    for name in names:
        stream = twitch_stream(payload, name)
        if stream is not None:
            found[name.casefold()] = stream
    return found


def _steam_header(app_id: int) -> str:
    payload = _json(f"https://store.steampowered.com/api/appdetails?appids={app_id}")
    if not isinstance(payload, dict):
        return ""
    app = payload.get(str(app_id))
    data = app.get("data") if isinstance(app, dict) else None
    header = str(data.get("header_image") or "") if isinstance(data, dict) else ""
    return header if header.startswith("https://") else ""


def _text(url: str) -> str:
    if not url.startswith("https://"):
        return ""
    request = urllib.request.Request(url, headers={"User-Agent": "daily-feed/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read(200000).decode("utf-8", "replace")
    except (OSError, ValueError):
        return ""


def _json(
    url: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict | list | None:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"User-Agent": "daily-feed/0.1", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
