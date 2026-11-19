"""Stop scraped pages from turning a Discord post into a ping."""

from __future__ import annotations

import re

PING_MARKERS = ("@everyone", "@here", "<@", "<@&")

_EVERYONE = re.compile(r"@everyone", re.IGNORECASE)
_HERE = re.compile(r"@here", re.IGNORECASE)


def find_pings(text: str) -> list[str]:
    """Return ping markers present in text.

    ``@everyone`` and ``@here`` match case-insensitively. ``<@`` and ``<@&``
    are literal. A role mention contains both ``<@`` and ``<@&``.
    """
    found: list[str] = []
    if _EVERYONE.search(text):
        found.append("@everyone")
    if _HERE.search(text):
        found.append("@here")
    if "<@" in text:
        found.append("<@")
    if "<@&" in text:
        found.append("<@&")
    return found


def assert_no_pings(text: str) -> None:
    """Raise ValueError when text still contains a ping marker."""
    found = find_pings(text)
    if found:
        listed = ", ".join(found)
        raise ValueError(f"Discord message contains ping markers: {listed}")


def strip_pings(text: str) -> str:
    """Remove ping markers so a scraped line cannot mention the channel.

    ``@everyone`` and ``@here`` are removed case-insensitively. The role
    marker ``<@&`` is removed before ``<@`` so a role mention is not left
    as a bare ampersand.
    """
    cleaned = _EVERYONE.sub("", text)
    cleaned = _HERE.sub("", cleaned)
    cleaned = cleaned.replace("<@&", "")
    cleaned = cleaned.replace("<@", "")
    return cleaned
