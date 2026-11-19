"""Once a day at 3pm America/Chicago."""

from __future__ import annotations

from datetime import date, datetime
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
