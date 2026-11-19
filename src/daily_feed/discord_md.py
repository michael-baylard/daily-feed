"""Render one Update as a Discord message body."""

from __future__ import annotations

from daily_feed.models import Update
from daily_feed.safety import assert_no_pings, strip_pings


def render(update: Update) -> str:
    """Discord markdown for one update. Not an embed.

    Shape::

        ## {name}
        **{title}**
        - {line}

        [Open {kind}]({url})
        -# {source}

    An empty ``lines`` tuple skips the bullet block, so the link follows
    the title after a single blank line.
    """
    name = strip_pings(update.name).rstrip()
    title = strip_pings(update.title).rstrip()
    source = strip_pings(update.source).rstrip()
    lines = [strip_pings(line).rstrip() for line in update.lines]
    label = f"Open {update.kind.value}"

    parts: list[str] = [f"## {name}", f"**{title}**"]
    if lines:
        parts.extend(f"- {line}" for line in lines)
    parts.append("")
    parts.append(f"[{label}]({update.url})")
    parts.append(f"-# {source}")

    text = "\n".join(part.rstrip() for part in parts)
    assert_no_pings(text)
    return text
