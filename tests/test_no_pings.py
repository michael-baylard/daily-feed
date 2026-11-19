"""Ping marker detection and removal."""

from __future__ import annotations

import pytest

from daily_feed.safety import PING_MARKERS, assert_no_pings, find_pings, strip_pings


def test_ping_markers_are_the_four_discord_pings() -> None:
    assert PING_MARKERS == ("@everyone", "@here", "<@", "<@&")


def test_find_pings_everyone_is_case_insensitive() -> None:
    assert find_pings("hello @EVERYONE there") == ["@everyone"]
    assert find_pings("@Everyone") == ["@everyone"]


def test_find_pings_here_is_case_insensitive() -> None:
    assert find_pings("room @HERE") == ["@here"]
    assert find_pings("@Here") == ["@here"]


def test_find_pings_user_and_role_mentions() -> None:
    assert find_pings("user <@123>") == ["<@"]
    assert find_pings("role <@&123>") == ["<@", "<@&"]


def test_find_pings_reports_each_marker_once() -> None:
    text = "@everyone @EVERYONE @here <@1> <@&2>"
    assert find_pings(text) == ["@everyone", "@here", "<@", "<@&"]


def test_find_pings_empty_when_clean() -> None:
    assert find_pings("The Batman opens Friday.") == []


def test_assert_no_pings_raises_and_lists_markers() -> None:
    with pytest.raises(ValueError, match="@everyone") as exc:
        assert_no_pings("do not ping @everyone or @here")
    message = str(exc.value)
    assert "@here" in message
    assert "<@" not in message


def test_assert_no_pings_passes_when_clean() -> None:
    assert_no_pings("## The Batman\n**New trailer**\n-# page")


def test_strip_pings_removes_everyone_and_here_ignoring_case() -> None:
    assert strip_pings("a @EvErYoNe b @HERE c") == "a  b  c"


def test_strip_pings_removes_user_and_role_markers() -> None:
    assert strip_pings("user <@123> role <@&456>") == "user 123> role 456>"
    assert "<@" not in strip_pings("<@&123>")
    assert "<@&" not in strip_pings("<@&123>")


def test_strip_pings_leaves_clean_text() -> None:
    original = "Trailer drops Friday."
    assert strip_pings(original) == original
