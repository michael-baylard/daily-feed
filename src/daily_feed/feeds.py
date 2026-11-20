"""Turn Rockstar, ESPN, and Twitch payloads into article dicts. No HTTP."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_TOPIC = (
    "racial slur",
    "racist",
    "racism",
    "homophobic",
    "anti-gay",
    "antigay",
    "anti-lgbt",
    "antisemit",
)
_CONSEQUENCE = (
    "suspended",
    "suspension",
    "fired",
    "banned",
    "ban ",
    "on leave",
    "terminated",
    "apology",
    "apolog",
    "dropped",
)
_SKIP = ("teenager", "teenagers", " teen ", " teens", "middle school", " a minor")

_EASTERN = ZoneInfo("America/New_York")


def rockstar_articles(payload: dict) -> list[dict]:
    """Newswire posts from ``graph.rockstargames.com``."""
    results = ((payload.get("data") or {}).get("posts") or {}).get("results") or []
    articles: list[dict] = []
    for post in results:
        if not isinstance(post, dict):
            continue
        title = str(post.get("title") or "").strip()
        path = str(post.get("url") or "").strip()
        if not title or not path:
            continue
        url = path if path.startswith("http") else f"https://www.rockstargames.com{path}"
        subtitle = str(post.get("subtitle") or "").strip()
        articles.append(
            {
                "id": str(post.get("id") or url),
                "title": title,
                "url": url,
                "text": subtitle or title,
                "published_at": _rockstar_time(str(post.get("created") or "")),
            }
        )
    return articles


def roster_names(payload: dict) -> set[str]:
    """Full names from an ESPN team roster. Matching is case-insensitive."""
    names: set[str] = set()
    for group in payload.get("athletes") or []:
        if not isinstance(group, dict):
            continue
        for person in group.get("items") or []:
            if not isinstance(person, dict):
                continue
            name = str(person.get("fullName") or person.get("displayName") or "").strip()
            if name:
                names.add(name.casefold())
    return names


def bears_story(item: dict, roster: set[str]) -> bool:
    """True when the headline is about the Bears or a player on the roster.

    A Chicago tag is not enough. ESPN also tags the Bears on an opponent's injury note.
    """
    athletes: list[str] = []
    for category in item.get("categories") or []:
        if isinstance(category, dict) and category.get("type") == "athlete":
            name = str(category.get("description") or "").strip()
            if name:
                athletes.append(name)
    roster_names_in_story = [name for name in athletes if name.casefold() in roster]
    others = [name for name in athletes if name.casefold() not in roster]
    headline = str(item.get("headline") or item.get("displayName") or "").strip()
    folded = headline.casefold()
    if roster_names_in_story and not others:
        return True
    if any(folded.startswith(name.casefold()) for name in others):
        return False
    if roster_names_in_story and any(name.casefold() in folded for name in roster_names_in_story):
        return True
    if others:
        return False
    return folded.startswith(("bears", "chicago bears", "the bears"))


def espn_articles(payload: dict, roster: set[str] | None = None) -> list[dict]:
    """NFL headlines from ESPN's public NFL news JSON."""
    names = roster or set()
    articles: list[dict] = []
    for item in payload.get("articles") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("headline") or "").strip()
        links = item.get("links") if isinstance(item.get("links"), dict) else {}
        web = links.get("web") if isinstance(links.get("web"), dict) else {}
        url = str(web.get("href") or "").strip()
        if not title or not url:
            continue
        description = str(item.get("description") or "").strip()
        article = {
            "id": str(item.get("id") or url),
            "title": title,
            "url": url,
            "text": description or title,
            "published_at": _iso(str(item.get("published") or "")),
            "image": image_url(item.get("images")),
        }
        if names and bears_story(item, names):
            article["focus"] = "bears"
        articles.append(article)
    return articles


def espn_search_hits(payload: dict) -> list[dict]:
    """Article hits from ESPN search. Videos are dropped."""
    hits: list[dict] = []
    for group in payload.get("results") or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("contents") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").casefold() not in {"headlinenews", "story", "article"}:
                continue
            title = str(item.get("displayName") or "").strip()
            link = item.get("link") if isinstance(item.get("link"), dict) else {}
            url = str(link.get("web") or "").strip()
            story_id = str(item.get("id") or "").strip()
            if not title or not url or not story_id.isdigit():
                continue
            hits.append(
                {
                    "id": story_id,
                    "title": title,
                    "url": url,
                    "published_at": _iso(str(item.get("date") or "")),
                }
            )
    return hits


def bears_from_search(payload: dict, roster: set[str]) -> list[dict]:
    """Bears stories from ESPN search. The front page drops them after a day."""
    articles: list[dict] = []
    for group in payload.get("results") or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("contents") or []:
            if not isinstance(item, dict) or not bears_story(item, roster):
                continue
            link = item.get("link") if isinstance(item.get("link"), dict) else {}
            url = str(link.get("web") or "").strip()
            title = str(item.get("displayName") or "").strip()
            published = _iso(str(item.get("date") or ""))
            if not url or not title or published.year < 2000:
                continue
            if "/video/" in url or "/team/" in url:
                continue
            articles.append(
                {
                    "id": str(item.get("id") or url),
                    "title": title,
                    "url": url,
                    "text": title,
                    "published_at": published,
                    "image": image_url(item.get("images")),
                    "focus": "bears",
                }
            )
    return articles


def og_image(html: str) -> str:
    """The og:image URL in a page, when that URL is https."""
    match = re.search(r'property="og:image" content="(https://[^"]+)"', html)
    return match.group(1) if match else ""


def image_url(value: object) -> str:
    """First https picture URL in an ESPN image field."""
    if isinstance(value, str) and value.startswith("https://"):
        return value
    if isinstance(value, dict):
        for key in ("url", "href", "src"):
            found = image_url(value.get(key))
            if found:
                return found
        return ""
    if isinstance(value, list):
        for item in value:
            found = image_url(item)
            if found:
                return found
    return ""


def espn_now_image(payload: dict) -> str:
    headlines = payload.get("headlines") or []
    if not headlines or not isinstance(headlines[0], dict):
        return ""
    return image_url(headlines[0].get("images"))


def espn_now_text(payload: dict) -> str:
    """Plain text of one ESPN Now story, capped for the summary model."""
    headlines = payload.get("headlines") or []
    if not headlines or not isinstance(headlines[0], dict):
        return ""
    story = _plain(str(headlines[0].get("story") or ""))
    description = str(headlines[0].get("description") or "").strip()
    return (story or description)[:1600]


def is_conduct(title: str, text: str) -> bool:
    """A reported penalty tied to a racist, anti-LGBTQ, or antisemitic remark.

    Stories about teenagers and middle schools are left out.
    """
    blob = f"{title}\n{text}".casefold()
    if any(word in blob for word in _SKIP):
        return False
    return any(word in blob for word in _TOPIC) and any(word in blob for word in _CONSEQUENCE)


def twitch_stream(payload: dict, login: str) -> dict | None:
    """The Helix stream for ``login``, or None when that login is offline."""
    for stream in payload.get("data") or []:
        if not isinstance(stream, dict):
            continue
        if str(stream.get("user_login") or "").casefold() != login.casefold():
            continue
        if str(stream.get("type") or "live").casefold() not in {"", "live"}:
            continue
        thumb = str(stream.get("thumbnail_url") or "")
        return {
            "user_login": login,
            "title": str(stream.get("title") or ""),
            "started_at": str(stream.get("started_at") or ""),
            "image": thumb.replace("{width}", "1280").replace("{height}", "720"),
        }
    return None


def _rockstar_time(value: str) -> datetime:
    text = value.replace("\u202f", " ").replace("\xa0", " ").strip()
    try:
        parsed = datetime.strptime(text, "%m/%d/%y, %I:%M %p")
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return parsed.replace(tzinfo=_EASTERN)


def _plain(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _iso(value: str) -> datetime:
    text = value.strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
