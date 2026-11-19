"""Sort order for the daily post."""

from __future__ import annotations

from datetime import datetime, timezone

from daily_feed.models import Kind, Update
from daily_feed.order import sort_updates


def _update(
    *,
    slug: str,
    published_at: datetime,
    url: str = "https://example.com/item",
) -> Update:
    return Update(
        slug=slug,
        kind=Kind.movie,
        name=slug,
        title=slug,
        published_at=published_at,
        url=url,
        lines=("one",),
        source="page",
    )


def test_later_update_is_second() -> None:
    early = _update(slug="early", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    late = _update(slug="late", published_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    ordered = sort_updates([late, early])
    assert [item.slug for item in ordered] == ["early", "late"]


def test_equal_time_sorts_by_slug() -> None:
    when = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    zeta = _update(slug="zeta", published_at=when)
    alpha = _update(slug="alpha", published_at=when)
    ordered = sort_updates([zeta, alpha])
    assert [item.slug for item in ordered] == ["alpha", "zeta"]


def test_equal_time_and_slug_sorts_by_url() -> None:
    when = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    later_url = _update(
        slug="same",
        published_at=when,
        url="https://example.com/b",
    )
    earlier_url = _update(
        slug="same",
        published_at=when,
        url="https://example.com/a",
    )
    ordered = sort_updates([later_url, earlier_url])
    assert [item.url for item in ordered] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_sort_does_not_mutate_input() -> None:
    first = _update(slug="z", published_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    second = _update(slug="a", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    updates = [first, second]
    before = [item.slug for item in updates]
    ordered = sort_updates(updates)
    assert [item.slug for item in updates] == before
    assert updates == [first, second]
    assert ordered is not updates
    assert [item.slug for item in ordered] == ["a", "z"]


def test_time_beats_slug() -> None:
    early_z = _update(slug="z", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    late_a = _update(slug="a", published_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    ordered = sort_updates([late_a, early_z])
    assert [item.slug for item in ordered] == ["z", "a"]
