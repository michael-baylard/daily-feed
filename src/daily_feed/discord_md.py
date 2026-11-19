"""Render one Update as a Discord message body."""

from __future__ import annotations

from daily_feed.models import Kind, Update
from daily_feed.safety import assert_no_pings, strip_pings

KIND_EMOJI = {
    Kind.game: "🎮",
    Kind.show: "📺",
    Kind.movie: "🎬",
    Kind.publisher: "📰",
    Kind.person: "👤",
    Kind.tool: "🛠️",
    Kind.athlete: "🏅",
    Kind.league: "🏆",
    Kind.match: "🆚",
}
_TWITCH_EMOJI = "🔴"
_FILLER = {"update", "is live"}


def render(update: Update) -> str:
    """Discord markdown for one update. Not an embed.

    The title is the link. A title that only repeats the name is dropped
    and the name carries the link instead. A bullet that repeats either
    one is dropped. There is no separate "Open {kind}" line.

    Shape::

        {emoji} {name} - #{source}
        **[{title}]({url})**
        - {line}
    """
    name = strip_pings(update.name).rstrip()
    title = strip_pings(update.title).rstrip()
    source = strip_pings(update.source).rstrip()
    lines = [strip_pings(line).rstrip() for line in update.lines if strip_pings(line).rstrip()]
    emoji = _TWITCH_EMOJI if source == "twitch" else KIND_EMOJI[update.kind]
    folded_name = name.casefold()
    folded_title = title.casefold()
    title_repeats_name = folded_title in {folded_name, *(f"{folded_name} {word}" for word in _FILLER)}
    kept = [
        line
        for line in lines
        if line.casefold() not in {folded_name, folded_title, *(f"{folded_name} {word}" for word in _FILLER)}
    ]

    tag = f" - #{source}" if source else ""
    if title and not title_repeats_name:
        parts = [f"{emoji} {name}{tag}", _link(title, update.url)]
    else:
        parts = [f"{emoji} {_link(name, update.url)}{tag}"]
    parts.extend(f"- {line}" for line in kept)

    text = "\n".join(part.rstrip() for part in parts)
    assert_no_pings(text)
    return text


def _link(label: str, url: str) -> str:
    safe = label.replace("[", "").replace("]", "")
    return f"**[{safe}]({url})**"
