"""Friend form parser and watchlist merge. No network."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from daily_feed.inbox import merge_inbox, parse_request
from daily_feed.models import Kind, WatchItem, Watchlist
from daily_feed.slug import to_slug

FORM = Path(__file__).resolve().parents[1] / "inbox" / "FORM.txt"


def test_blank_text_returns_empty():
    assert parse_request("") == []
    assert parse_request("   \n\n") == []
    assert parse_request("---\n---\n") == []


def test_parse_movie():
    items = parse_request(
        "type: movie\n"
        "name: Spider-Man: No Way Home\n"
        "url: https://www.marvel.com/movies/spider-man-no-way-home\n"
    )
    assert len(items) == 1
    item = items[0]
    assert item.kind is Kind.movie
    assert item.name == "Spider-Man: No Way Home"
    assert item.slug == to_slug(item.name)
    assert item.urls == ("https://www.marvel.com/movies/spider-man-no-way-home",)
    assert item.steam_app_id is None
    assert item.twitch_login is None


def test_parse_movie_trailer_and_release_dates():
    items = parse_request(
        "type: movie\n"
        "name: The Batman\n"
        "url: https://example.com/the-batman\n"
        "trailer: 2026-11-26\n"
        "releases: 2026-12-18\n"
    )
    assert items[0].trailer_on == date(2026, 11, 26)
    assert items[0].releases_on == date(2026, 12, 18)


def test_bad_trailer_date_raises():
    with pytest.raises(ValueError, match="trailer"):
        parse_request("type: movie\nname: The Batman\ntrailer: next friday\n")


def test_parse_publisher():
    items = parse_request(
        "type: publisher\nname: DC Comics\nurl: https://www.dc.com/blog\n"
    )
    assert items[0].kind is Kind.publisher
    assert items[0].name == "DC Comics"
    assert items[0].slug == to_slug("DC Comics")
    assert items[0].urls == ("https://www.dc.com/blog",)


def test_streamer_alias_maps_to_person():
    items = parse_request(
        "type: streamer\nname: Lirik\ntwitch: lirik\nurl: https://www.twitch.tv/lirik\n"
    )
    assert len(items) == 1
    assert items[0].kind is Kind.person
    assert items[0].slug == to_slug("Lirik")
    assert items[0].twitch_login == to_slug("lirik").replace("_", "")
    assert items[0].urls == ("https://www.twitch.tv/lirik",)


def test_two_records_split_on_rule():
    text = (
        "type: movie\n"
        "name: Spider-Man: No Way Home\n"
        "url: https://www.marvel.com/movies/spider-man-no-way-home\n"
        "---\n"
        "type: publisher\n"
        "name: Marvel\n"
        "url: https://www.marvel.com/articles\n"
    )
    items = parse_request(text)
    assert [item.kind for item in items] == [Kind.movie, Kind.publisher]
    assert items[0].name == "Spider-Man: No Way Home"
    assert items[1].name == "Marvel"
    assert items[1].urls == ("https://www.marvel.com/articles",)


def test_only_exact_rule_splits_records():
    items = parse_request("type: movie\nname: Dune ---- Part Two\n----\ntype: game\nname: Hades\n")
    assert len(items) == 1
    assert items[0].name == "Dune ---- Part Two"


def test_at_sign_stripped_from_twitch_login():
    items = parse_request("type: person\nname: Name\ntwitch: @Name\n")
    login = items[0].twitch_login
    assert login == to_slug("Name").replace("_", "")
    assert login is not None
    assert "@" not in login
    assert login == login.lower()
    assert "_" not in login


def test_twitch_login_drops_underscores():
    items = parse_request("type: person\nname: Some Name\ntwitch: Some_Name\n")
    login = items[0].twitch_login
    assert login == to_slug("Some_Name").replace("_", "")
    assert login is not None
    assert "_" not in login
    assert login == login.lower()


def test_blank_urls_dropped_and_rest_stripped():
    items = parse_request(
        "type: movie\nname: Dune\nurl:\nurl:   https://example.com/dune  \nurl:   \n"
    )
    assert items[0].urls == ("https://example.com/dune",)


def test_repeated_urls_stay_in_order():
    items = parse_request(
        "type: publisher\n"
        "name: Marvel\n"
        "url: https://www.marvel.com/articles\n"
        "url: https://www.marvel.com\n"
    )
    assert items[0].urls == (
        "https://www.marvel.com/articles",
        "https://www.marvel.com",
    )


def test_optional_ids():
    items = parse_request(
        "type: game\nname: Helldivers 2\nsteam_app_id: 553850\n"
        "---\n"
        "type: show\nname: Shogun\ntvmaze_id: 43031\n"
    )
    assert items[0].kind is Kind.game
    assert items[0].steam_app_id == 553850
    assert items[0].tvmaze_id is None
    assert items[1].kind is Kind.show
    assert items[1].tvmaze_id == 43031
    assert items[1].steam_app_id is None


def test_unknown_type_raises():
    with pytest.raises(ValueError, match="unknown type"):
        parse_request("type: podcast\nname: Nope\n")


def test_missing_name_raises():
    with pytest.raises(ValueError, match="missing name"):
        parse_request("type: movie\nurl: https://example.com/dune\n")


def test_blank_template_is_skipped():
    assert parse_request("type:\nname:\nurl:\ntwitch:\n") == []


def test_missing_type_raises():
    with pytest.raises(ValueError, match="missing type"):
        parse_request("name: Dune\nurl: https://example.com/dune\n")


def test_bad_steam_app_id_raises():
    with pytest.raises(ValueError, match="steam_app_id"):
        parse_request("type: game\nname: Hades\nsteam_app_id: nope\n")


def test_duplicate_kind_and_slug_not_added_twice():
    current = WatchItem(
        Kind.publisher, "DC", "dc", urls=("https://www.dc.com/blog",)
    )
    duplicate = WatchItem(
        Kind.publisher, "DC", "dc", urls=("https://www.dc.com/comics",)
    )
    updated, added = merge_inbox(Watchlist(items=[current]), [duplicate, current])
    assert added == []
    assert updated.items == [current]


def test_same_slug_different_kind_both_stay():
    publisher = WatchItem(
        Kind.publisher, "DC", "dc", urls=("https://www.dc.com/blog",)
    )
    game = WatchItem(Kind.game, "DC", "dc", urls=("https://store.steampowered.com/app/1",))
    updated, added = merge_inbox(Watchlist(items=[publisher]), [publisher, game])
    assert added == [game]
    assert updated.items == [publisher, game]
    assert updated.items[0].kind is Kind.publisher
    assert updated.items[1].kind is Kind.game
    assert updated.items[0].slug == updated.items[1].slug == "dc"


def test_parsed_dc_publisher_and_game_both_stay():
    publisher = parse_request("type: publisher\nname: DC\nurl: https://www.dc.com/blog\n")
    game = parse_request("type: game\nname: DC\n")
    assert publisher[0].slug == game[0].slug
    updated, added = merge_inbox(Watchlist(items=publisher), [*publisher, *game])
    assert added == game
    assert [item.kind for item in updated.items] == [Kind.publisher, Kind.game]


def test_added_items_append_after_existing():
    movie = WatchItem(Kind.movie, "Dune", "dune")
    show = WatchItem(Kind.show, "Shogun", "shogun", tvmaze_id=43031)
    person = WatchItem(Kind.person, "Lirik", "lirik", twitch_login="lirik")
    updated, added = merge_inbox(Watchlist(items=[movie]), [show, person, show])
    assert added == [show, person]
    assert updated.items == [movie, show, person]


def test_merge_does_not_mutate_caller_list():
    publisher = WatchItem(Kind.publisher, "DC", "dc")
    original = [publisher]
    watchlist = Watchlist(items=original)
    game = WatchItem(Kind.game, "DC", "dc")
    incoming = [game]
    updated, added = merge_inbox(watchlist, incoming)
    assert original == [publisher]
    assert watchlist.items == [publisher]
    assert incoming == [game]
    assert added == [game]
    assert updated.items == [publisher, game]
    assert updated is not watchlist


def test_form_states_types_and_pickup_time():
    text = FORM.read_text(encoding="utf-8")
    assert "A new row is picked up on the next 3pm America/Chicago run." in text
    assert "type: streamer" in text
    assert "BurntPeanut" in text
    assert "type: league" in text
    assert "NFL" in text
    assert "tool" in text
    assert "\n---\n" in text
    _example, template = text.split("\n---\n", 1)
    assert "type:" in template
    assert "name:" in template
