"""Order the day's updates before they are posted."""

from __future__ import annotations

from daily_feed.models import Update


def sort_updates(updates: list[Update]) -> list[Update]:
    """Oldest published_at first. Tie-break by slug, then url.

    Returns a new list. The input list is left unchanged.
    """
    return sorted(updates, key=lambda update: (update.published_at, update.slug, update.url))
