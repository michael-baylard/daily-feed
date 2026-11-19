"""Matrix coverage for daily_feed.discord_md.render — not the Batman snapshot."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daily_feed.discord_md import KIND_EMOJI, render
from daily_feed.models import Kind, Update

_CHICAGO = timezone.utc  # tests only need tz-aware; UTC is fine
_PUBLISHED = datetime(2026, 6, 15, 20, 0, tzinfo=_CHICAGO)
_URL = "https://example.com/watch/slug"

_ALL_KINDS = list(Kind)
_PING_URL_CASES = [
    "https://evil.test/@everyone",
    "https://evil.test/@HERE",
    "https://evil.test/user<@123>",
    "https://evil.test/role<@&99>",
]
_TITLE_FILLER_CASES = [
    ("Acme", "Acme", "Acme"),
    ("Acme", "ACME", "acme"),
    ("Acme", "acme update", "ACME UPDATE"),
    ("Acme", "Acme Is Live", "acme is live"),
    ("BurntPeanut", "burntpeanut update", "BurntPeanut UPDATE"),
]


def _update(**overrides: object) -> Update:
    data: dict[str, object] = {
        "slug": "matrix-slug",
        "kind": Kind.game,
        "name": "Matrix Name",
        "title": "Distinct headline",
        "published_at": _PUBLISHED,
        "url": _URL,
        "lines": ("First fact.", "Second fact."),
        "source": "rss",
    }
    data.update(overrides)
    return Update(**data)  # type: ignore[arg-type]


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _header(text: str) -> str:
    return _lines(text)[0]


def _assert_no_dash_hash_source_line(text: str) -> None:
    assert not any(line.startswith("-#") for line in _lines(text))


# --- Kind emoji (KIND_EMOJI), twitch override ---


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_matrix_kind_emoji_on_first_line_non_twitch(kind: Kind) -> None:
    text = render(_update(kind=kind, source="page", lines=()))
    assert _header(text).startswith(f"{KIND_EMOJI[kind]} ")


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_matrix_twitch_source_uses_red_circle_not_kind_emoji(kind: Kind) -> None:
    text = render(
        _update(
            kind=kind,
            name="Streamer",
            title="Streamer is live",
            source="twitch",
            url="https://www.twitch.tv/streamer",
            lines=(),
        )
    )
    assert _header(text).startswith("🔴 ")
    assert not _header(text).startswith(f"{KIND_EMOJI[kind]} ")


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_matrix_non_twitch_does_not_use_red_circle(kind: Kind) -> None:
    text = render(_update(kind=kind, source="steam", lines=()))
    assert not _header(text).startswith("🔴 ")


# --- Source tag on header, empty source ---


@pytest.mark.parametrize(
    "source",
    ["page", "rss", "steam", "tvmaze", "imdb"],
)
def test_matrix_source_tag_appended_on_name_line(source: str) -> None:
    text = render(_update(source=source, lines=()))
    assert _header(text).endswith(f" - #{source}")
    _assert_no_dash_hash_source_line(text)


def test_matrix_empty_source_omits_tag() -> None:
    text = render(_update(source="", lines=()))
    assert " - #" not in _header(text)
    assert _header(text) == f"🎮 Matrix Name"
    _assert_no_dash_hash_source_line(text)


def test_matrix_whitespace_only_source_after_strip_behaves_like_empty() -> None:
    text = render(_update(source="  ", lines=()))
    assert " - #" not in _header(text)


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_matrix_no_line_starts_with_dash_hash(kind: Kind) -> None:
    text = render(_update(kind=kind, source="feed", lines=("a", "b")))
    _assert_no_dash_hash_source_line(text)


# --- Title differs: name plain on header, title is link ---


def test_matrix_distinct_title_name_not_inside_link() -> None:
    text = render(_update(name="Show Title", title="Episode guide", lines=()))
    header, link_line = _lines(text)[:2]
    assert "Show Title" in header
    assert "Show Title" not in link_line
    assert link_line == f"**[Episode guide]({_URL})**"


def test_matrix_distinct_title_link_contains_url() -> None:
    url = "https://cdn.example/game/patch"
    text = render(_update(title="Patch notes", url=url, lines=()))
    assert f"**[Patch notes]({url})**" in _lines(text)


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_matrix_distinct_title_two_line_minimum(kind: Kind) -> None:
    text = render(_update(kind=kind, lines=()))
    assert len(_lines(text)) >= 2
    assert _lines(text)[1].startswith("**[")


# --- Title repeats name / filler: name is link, no title line ---


@pytest.mark.parametrize(
    "name,title",
    [
        ("Zelda", "Zelda"),
        ("Zelda", "zelda"),
        ("Zelda", "ZELDA"),
    ],
)
def test_matrix_title_equals_name_name_is_only_link(name: str, title: str) -> None:
    text = render(_update(name=name, title=title, lines=()))
    assert _lines(text) == [f"🎮 **[{name.replace('[', '').replace(']', '')}]({_URL})** - #rss"]


@pytest.mark.parametrize("name,title,title_variant", _TITLE_FILLER_CASES)
def test_matrix_filler_titles_link_name_single_header_line(
    name: str, title: str, title_variant: str
) -> None:
    for t in (title, title_variant):
        text = render(_update(name=name, title=t, lines=()))
        assert len(_lines(text)) == 1
        assert f"**[{name}]({_URL})**" in _header(text)


def test_matrix_name_is_live_filler_drops_matching_bullet() -> None:
    text = render(
        _update(
            name="Caster",
            title="Caster is live",
            lines=("Caster is live", "Now playing Valorant."),
        )
    )
    body = _lines(text)
    assert len(body) == 2
    assert "- Now playing Valorant." in body
    assert not any("Caster is live" == line.lstrip("- ").strip() for line in body[1:])


def test_matrix_name_update_filler_drops_matching_bullet() -> None:
    text = render(
        _update(
            name="Tool",
            title="Tool update",
            lines=("Tool update", "Version 2 shipped."),
        )
    )
    assert "- Version 2 shipped." in _lines(text)
    assert "- Tool update" not in _lines(text)


# --- Bullet dedup ---


def test_matrix_drops_bullet_equal_to_name() -> None:
    text = render(_update(name="Dup", title="Headline", lines=("Dup", "keep")))
    assert "- keep" in _lines(text)
    assert "- Dup" not in _lines(text)


def test_matrix_drops_bullet_equal_to_title() -> None:
    text = render(_update(title="Headline", lines=("Headline", "keep")))
    assert "- keep" in _lines(text)
    assert "- Headline" not in _lines(text)


def test_matrix_drops_bullet_case_insensitive_match_name() -> None:
    text = render(_update(name="Mix", title="Other", lines=("mix",)))
    assert not any(line.startswith("- ") for line in _lines(text))


def test_matrix_drops_bullet_matching_filler_phrase_on_name() -> None:
    text = render(
        _update(
            name="Hero",
            title="Breaking",
            lines=("hero update", "Stats reset."),
        )
    )
    assert "- Stats reset." in _lines(text)
    assert "- hero update" not in _lines(text)


def test_matrix_empty_lines_after_strip_removed() -> None:
    text = render(_update(lines=("   ", "real")))
    assert "- real" in _lines(text)
    assert sum(1 for line in _lines(text) if line.startswith("- ")) == 1


# --- Ping stripping ---


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Safe @everyone Name"),
        ("title", "Safe @HERE Title"),
        ("source", "src <@123>"),
    ],
)
def test_matrix_strips_pings_from_header_fields(field: str, value: str) -> None:
    text = render(_update(**{field: value}, lines=()))  # type: ignore[arg-type]
    assert "@everyone" not in text.lower() or field == "title"
    assert "@here" not in text.lower() or field != "name"
    assert "<@" not in text
    assert "<@&" not in text


def test_matrix_strips_ping_from_line_keeps_remainder() -> None:
    text = render(_update(lines=("brief @HERE tail",)))
    assert any(line.startswith("- brief") and "tail" in line for line in _lines(text))
    assert "<@" not in text
    assert "@here" not in text.lower()


def test_matrix_strips_everyone_from_name_on_header() -> None:
    text = render(_update(kind=Kind.movie, name="Film @everyone", lines=()))
    assert _header(text).startswith("🎬")
    assert "Film" in _header(text)
    assert "@everyone" not in text.lower()


def test_matrix_strips_here_from_title_in_link() -> None:
    text = render(_update(title="Drop @HERE", lines=()))
    assert "**[Drop]({})**".format(_URL) in text
    assert "@here" not in text.lower()


@pytest.mark.parametrize("url", _PING_URL_CASES)
def test_matrix_url_with_ping_raises_value_error(url: str) -> None:
    with pytest.raises(ValueError, match="ping"):
        render(_update(url=url))


# --- Brackets in link label ---


def test_matrix_strips_square_brackets_from_name_in_link() -> None:
    text = render(_update(name="A [beta] build", title="A [beta] build", lines=()))
    assert f"**[A beta build]({_URL})**" in text
    assert "[beta]" not in text.split("](")[0]


def test_matrix_strips_square_brackets_from_title_in_link() -> None:
    text = render(_update(title="Patch [v1.2]", lines=()))
    assert "**[Patch v1.2]({})**".format(_URL) in text


def test_matrix_nested_brackets_removed_in_label() -> None:
    text = render(_update(title="[[warn]]", lines=()))
    assert "**[warn]({})**".format(_URL) in text


# --- Shape / hygiene ---


def test_matrix_no_open_kind_line() -> None:
    text = render(_update(kind=Kind.movie, lines=()))
    assert "Open movie" not in text
    assert "Open " not in text


def test_matrix_no_trailing_spaces_on_any_line() -> None:
    text = render(
        _update(
            name="N ",
            title="T ",
            lines=("x ",),
            source="s ",
        )
    )
    assert all(not line.endswith(" ") for line in _lines(text))


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_matrix_published_at_tz_aware_in_model_only(kind: Kind) -> None:
    ts = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)
    u = _update(kind=kind, published_at=ts)
    assert u.published_at.tzinfo is not None
    text = render(u)
    assert _header(text).startswith(KIND_EMOJI[kind])


def test_matrix_twitch_header_shape_name_linked() -> None:
    url = "https://www.twitch.tv/nick"
    text = render(
        _update(
            kind=Kind.person,
            name="Nick",
            title="nick is live",
            source="twitch",
            url=url,
            lines=(),
        )
    )
    assert text == f"🔴 **[Nick]({url})** - #twitch"


def test_matrix_source_tag_not_separate_bullet_with_lines() -> None:
    text = render(_update(source="imdb", lines=("Fact.",)))
    assert _lines(text)[0].endswith(" - #imdb")
    assert _lines(text)[1].startswith("**[")
    assert _lines(text)[2] == "- Fact."