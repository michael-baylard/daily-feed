"""Discord markdown body for one Update."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daily_feed.discord_md import KIND_EMOJI, render, render_digest
from daily_feed.models import Kind, Update

BATMAN_RENDER = (
    "🎬 The Batman\n"
    "**[New trailer](https://example.com/the-batman)**\n"
    "- Trailer drops Friday.\n"
    "- Runtime is 176 minutes."
)


def _update(**overrides: object) -> Update:
    data: dict[str, object] = {
        "slug": "the-batman",
        "kind": Kind.movie,
        "name": "The Batman",
        "title": "New trailer",
        "published_at": datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        "url": "https://example.com/the-batman",
        "lines": ("Trailer drops Friday.", "Runtime is 176 minutes."),
        "source": "page",
    }
    data.update(overrides)
    return Update(**data)  # type: ignore[arg-type]


def test_render_batman_snapshot() -> None:
    text = render(_update())
    assert text == BATMAN_RENDER
    assert "🎬 The Batman\n" in text
    assert "#page" not in text
    assert "[New trailer](https://example.com/the-batman)" in text
    assert "Open movie" not in text
    assert not any(line.startswith("-#") for line in text.splitlines())


def test_render_strips_everyone_from_line() -> None:
    text = render(_update(lines=("hello @everyone",)))
    assert "@everyone" not in text.lower()
    assert "hello" in text
    assert "- hello" in text.splitlines()


def test_render_strips_here() -> None:
    text = render(_update(lines=("room @HERE now",)))
    assert "@here" not in text.lower()
    assert "<@" not in text


def test_render_strips_user_mention() -> None:
    text = render(_update(lines=("cast <@123> listed",)))
    assert "<@" not in text
    assert "<@123>" not in text


def test_render_strips_role_mention() -> None:
    text = render(_update(lines=("mods <@&123> listed",)))
    assert "<@" not in text
    assert "<@&" not in text
    assert "<@&123>" not in text


def test_render_empty_lines_still_have_header_and_link() -> None:
    text = render(_update(lines=()))
    assert text.startswith("🎬 The Batman\n")
    assert "[New trailer](https://example.com/the-batman)" in text
    assert not any(line.startswith("-#") for line in text.splitlines())
    assert not any(line.startswith("- ") for line in text.splitlines())
    expected = (
        "🎬 The Batman\n"
        "**[New trailer](https://example.com/the-batman)**"
    )
    assert text == expected


def test_render_has_no_trailing_spaces() -> None:
    text = render(
        _update(
            name="The Batman @everyone",
            title="New trailer @here",
            lines=("line <@123> ",),
            source="page <@&9>",
        )
    )
    assert all(not line.endswith(" ") for line in text.split("\n"))
    assert "@everyone" not in text.lower()
    assert "@here" not in text.lower()
    assert "<@" not in text


def test_render_strips_name_title_and_source() -> None:
    text = render(
        _update(
            name="The Batman @everyone",
            title="News @HERE",
            source="page <@123>",
            lines=(),
        )
    )
    assert text.splitlines()[0] == "🎬 The Batman"
    assert "**[News](https://example.com/the-batman)**" in text
    assert not any(line.startswith("-#") for line in text.splitlines())
    assert "@everyone" not in text.lower()
    assert "@here" not in text.lower()
    assert "<@" not in text


def test_render_emoji_and_linked_title_for_each_kind() -> None:
    url = "https://example.com/item"
    for kind in Kind:
        text = render(_update(kind=kind, url=url, lines=()))
        assert text.splitlines()[0].startswith(KIND_EMOJI[kind] + " ")
        assert f"**[New trailer]({url})**" in text
        assert "Open " not in text


def test_render_links_the_name_when_the_title_repeats_it() -> None:
    text = render(
        _update(
            kind=Kind.person,
            name="BurntPeanut",
            title="BurntPeanut is live",
            lines=("BurntPeanut is live",),
            url="https://www.twitch.tv/burntpeanut",
            source="twitch",
        )
    )
    assert text == (
        "🔴 **[BurntPeanut](https://www.twitch.tv/burntpeanut)**"
    )


def test_digest_groups_a_kind_and_splits_stories() -> None:
    bears = _update(
        slug="nfl",
        kind=Kind.league,
        name="NFL",
        title="Bears win",
        url="https://www.espn.com/nfl/story/bears",
        lines=("Williams threw four.",),
        source="nfl",
    )
    hippo = _update(
        slug="nfl",
        kind=Kind.league,
        name="NFL",
        title="Fiona the hippo",
        url="https://www.espn.com/nfl/story/hippo",
        lines=("The hippo stopped by.",),
        source="nfl",
        published_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
    )
    game = _update(kind=Kind.game, name="Grand Theft Auto Online", title="Kortz Center", source="steam")
    messages = render_digest([game, bears, hippo])
    assert len(messages) == 3
    assert messages[0].startswith("🎮")
    assert "Grand Theft Auto Online" in messages[0]
    assert "https://store.steampowered.com/app/1" in messages[0] or "Kortz" in messages[0]
    assert messages[1].startswith("🏆")
    assert "Bears win" in messages[1]
    assert "Fiona" not in messages[1]
    assert messages[2].startswith("🏆")
    assert "Fiona the hippo" in messages[2]


def test_render_rejects_ping_left_in_url() -> None:
    with pytest.raises(ValueError, match="@everyone"):
        render(_update(url="https://example.com/@everyone"))
