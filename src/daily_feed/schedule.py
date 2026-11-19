"""Once a day at 3pm America/Chicago. Streamers are checked every hour."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
RUN_HOUR = 15  # 3pm local


def _in_chicago(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=CHICAGO)
    return now.astimezone(CHICAGO)


def local_day(now: datetime) -> date:
    """Calendar date of ``now`` in America/Chicago. ``now`` may be aware UTC."""
    return _in_chicago(now).date()


def due(now: datetime, last_run_day: date | None) -> bool:
    """True at or after 3pm Chicago when that local date has not run yet.

    Before 3pm the run is not due, even when ``last_run_day`` is yesterday
    or has never been set.
    """
    local = _in_chicago(now)
    if local.hour < RUN_HOUR:
        return False
    return local.date() != last_run_day


COUNTDOWN_DAYS = 7


def days_until(today: date, event: date) -> int | None:
    """Days from ``today`` through ``event``, inside the one-week window.

    ``0`` is the day it lands. ``7`` is the first day. Anything earlier
    or later returns None.
    """
    remaining = (event - today).days
    if remaining < 0 or remaining > COUNTDOWN_DAYS:
        return None
    return remaining


def due_hourly(now: datetime, last_post: datetime | None) -> bool:
    """True when this streamer has not posted in the last hour.

    A missing ``last_post`` is due. Offline callers never reach this.
    """
    if last_post is None:
        return True
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    previous = last_post if last_post.tzinfo is not None else last_post.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc) - previous.astimezone(timezone.utc) >= timedelta(hours=1)
