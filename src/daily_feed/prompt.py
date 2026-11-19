"""Prompt text for a changed studio or movie page. This does not call a model."""

from __future__ import annotations

from daily_feed.models import WatchItem
from daily_feed.slug import to_slug

_PAGE_LIMIT = 4000


def build_prompt(item: WatchItem, page_text: str) -> str:
    """What we would send when a page fingerprint changes.

    Includes the watchlist slug, the snake_case slug of the name, the
    lowercase search form (that slug with underscores removed), the kind,
    and the page text trimmed to 4000 characters.
    """
    name_slug = to_slug(item.name)
    slug = item.slug or name_slug
    search = name_slug.replace("_", "")
    kind = item.kind.value
    body = page_text[:_PAGE_LIMIT]
    return (
        f"Slug: {slug}\n"
        f"Name slug: {name_slug}\n"
        f"Search: {search}\n"
        f"Kind: {kind}\n"
        "Return exactly 3 plain lines.\n"
        "No @ mentions.\n"
        "No links in the lines.\n"
        "AI only when it is about this title.\n"
        "An AI mod, or this game, show, movie, or league using AI, is in scope.\n"
        "A general model or tool launch is out of scope.\n"
        "\n"
        f"{body}"
    )
