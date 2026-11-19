"""Matrix coverage for schedule.due, days_until, due_hourly, and gate.allow_post. No network."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from daily_feed.gate import allow_post
from daily_feed.schedule import CHICAGO, RUN_HOUR, days_until, due, due_hourly, local_day

_YESTERDAY = date(2026, 11, 18)
_TODAY = date(2026, 11, 19)
_EVENT = date(2026, 11, 26)


def _chicago(y: int, m: int, d: int, hour: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, hour, minute, tzinfo=CHICAGO)


@pytest.mark.parametrize("hour", range(RUN_HOUR))
@pytest.mark.parametrize("last_run_day", (None, _YESTERDAY, _TODAY))
def test_matrix_due_false_before_3pm_chicago(hour: int, last_run_day: date | None) -> None:
    at = _chicago(2026, 11, 19, hour, 59 if hour == RUN_HOUR - 1 else 0)
    assert due(at, last_run_day) is False
    assert due(at.astimezone(timezone.utc), last_run_day) is False


@pytest.mark.parametrize("hour", range(RUN_HOUR, 24))
@pytest.mark.parametrize("last_run_day", (None, _YESTERDAY))
def test_matrix_due_true_at_or_after_3pm_when_not_run_today(hour: int, last_run_day: date | None) -> None:
    at = _chicago(2026, 11, 19, hour)
    assert due(at, last_run_day) is True
    assert due(at.astimezone(timezone.utc), last_run_day) is True


@pytest.mark.parametrize("hour", range(RUN_HOUR, 24))
def test_matrix_due_false_after_3pm_when_last_run_is_today(hour: int) -> None:
    at = _chicago(2026, 11, 19, hour)
    assert due(at, _TODAY) is False


@pytest.mark.parametrize(
    ("utc_when", "expected_day"),
    [
        (datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc), _TODAY),
        (datetime(2026, 11, 20, 5, 30, tzinfo=timezone.utc), _TODAY),
        (datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc), date(2026, 11, 20)),
        (datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc), _TODAY),
        (datetime(2026, 11, 18, 6, 0, tzinfo=timezone.utc), _YESTERDAY),
    ],
)
def test_matrix_local_day_follows_chicago(utc_when: datetime, expected_day: date) -> None:
    assert local_day(utc_when) == expected_day
    assert local_day(utc_when.astimezone(CHICAGO)) == expected_day


@pytest.mark.parametrize(
    ("today", "event", "expected"),
    [
        (date(2026, 11, 11), _EVENT, None),
        (date(2026, 11, 18), _EVENT, None),
        (date(2026, 11, 19), _EVENT, 7),
        (date(2026, 11, 20), _EVENT, 6),
        (date(2026, 11, 21), _EVENT, 5),
        (date(2026, 11, 22), _EVENT, 4),
        (date(2026, 11, 23), _EVENT, 3),
        (date(2026, 11, 24), _EVENT, 2),
        (date(2026, 11, 25), _EVENT, 1),
        (date(2026, 11, 26), _EVENT, 0),
        (date(2026, 11, 27), _EVENT, None),
        (date(2026, 12, 1), _EVENT, None),
        (_EVENT, _EVENT, 0),
        (_TODAY, date(2026, 12, 3), None),
    ],
)
def test_matrix_days_until_window(today: date, event: date, expected: int | None) -> None:
    assert days_until(today, event) == expected


@pytest.mark.parametrize(
    ("minutes_ago", "expected_due"),
    [
        (None, True),
        (0, False),
        (1, False),
        (30, False),
        (59, False),
        (60, True),
        (90, True),
    ],
)
def test_matrix_due_hourly_elapsed(minutes_ago: int | None, expected_due: bool) -> None:
    now = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)
    last = None if minutes_ago is None else now - timedelta(minutes=minutes_ago)
    assert due_hourly(now, last) is expected_due


def test_matrix_due_hourly_naive_datetimes_treated_as_utc() -> None:
    now = datetime(2026, 11, 19, 18, 0)
    last = datetime(2026, 11, 19, 17, 1)
    assert due_hourly(now, last) is False
    last_due = datetime(2026, 11, 19, 17, 0)
    assert due_hourly(now, last_due) is True


@pytest.mark.parametrize("hour_due", (True, False))
def test_matrix_streamer_posts_live_and_changed_ignores_hour_due(hour_due: bool) -> None:
    assert allow_post(
        has_twitch=True,
        live=True,
        hour_due=hour_due,
        day_due=False,
        changed=True,
        text="updated title",
    )


@pytest.mark.parametrize("hour_due", (True, False))
def test_matrix_streamer_skips_offline_even_when_hour_due(hour_due: bool) -> None:
    assert not allow_post(
        has_twitch=True,
        live=False,
        hour_due=hour_due,
        day_due=True,
        changed=True,
        text="ignored",
    )


@pytest.mark.parametrize("hour_due", (True, False))
def test_matrix_streamer_skips_unchanged_title(hour_due: bool) -> None:
    assert not allow_post(
        has_twitch=True,
        live=True,
        hour_due=hour_due,
        day_due=False,
        changed=False,
        text="same title",
    )


def test_matrix_daily_posts_day_due_and_changed() -> None:
    assert allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=True,
        changed=True,
        text="patch notes",
    )


def test_matrix_daily_skips_when_changed_but_not_day_due() -> None:
    assert not allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=False,
        changed=True,
        text="early change",
    )


def test_matrix_daily_skips_unchanged_on_due_day() -> None:
    assert not allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=True,
        changed=False,
        text="no diff",
    )


@pytest.mark.parametrize(
    "text",
    [
        "hi @everyone",
        "hi @EVERYONE",
        "wave @Here",
        "wave @HERE",
        "user <@123456789>",
        "role <@&987654321>",
        "mixed @EvErYoNe and <@111>",
    ],
)
def test_matrix_ping_in_text_forces_skip(text: str) -> None:
    assert not allow_post(
        has_twitch=True,
        live=True,
        hour_due=True,
        day_due=True,
        changed=True,
        text=text,
    )
    assert not allow_post(
        has_twitch=False,
        live=False,
        hour_due=False,
        day_due=True,
        changed=True,
        text=text,
    )


def test_matrix_twitch_routes_streamer_when_day_also_due_live_changed() -> None:
    assert allow_post(
        has_twitch=True,
        live=True,
        hour_due=False,
        day_due=True,
        changed=True,
        text="live now",
    )


def test_matrix_twitch_routes_streamer_not_daily_when_offline_on_due_day() -> None:
    assert not allow_post(
        has_twitch=True,
        live=False,
        hour_due=False,
        day_due=True,
        changed=True,
        text="would-be daily",
    )