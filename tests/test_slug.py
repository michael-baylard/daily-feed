"""Exact slug and search-key strings."""

from __future__ import annotations

import re

import pytest

from daily_feed.slug import search_key, to_slug

_SNAKE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_DIGITS = re.compile(r"^[a-z0-9]+$")


def test_titles() -> None:
    assert to_slug("Spider-Man: No Way Home") == "spider_man_no_way_home"
    assert search_key("Spider-Man: No Way Home") == "spidermannowayhome"
    assert to_slug("DC Comics") == "dc_comics"
    assert search_key("DC Comics") == "dccomics"
    assert to_slug("Marvel") == "marvel"
    assert search_key("Marvel") == "marvel"
    assert to_slug("The Batman") == "the_batman"
    assert search_key("The Batman") == "thebatman"
    assert to_slug("Helldivers 2") == "helldivers_2"
    assert search_key("Helldivers 2") == "helldivers2"
    assert to_slug("The Last of Us") == "the_last_of_us"
    assert search_key("The Last of Us") == "thelastofus"
    assert to_slug("Mr. Robot") == "mr_robot"
    assert search_key("Mr. Robot") == "mrrobot"
    assert to_slug("Half-Life 2") == "half_life_2"
    assert search_key("Half-Life 2") == "halflife2"
    assert to_slug("Game 2: The Sequel") == "game_2_the_sequel"
    assert search_key("Game 2: The Sequel") == "game2thesequel"


def test_people_and_logins() -> None:
    assert to_slug("xQc") == "xqc"
    assert search_key("xQc") == "xqc"
    assert to_slug(" @Shroud") == "shroud"
    assert search_key(" @Shroud") == "shroud"
    assert to_slug("Pokimane") == "pokimane"
    assert search_key("Pokimane") == "pokimane"
    assert to_slug("O'Donnell") == "odonnell"
    assert search_key("O'Donnell") == "odonnell"
    assert to_slug("O\u2019Brien") == "obrien"
    assert search_key("O\u2019Brien") == "obrien"
    assert to_slug("  @xQc  ") == "xqc"
    assert search_key("  @xQc  ") == "xqc"


def test_ampersand_becomes_and() -> None:
    assert to_slug("Dungeons & Dragons") == "dungeons_and_dragons"
    assert search_key("Dungeons & Dragons") == "dungeonsanddragons"
    assert to_slug("D&D") == "d_and_d"
    assert search_key("D&D") == "dandd"
    assert to_slug("Tom & Jerry") == "tom_and_jerry"
    assert search_key("Tom & Jerry") == "tomandjerry"
    assert to_slug("AT&T") == "at_and_t"
    assert search_key("AT&T") == "atandt"
    assert to_slug("M&M's") == "m_and_ms"
    assert search_key("M&M's") == "mandms"
    assert to_slug("A & B") == "a_and_b"
    assert search_key("A & B") == "aandb"
    assert to_slug("&") == "and"
    assert search_key("&") == "and"
    assert to_slug("&&") == "and_and"
    assert search_key("&&") == "andand"


def test_apostrophes_drop() -> None:
    assert to_slug("Spider-Man\u2019s Home") == "spider_mans_home"
    assert search_key("Spider-Man\u2019s Home") == "spidermanshome"
    assert to_slug("Spider-Man's Home") == "spider_mans_home"
    assert search_key("Spider-Man's Home") == "spidermanshome"
    assert to_slug("Rock 'n' Roll") == "rock_n_roll"
    assert search_key("Rock 'n' Roll") == "rocknroll"
    assert to_slug("it's") == "its"
    assert search_key("it's") == "its"


def test_case_and_separators_collapse() -> None:
    assert to_slug("The Batman") == to_slug("the   batman") == to_slug("THE-BATMAN")
    assert search_key("The Batman") == search_key("the   batman") == search_key("THE-BATMAN")
    assert to_slug("the   batman") == "the_batman"
    assert search_key("the   batman") == "thebatman"
    assert to_slug("THE-BATMAN") == "the_batman"
    assert search_key("THE-BATMAN") == "thebatman"
    assert to_slug("  Marvel  ") == "marvel"
    assert to_slug("Spider--Man") == "spider_man"
    assert search_key("Spider--Man") == "spiderman"
    assert to_slug("!!Marvel!!") == "marvel"
    assert search_key("!!Marvel!!") == "marvel"
    assert to_slug("___hello___") == "hello"
    assert search_key("___hello___") == "hello"
    assert to_slug("C++") == "c"
    assert search_key("C++") == "c"
    assert to_slug("Player 1") == "player_1"
    assert search_key("Player 1") == "player1"


def test_non_ascii_is_stable_snake_case() -> None:
    slug = to_slug("Sh\u014dgun")
    assert slug == "sh_gun"
    assert slug == to_slug("Sh\u014dgun")
    assert to_slug("SH\u014cGUN") == "sh_gun"
    assert _SNAKE.fullmatch(slug)
    key = search_key("Sh\u014dgun")
    assert key == "shgun"
    assert key == search_key("Sh\u014dgun")
    assert key == slug.replace("_", "")
    assert "_" not in key
    assert _DIGITS.fullmatch(key)
    assert to_slug("Stra\u00dfe") == "strasse"
    assert search_key("Stra\u00dfe") == "strasse"


@pytest.mark.parametrize("name", ["  ", "!!!", "", "---", "'''", "   @   ", "..."])
def test_empty_slug_raises(name: str) -> None:
    with pytest.raises(ValueError):
        to_slug(name)


@pytest.mark.parametrize("name", ["  ", "!!!", "", "---", "'''", "   @   ", "..."])
def test_empty_search_key_raises(name: str) -> None:
    with pytest.raises(ValueError):
        search_key(name)


def test_search_key_is_slug_without_underscores() -> None:
    samples = (
        "Spider-Man: No Way Home",
        "DC Comics",
        "Marvel",
        "The Batman",
        "Helldivers 2",
        "Dungeons & Dragons",
        "Pokimane",
        "Sh\u014dgun",
        "xQc",
        " @Shroud",
    )
    for name in samples:
        slug = to_slug(name)
        key = search_key(name)
        assert key == slug.replace("_", "")
        assert _SNAKE.fullmatch(slug)
        assert _DIGITS.fullmatch(key)
        assert to_slug(slug) == slug
