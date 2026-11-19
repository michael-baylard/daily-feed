"""Matrix coverage for parse_request and merge_inbox. No network."""

from __future__ import annotations

from datetime import date

import pytest

from daily_feed.inbox import merge_inbox, parse_request
from daily_feed.models import Kind, WatchItem, Watchlist
from daily_feed.slug import to_slug

_KIND_ALIAS_EXPECTED = (
    ("game", Kind.game),
    ("show", Kind.show),
    ("movie", Kind.movie),
    ("publisher", Kind.publisher),
    ("person", Kind.person),
    ("streamer", Kind.person),
    ("tool", Kind.tool),
    ("ai", Kind.tool),
    ("harness", Kind.tool),
    ("athlete", Kind.athlete),
    ("player", Kind.athlete),
    ("league", Kind.league),
    ("nfl", Kind.league),
    ("match", Kind.match),
)


@pytest.mark.parametrize(("alias", "expected"), _KIND_ALIAS_EXPECTED)
def test_kind_alias_maps_to_expected_kind(alias: str, expected: Kind) -> None:
    items = parse_request(f"type: {alias}\nname: Matrix Item\n")
    assert len(items) == 1
    assert items[0].kind is expected
    assert items[0].slug == to_slug("Matrix Item")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\n\n  \t  \n",
        "---",
        "---\n---",
        " --- \n --- ",
    ],
)
def test_empty_or_rule_only_input_yields_no_items(text: str) -> None:
    assert parse_request(text) == []


def test_bom_stripped_before_parse() -> None:
    assert parse_request("\ufeff") == []
    items = parse_request("\ufefftype: game\nname: BOM Game\n")
    assert len(items) == 1
    assert items[0].kind is Kind.game
    assert items[0].name == "BOM Game"


def test_missing_type_with_name_raises() -> None:
    with pytest.raises(ValueError, match="missing type"):
        parse_request("name: Solo Name\nurl: https://example.com\n")


def test_missing_name_with_type_raises() -> None:
    with pytest.raises(ValueError, match="missing name"):
        parse_request("type: show\nurl: https://example.com/show\n")


@pytest.mark.parametrize("kind_label", ["podcast", "comic", "random"])
def test_unknown_type_raises(kind_label: str) -> None:
    with pytest.raises(ValueError, match="unknown type"):
        parse_request(f"type: {kind_label}\nname: Whatever\n")


@pytest.mark.parametrize(
    ("field", "body"),
    [
        ("steam_app_id", "type: game\nname: Hades\nsteam_app_id: twelve\n"),
        ("tvmaze_id", "type: show\nname: Lost\n tvmaze_id: 12.5\n".replace(" ", "")),
    ],
)
def test_optional_int_field_rejects_non_integer(field: str, body: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must be an int"):
        parse_request(body)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("trailer", "someday"),
        ("trailer", "2026-13-01"),
        ("releases", "March 4"),
        ("releases", "99-01-01"),
    ],
)
def test_date_fields_reject_invalid_iso(key: str, value: str) -> None:
    with pytest.raises(ValueError, match=f"{key} must be YYYY-MM-DD"):
        parse_request(f"type: movie\nname: Date Test\n{key}: {value}\n")


@pytest.mark.parametrize("key", ["trailer", "releases"])
def test_empty_date_field_is_none(key: str) -> None:
    items = parse_request(f"type: movie\nname: Dates\n{key}:\n")
    assert len(items) == 1
    assert getattr(items[0], f"{key}_on") is None


def test_valid_trailer_and_release_dates_parse() -> None:
    items = parse_request(
        "type: movie\n"
        "name: Scheduled\n"
        "trailer: 2027-01-15\n"
        "releases: 2027-06-30\n"
    )
    assert items[0].trailer_on == date(2027, 1, 15)
    assert items[0].releases_on == date(2027, 6, 30)


@pytest.mark.parametrize(
    ("twitch", "expected"),
    [
        ("@Cool_Login", to_slug("Cool_Login").replace("_", "")),
        ("MixedCase_Name", to_slug("MixedCase_Name").replace("_", "")),
        ("plain", to_slug("plain").replace("_", "")),
    ],
)
def test_twitch_login_normalized(twitch: str, expected: str) -> None:
    items = parse_request(f"type: person\nname: Host\ntwitch: {twitch}\n")
    login = items[0].twitch_login
    assert login == expected
    assert login is not None
    assert "@" not in login
    assert "_" not in login
    assert login == login.lower()


def test_multiple_url_lines_form_tuple_and_drop_blanks() -> None:
    items = parse_request(
        "type: publisher\n"
        "name: Many Links\n"
        "url:\n"
        "url: https://a.example\n"
        "url:  \n"
        "url: https://b.example\n"
    )
    assert items[0].urls == ("https://a.example", "https://b.example")


def test_hash_comment_lines_ignored_without_fields() -> None:
    assert parse_request("# just a comment\n# more noise\n") == []


def test_inline_comment_line_skipped_between_fields() -> None:
    items = parse_request("type: game\n# block comment\nname: Commented\n")
    assert len(items) == 1
    assert items[0].name == "Commented"
    assert items[0].kind is Kind.game


def test_blank_lines_around_fields_still_parse() -> None:
    items = parse_request("\n\n# header\n\ntype: tool\n\nname: After Comment\n\n")
    assert len(items) == 1
    assert items[0].name == "After Comment"
    assert items[0].kind is Kind.tool


def test_comment_only_record_produces_no_item() -> None:
    assert parse_request("# nothing here\n# also nothing\n") == []


def test_exact_rule_line_splits_records() -> None:
    text = (
        "type: game\nname: One\n---\n"
        "type: show\nname: Two\n---\n"
        "type: movie\nname: Three\n"
    )
    items = parse_request(text)
    assert [item.name for item in items] == ["One", "Two", "Three"]
    assert [item.kind for item in items] == [Kind.game, Kind.show, Kind.movie]


@pytest.mark.parametrize(
    "line",
    ["----", "---x", "x---", "---extra", "=== "],
)
def test_non_exact_rule_marker_does_not_split(line: str) -> None:
    body = f"type: movie\nname: Title {line}\n{line}\ntype: game\nname: Orphan\n"
    items = parse_request(body)
    assert len(items) == 1
    assert items[0].kind is Kind.movie
    assert items[0].name.startswith("Title")


def test_type_key_case_insensitive() -> None:
    items = parse_request("TYPE: GAME\nname: Caps\n")
    assert items[0].kind is Kind.game


def test_field_keys_case_insensitive() -> None:
    items = parse_request("TyPe: MoViE\nNaMe: Mixed Keys\nURL: https://example.com/m\n")
    assert items[0].kind is Kind.movie
    assert items[0].urls == ("https://example.com/m",)


def test_merge_appends_only_new_kind_slug_pairs() -> None:
    base = WatchItem(Kind.movie, "Alpha", "alpha")
    dup = WatchItem(Kind.movie, "Alpha duplicate", "alpha")
    fresh = WatchItem(Kind.show, "Beta", "beta")
    updated, added = merge_inbox(Watchlist(items=[base]), [dup, fresh, dup])
    assert added == [fresh]
    assert updated.items == [base, fresh]


def test_merge_preserves_existing_order_then_appends_new_in_order() -> None:
    first = WatchItem(Kind.game, "First", "first")
    second = WatchItem(Kind.game, "Second", "second")
    third = WatchItem(Kind.league, "Third", "third")
    fourth = WatchItem(Kind.match, "Fourth", "fourth")
    updated, added = merge_inbox(
        Watchlist(items=[first, second]),
        [second, third, fourth, third],
    )
    assert added == [third, fourth]
    assert [item.slug for item in updated.items] == ["first", "second", "third", "fourth"]


def test_merge_does_not_mutate_watchlist_or_incoming_lists() -> None:
    existing = WatchItem(Kind.publisher, "Stay", "stay")
    original_items = [existing]
    watchlist = Watchlist(items=original_items)
    newcomer = WatchItem(Kind.tool, "New", "new")
    incoming = [newcomer]
    updated, added = merge_inbox(watchlist, incoming)
    assert original_items == [existing]
    assert watchlist.items == [existing]
    assert incoming == [newcomer]
    assert added == [newcomer]
    assert updated.items == [existing, newcomer]
    assert updated is not watchlist


def test_merge_onto_empty_watchlist_adds_all_unique() -> None:
    a = WatchItem(Kind.athlete, "A", "a")
    b = WatchItem(Kind.athlete, "B", "b")
    updated, added = merge_inbox(Watchlist(items=[]), [a, b, a])
    assert added == [a, b]
    assert updated.items == [a, b]


def test_merge_same_slug_different_kind_keeps_both() -> None:
    pub = WatchItem(Kind.publisher, "Edge", "edge")
    game = WatchItem(Kind.game, "Edge", "edge")
    updated, added = merge_inbox(Watchlist(items=[pub]), [game])
    assert added == [game]
    assert [item.kind for item in updated.items] == [Kind.publisher, Kind.game]


def test_merge_with_no_new_items_returns_same_logical_rows() -> None:
    row = WatchItem(Kind.match, "Final", "final")
    watchlist = Watchlist(items=[row])
    updated, added = merge_inbox(watchlist, [])
    assert added == []
    assert updated.items == [row]


def test_optional_int_fields_accept_valid_values() -> None:
    game = parse_request("type: game\nname: Steamy\nsteam_app_id: 42\n")
    show = parse_request("type: show\nname: TV\n tvmaze_id: 7\n".replace(" ", ""))
    assert game[0].steam_app_id == 42
    assert show[0].tvmaze_id == 7


def test_whitespace_only_record_between_rules_ignored() -> None:
    items = parse_request("---\n   \n# noise\n---\ntype: tool\nname: Kept\n")
    assert len(items) == 1
    assert items[0].name == "Kept"