"""Matrix coverage for slug cleanup and Discord ping safety (invariants + edge cases)."""

from __future__ import annotations

import re

import pytest

from daily_feed.safety import assert_no_pings, find_pings, strip_pings
from daily_feed.slug import search_key, to_slug

_SNAKE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_ALNUM_LOWER = re.compile(r"^[a-z0-9]+$")


def _slug_invariants(name: str) -> None:
    slug = to_slug(name)
    key = search_key(name)
    assert slug == slug.lower()
    assert _SNAKE.fullmatch(slug)
    assert "_" not in key
    assert key == slug.replace("_", "")
    assert _ALNUM_LOWER.fullmatch(key)
    assert search_key(name) == to_slug(name).replace("_", "")


@pytest.mark.parametrize(
    "name",
    [
        "Zelda",
        "Episode 42: Revenge",
        "foo/bar/baz",
        'Hello "World"',
        "Naïve Café",
        "a" * 120 + " trailer",
        "🔥Fire🔥",
        "Test___Multiple___Gaps",
        "  leading space",
        "trailing space  ",
        "MiXeD CaSe WoRdS",
        "semicolon;value",
        "back\\slash",
        "pipe|pipe",
        "question?mark",
        "exclamation!point",
        "percent%100",
        "plus+plus",
        "equals=sign",
        "hash#tag",
        "dollar$sign",
        "tilde~wave",
        "brackets[test]",
        "parens(test)",
        "tab\there",
        "café noir",
        "résumé builder",
        "100% pure",
        "v2.0.1 release",
        "3.14 pi",
        "x-y-z axis",
        "a.b.c dots",
        "Rock&Roll night",
        "Prince's album",
        "colon:split:twice",
        "slash/and\\combo",
        "double//slash",
        "abc123def",
        "0 lone digit",
        "9 lives",
        "A single letter",
        "__only__junk__!!!__",
        "word—emdash",
        "ellipsis…trail",
        "®registered",
        "under_score literal",
        "ALLCAPS TITLE",
        "snake_case_input",
        "Year 3000",
        "Part IV",
        "No. 5",
        "Q&A session",
        "C# language",
        "UTF-8 encoding",
        "Tom——Jerry",
    ],
)
def test_matrix_to_slug_and_search_key(name: str) -> None:
    _slug_invariants(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "\t\n",
        "!!!",
        "***",
        "---",
        "'''",
        "...",
        "   @   ",
        "Москва",
        "日本語",
        "한글",
        "🔥",
        "…",
        "<>",
    ],
)
def test_matrix_empty_slug_raises(name: str) -> None:
    with pytest.raises(ValueError, match="empty slug"):
        to_slug(name)
    with pytest.raises(ValueError, match="empty slug"):
        search_key(name)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", []),
        ("plain announcement", []),
        ("@everyone", ["@everyone"]),
        ("@EVERYONE", ["@everyone"]),
        ("@EvErYoNe", ["@everyone"]),
        ("@here", ["@here"]),
        ("@HERE", ["@here"]),
        ("@HeRe", ["@here"]),
        ("say <@999999>", ["<@"]),
        ("role <@&42>", ["<@", "<@&"]),
        ("glue@everyone", ["@everyone"]),
        ("prefix@here suffix", ["@here"]),
        ("@everyone and @HERE", ["@everyone", "@here"]),
        ("<@1> <@&2> blast", ["<@", "<@&"]),
        ("no mentions just text", []),
        ("angle @notping", []),
        ("literally <@& in prose", ["<@", "<@&"]),
        ("orphan <@", ["<@"]),
        ("@everyone@everyone", ["@everyone"]),
        ("mixed @Everyone @hErE <@7>", ["@everyone", "@here", "<@"]),
    ],
)
def test_matrix_find_pings(text: str, expected: list[str]) -> None:
    assert find_pings(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Release notes",
        "",
        "Trailer: Friday",
        "Discord markdown **bold**",
        "email user@example.com",
        "at sign alone @",
        "ampersand & partners",
    ],
)
def test_matrix_assert_no_pings_accepts_clean(text: str) -> None:
    assert find_pings(text) == []
    assert_no_pings(text)


@pytest.mark.parametrize(
    "text,marker",
    [
        ("ping @everyone now", "@everyone"),
        ("ROOM @HERE", "@here"),
        ("<@123456789>", "<@"),
        ("<@&987654>", "<@&"),
        ("dual @Everyone @here", "@everyone"),
        ("combo <@1> @HERE", "@here"),
    ],
)
def test_matrix_assert_no_pings_raises(text: str, marker: str) -> None:
    with pytest.raises(ValueError, match="ping markers") as exc:
        assert_no_pings(text)
    assert marker in str(exc.value)


@pytest.mark.parametrize(
    "text",
    [
        "Schedule update",
        "No pings in this line.",
        "## Heading\nBody copy.",
        "",
    ],
)
def test_matrix_strip_pings_idempotent_on_clean(text: str) -> None:
    assert strip_pings(text) == text
    assert find_pings(strip_pings(text)) == []


@pytest.mark.parametrize(
    "text",
    [
        "@everyone please watch",
        "GO @HERE team",
        "user <@555> joined",
        "role <@&777> ping",
        "a @EvErYoNe b @HERE c <@&1> d <@2>",
        "stuck@everyoneword",  # only literal @everyone substring
        "@everyone",
        "<@&only>",
    ],
)
def test_matrix_strip_pings_removes_all_markers(text: str) -> None:
    cleaned = strip_pings(text)
    assert find_pings(cleaned) == []
    assert "<@" not in cleaned
    assert "<@&" not in cleaned


def test_matrix_strip_pings_role_marker_before_user_prefix() -> None:
    raw = "mention <@&99> end"
    cleaned = strip_pings(raw)
    assert "<@&" not in cleaned
    assert "<@" not in cleaned
    assert "99>" in cleaned