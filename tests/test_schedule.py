"""3pm America/Chicago gate. No network."""

from __future__ import annotations

from datetime import date, datetime, timezone

from daily_feed.schedule import CHICAGO, RUN_HOUR, due, local_day

_YESTERDAY = date(2026, 11, 18)
_TODAY = date(2026, 11, 19)


def test_run_hour_is_3pm() -> None:
    assert RUN_HOUR == 15


def test_due_false_at_14_chicago_when_last_run_was_yesterday() -> None:
    at_14 = datetime(2026, 11, 19, 14, 0, tzinfo=CHICAGO)
    assert due(at_14, _YESTERDAY) is False
    assert due(at_14.astimezone(timezone.utc), _YESTERDAY) is False


def test_due_true_at_15_chicago_when_last_run_was_yesterday() -> None:
    at_15 = datetime(2026, 11, 19, 15, 0, tzinfo=CHICAGO)
    assert due(at_15, _YESTERDAY) is True
    assert due(at_15.astimezone(timezone.utc), _YESTERDAY) is True


def test_due_false_at_16_chicago_when_last_run_is_today() -> None:
    at_16 = datetime(2026, 11, 19, 16, 0, tzinfo=CHICAGO)
    assert due(at_16, _TODAY) is False


def test_due_false_before_3pm_even_if_never_run() -> None:
    at_1459 = datetime(2026, 11, 19, 14, 59, tzinfo=CHICAGO)
    assert due(at_1459, None) is False
    assert due(at_1459, _YESTERDAY) is False


def test_local_day_uses_chicago_not_the_utc_date() -> None:
    # 05:30 UTC on Nov 20 is still the evening of Nov 19 in Chicago.
    now = datetime(2026, 11, 20, 5, 30, tzinfo=timezone.utc)
    assert local_day(now) == _TODAY
    assert due(now, _YESTERDAY) is True
    assert due(now, _TODAY) is False
