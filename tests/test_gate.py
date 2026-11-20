"""LangGraph gate. No network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from daily_feed.gate import allow_post
from daily_feed.models import Kind, WatchItem
from daily_feed.run import collect

NOW = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)
LIVE = {
    "user_login": "burntpeanut",
    "title": "ranked",
    "started_at": "2026-11-19T20:00:00Z",
}


def test_streamer_posts_when_live_and_the_hour_is_due() -> None:
    assert allow_post(
        has_twitch=True,
        live=True,
        hour_due=True,
        day_due=False,
        changed=True,
        text="ranked",
    )


def test_streamer_skips_when_offline() -> None:
    assert not allow_post(
        has_twitch=True,
        live=False,
        hour_due=True,
        day_due=False,
        changed=False,
        text="",
    )


def test_streamer_posts_the_same_title_when_the_hour_is_due() -> None:
    assert allow_post(
        has_twitch=True,
        live=True,
        hour_due=True,
        day_due=False,
        changed=False,
        text="ranked",
    )


def test_streamer_skips_inside_the_hour() -> None:
    assert not allow_post(
        has_twitch=True,
        live=True,
        hour_due=False,
        day_due=False,
        changed=True,
        text="new title",
    )


def test_daily_posts_at_3pm_when_the_page_changed() -> None:
    assert allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=True,
        changed=True,
        text="new patch",
    )


def test_daily_skips_before_3pm_even_if_the_page_changed() -> None:
    assert not allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=False,
        changed=True,
        text="new patch",
    )


def test_ping_text_is_blocked() -> None:
    assert not allow_post(
        has_twitch=True,
        live=True,
        hour_due=True,
        day_due=False,
        changed=True,
        text="hello @everyone",
    )


def test_collect_skips_an_offline_streamer() -> None:
    item = WatchItem(kind=Kind.person, name="BurntPeanut", slug="burntpeanut", twitch_login="burntpeanut")
    fetched = {"burntpeanut": {"twitch": None}}
    assert collect([item], fetched, {"twitch_posts": {}}, NOW) == []


def test_collect_posts_the_same_title_when_the_hour_is_due() -> None:
    item = WatchItem(kind=Kind.person, name="BurntPeanut", slug="burntpeanut", twitch_login="burntpeanut")
    fetched = {"burntpeanut": {"twitch": LIVE}}
    earlier = (NOW - timedelta(hours=2)).isoformat()
    state = {
        "twitch_titles": {"burntpeanut": "ranked"},
        "twitch_posts": {"burntpeanut": earlier},
    }
    updates = collect([item], fetched, state, NOW)
    assert len(updates) == 1
    assert updates[0].title == "ranked"


def test_collect_skips_a_live_streamer_inside_the_hour() -> None:
    item = WatchItem(kind=Kind.person, name="BurntPeanut", slug="burntpeanut", twitch_login="burntpeanut")
    fetched = {"burntpeanut": {"twitch": {**LIVE, "title": "new game"}}}
    recent = (NOW - timedelta(minutes=10)).isoformat()
    state = {
        "twitch_titles": {"burntpeanut": "ranked"},
        "twitch_posts": {"burntpeanut": recent},
    }
    assert collect([item], fetched, state, NOW) == []
