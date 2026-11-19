"""Matrix coverage for daily_feed.sources checkers. No HTTP."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from daily_feed.hashing import content_hash
from daily_feed.models import Kind, WatchItem
from daily_feed.sources import (
    countdown_update,
    page_update,
    steam_news_update,
    tvmaze_episode_update,
    twitch_update,
)

TODAY = date(2026, 11, 19)
PUBLISHED = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


def _steam_item(**overrides: object) -> WatchItem:
    base: dict[str, object] = {
        "kind": Kind.game,
        "name": "Matrix Game",
        "slug": "matrix-game",
        "steam_app_id": 999001,
    }
    base.update(overrides)
    return WatchItem(**base)  # type: ignore[arg-type]


def _movie(**overrides: object) -> WatchItem:
    base: dict[str, object] = {
        "kind": Kind.movie,
        "name": "Matrix Movie",
        "slug": "matrix-movie",
        "urls": ("https://example.com/matrix-movie",),
    }
    base.update(overrides)
    return WatchItem(**base)  # type: ignore[arg-type]


def _show(**overrides: object) -> WatchItem:
    base: dict[str, object] = {
        "kind": Kind.show,
        "name": "Matrix Show",
        "slug": "matrix-show",
        "tvmaze_id": 424242,
    }
    base.update(overrides)
    return WatchItem(**base)  # type: ignore[arg-type]


def _person(**overrides: object) -> WatchItem:
    base: dict[str, object] = {
        "kind": Kind.person,
        "name": "Matrix Streamer",
        "slug": "matrix-streamer",
        "twitch_login": "matrix_login",
    }
    base.update(overrides)
    return WatchItem(**base)  # type: ignore[arg-type]


def _news_row(
    gid: object,
    stamp: int,
    title: object = "Headline",
    url: object = "https://store.steampowered.com/news/x",
    contents: str = "Body",
) -> dict:
    return {
        "gid": gid,
        "title": title,
        "url": url,
        "contents": contents,
        "date": stamp,
    }


def _steam_payload(*rows: dict) -> dict:
    return {"appnews": {"newsitems": list(rows)}}


def test_matrix_steam_returns_none_without_steam_app_id() -> None:
    item = _steam_item(steam_app_id=None)
    payload = _steam_payload(_news_row("1", 10, "T"))
    assert steam_news_update(item, payload, set()) is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"appnews": None},
        {"appnews": {}},
        {"appnews": {"newsitems": None}},
        {"appnews": {"newsitems": []}},
        "not-a-dict",
    ],
    ids=["empty", "appnews_null", "appnews_empty", "newsitems_null", "newsitems_empty", "payload_string"],
)
def test_matrix_steam_empty_or_invalid_payload_returns_none(payload: object) -> None:
    assert steam_news_update(_steam_item(), payload, set()) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw_news",
    [
        ["plain-string", 42, None],
        [{"gid": "ok", "date": 5, "title": "Only dict", "url": "u", "contents": ""}],
    ],
    ids=["filters_non_dict_rows", "keeps_dict_row"],
)
def test_matrix_steam_newsitem_list_shapes(raw_news: list) -> None:
    payload = {"appnews": {"newsitems": raw_news}}
    update = steam_news_update(_steam_item(), payload, set())
    if raw_news[0] == "plain-string":
        assert update is None
    else:
        assert update is not None
        assert update.title == "Only dict"


@pytest.mark.parametrize(
    "row,seen",
    [
        (_news_row("", 100, "Skipped"), set()),
        ({"title": "No gid key", "date": 100, "url": "u", "contents": "b"}, set()),
        (_news_row("dup", 100, "Skipped"), {"dup"}),
        (_news_row("dup", 100, "Skipped"), {"dup", "other"}),
    ],
    ids=["empty_gid", "missing_gid_key", "gid_in_seen", "gid_in_seen_multi"],
)
def test_matrix_steam_skips_missing_or_seen_gid(row: dict, seen: set[str]) -> None:
    assert steam_news_update(_steam_item(), _steam_payload(row), seen) is None


def test_matrix_steam_none_gid_value_coerces_to_string_none_and_is_kept() -> None:
    """Absent default is skipped; explicit null becomes the literal gid ``None``."""
    row = _news_row(None, 100, "Kept")
    update = steam_news_update(_steam_item(), _steam_payload(row), set())
    assert update is not None
    assert update.title == "Kept"


@pytest.mark.parametrize(
    "stamps,expected_title",
    [
        ((50, 200), "Newer"),
        ((200, 50), "Older ignored"),
        ((100, 100, 150), "Last tied stamp wins"),
    ],
    ids=["picks_higher_stamp", "rejects_lower_stamp", "tie_breaks_forward"],
)
def test_matrix_steam_newest_by_date_wins(stamps: tuple[int, ...], expected_title: str) -> None:
    titles = ["A", "B", "C"]
    rows = [_news_row(str(i), stamp, titles[min(i, len(titles) - 1)]) for i, stamp in enumerate(stamps)]
    if len(stamps) == 2 and stamps[0] == 50:
        rows = [_news_row("low", 50, "Older ignored"), _news_row("high", 200, "Newer")]
        expected_title = "Newer"
    elif len(stamps) == 2 and stamps[0] == 200:
        rows = [_news_row("high", 200, "Keeps first"), _news_row("low", 50, "Older ignored")]
        expected_title = "Keeps first"
    elif len(stamps) == 3:
        rows = [
            _news_row("a", 100, "First"),
            _news_row("b", 100, "Second"),
            _news_row("c", 150, "Last tied stamp wins"),
        ]
        expected_title = "Last tied stamp wins"
    update = steam_news_update(_steam_item(), _steam_payload(*rows), set())
    assert update is not None
    assert update.title == expected_title


@pytest.mark.parametrize(
    "contents,expected_lines",
    [
        ("[b]Alpha[/b]", ("Alpha",)),
        ("[url=x]Beta[/url]\nGamma", ("Beta", "Gamma")),
        ("One\n\n\nTwo\n[skip]Three[/skip]\nFour\nFive", ("One", "Two", "Three")),
        ("  \n\t\nHello", ("Hello",)),
    ],
    ids=["strip_one_bracket", "strip_url_tag", "max_three_skip_blank", "leading_blanks"],
)
def test_matrix_steam_content_lines(contents: str, expected_lines: tuple[str, ...]) -> None:
    update = steam_news_update(
        _steam_item(),
        _steam_payload(_news_row("1", 1, "T", contents=contents)),
        set(),
    )
    assert update is not None
    assert update.lines == expected_lines
    assert len(update.lines) <= 3


@pytest.mark.parametrize(
    "title,url",
    [
        (None, None),
        ("", ""),
        (123, 456),
    ],
    ids=["none_fields", "empty_strings", "non_string_coerced"],
)
def test_matrix_steam_missing_title_and_url_become_empty_str(title: object, url: object) -> None:
    row = _news_row("1", 2, title=title, url=url)
    update = steam_news_update(_steam_item(), _steam_payload(row), set())
    assert update is not None
    assert update.title == (str(title) if title is not None else "")
    if title is None:
        assert update.title == ""
    if url is None:
        assert update.url == ""
    else:
        assert update.url == str(url)


@pytest.mark.parametrize(
    "airdate,today,expect",
    [
        ("2026-11-19", date(2026, 11, 19), True),
        ("2026-11-18", date(2026, 11, 19), False),
        ("2026-11-20", date(2026, 11, 19), False),
        ("", date(2026, 11, 19), False),
    ],
    ids=["matches_today", "yesterday", "tomorrow", "empty_airdate"],
)
def test_matrix_tvmaze_airdate_must_equal_today(airdate: str, today: date, expect: bool) -> None:
    episode = {"name": "Ep", "season": 1, "number": 2, "airdate": airdate, "url": "u"}
    update = tvmaze_episode_update(_show(), episode, today)
    assert (update is not None) is expect


def test_matrix_tvmaze_missing_tvmaze_id_returns_none() -> None:
    item = _show(tvmaze_id=None)
    episode = {"name": "Ep", "season": 1, "number": 1, "airdate": TODAY.isoformat(), "url": ""}
    assert tvmaze_episode_update(item, episode, TODAY) is None


@pytest.mark.parametrize(
    "episode",
    [None, [], "episode", 7],
    ids=["none", "list", "string", "int"],
)
def test_matrix_tvmaze_non_dict_episode_returns_none(episode: object) -> None:
    assert tvmaze_episode_update(_show(), episode, TODAY) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name,expected_lines",
    [
        ("Only Line", ("Only Line",)),
        ("  Spaced  ", ("  Spaced  ",)),
        ("", ()),
        ("   ", ()),
        (None, ()),
        (42, ()),
    ],
    ids=["name_line", "name_preserved_strip_check", "empty", "whitespace", "none_name", "non_string_name"],
)
def test_matrix_tvmaze_name_becomes_zero_or_one_line(name: object, expected_lines: tuple[str, ...]) -> None:
    episode = {"name": name, "season": 3, "number": 9, "airdate": TODAY.isoformat(), "url": "u"}
    update = tvmaze_episode_update(_show(), episode, TODAY)
    assert update is not None
    assert update.lines == expected_lines


@pytest.mark.parametrize(
    "season,number,expected_title",
    [
        (1, 1, "Season 1, Episode 1"),
        (12, 5, "Season 12, Episode 5"),
        (None, None, "Season None, Episode None"),
    ],
    ids=["s1e1", "s12e5", "missing_season_number_in_title"],
)
def test_matrix_tvmaze_title_season_episode_format(
    season: object, number: object, expected_title: str
) -> None:
    episode = {"name": "N", "season": season, "number": number, "airdate": TODAY.isoformat(), "url": ""}
    update = tvmaze_episode_update(_show(), episode, TODAY)
    assert update is not None
    assert update.title == expected_title


@pytest.mark.parametrize(
    "previous_hash,text",
    [
        (content_hash("stable"), "stable"),
        (content_hash("v1"), "v1"),
    ],
    ids=["same_hash", "same_hash_repeat"],
)
def test_matrix_page_unchanged_hash_returns_none(previous_hash: str, text: str) -> None:
    item = WatchItem(kind=Kind.publisher, name="Pub", slug="pub", urls=("https://x/",))
    assert page_update(item, text, previous_hash, item.urls[0], PUBLISHED) is None


@pytest.mark.parametrize(
    "previous_hash,text",
    [
        (None, "first fetch"),
        (None, ""),
        (content_hash("old"), "new body"),
    ],
    ids=["no_hash", "no_hash_empty_text", "hash_differs"],
)
def test_matrix_page_change_emits_update(previous_hash: str | None, text: str) -> None:
    item = WatchItem(kind=Kind.movie, name="Page Title", slug="page-title", urls=("https://y/",))
    update = page_update(item, text, previous_hash, item.urls[0], PUBLISHED)
    assert update is not None
    assert update.source == "page"
    assert update.title == item.name
    assert update.lines == ()
    assert update.url == item.urls[0]
    assert update.published_at == PUBLISHED


@pytest.mark.parametrize(
    "kind",
    [Kind.game, Kind.show, Kind.publisher, Kind.person, Kind.tool, Kind.athlete, Kind.league, Kind.match],
)
def test_matrix_countdown_non_movie_returns_none(kind: Kind) -> None:
    item = WatchItem(
        kind=kind,
        name="Not Movie",
        slug="not-movie",
        trailer_on=TODAY,
        releases_on=TODAY + timedelta(days=3),
    )
    assert countdown_update(item, TODAY) is None


@pytest.mark.parametrize(
    "offset,expected_title",
    [
        (8, None),
        (7, "Trailer in 7 days"),
        (1, "Trailer tomorrow"),
        (0, "Trailer today"),
        (-1, None),
    ],
    ids=["d_plus_8", "d_plus_7", "d_plus_1", "d_plus_0", "d_minus_1"],
)
def test_matrix_countdown_trailer_window_by_offset(offset: int, expected_title: str | None) -> None:
    event = TODAY + timedelta(days=offset)
    item = _movie(trailer_on=event)
    update = countdown_update(item, TODAY)
    if expected_title is None:
        assert update is None
    else:
        assert update is not None
        assert update.title == expected_title
        assert update.source == "countdown"


@pytest.mark.parametrize(
    "offset,expected_title",
    [
        (8, None),
        (7, "In theaters in 7 days"),
        (1, "In theaters tomorrow"),
        (0, "In theaters today"),
        (-1, None),
    ],
    ids=["rel_plus_8", "rel_plus_7", "rel_plus_1", "rel_plus_0", "rel_minus_1"],
)
def test_matrix_countdown_release_window_by_offset(offset: int, expected_title: str | None) -> None:
    event = TODAY + timedelta(days=offset)
    item = _movie(releases_on=event)
    update = countdown_update(item, TODAY)
    if expected_title is None:
        assert update is None
    else:
        assert update is not None
        assert update.title == expected_title


def test_matrix_countdown_both_dates_sooner_is_title_second_is_line() -> None:
    item = _movie(trailer_on=TODAY + timedelta(days=2), releases_on=TODAY + timedelta(days=5))
    update = countdown_update(item, TODAY)
    assert update is not None
    assert update.title == "Trailer in 2 days"
    assert update.lines == ("In theaters in 5 days",)
    assert update.title not in update.lines
    assert update.published_at == datetime(
        item.trailer_on.year, item.trailer_on.month, item.trailer_on.day, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "live",
    [None, "offline"],
    ids=["none", "non_dict_live"],
)
def test_matrix_twitch_offline_returns_none(live: object) -> None:
    if live == "offline":
        assert twitch_update(_person(), live, None) is None  # type: ignore[arg-type]
    else:
        assert twitch_update(_person(), live, "prev") is None


@pytest.mark.parametrize(
    "item_login,live_login",
    [
        ("matrix_login", "other"),
        ("foo", "bar"),
        ("", "matrix_login"),
    ],
    ids=["different_login", "unrelated_logins", "empty_item_login"],
)
def test_matrix_twitch_login_mismatch_returns_none(item_login: str, live_login: str) -> None:
    item = _person(twitch_login=item_login or None)
    live = {"user_login": live_login, "title": "Live", "started_at": "2026-11-19T10:00:00Z"}
    assert twitch_update(item, live, None) is None


@pytest.mark.parametrize(
    "previous_title,live_title",
    [
        ("Same", "Same"),
        (" Same ", "Same"),
        ("old", "  old  "),
    ],
    ids=["exact", "previous_padded", "live_padded"],
)
def test_matrix_twitch_same_title_returns_none(previous_title: str, live_title: str) -> None:
    live = {"user_login": "matrix_login", "title": live_title, "started_at": "2026-11-19T10:00:00Z"}
    assert twitch_update(_person(), live, previous_title) is None


@pytest.mark.parametrize(
    "started_at",
    ["", None, "not-a-timestamp", "2026-11-19T12:30:00Z"],
    ids=["empty", "none", "invalid", "valid_z"],
)
def test_matrix_twitch_missing_or_bad_started_at_does_not_raise(started_at: object) -> None:
    live = {"user_login": "matrix_login", "title": "Fresh title", "started_at": started_at}
    update = twitch_update(_person(), live, None)
    assert update is not None
    if started_at == "2026-11-19T12:30:00Z":
        assert update.published_at == datetime(2026, 11, 19, 12, 30, tzinfo=timezone.utc)
    else:
        assert update.published_at == datetime(1970, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "item_login,live_login",
    [
        ("Matrix_Login", "matrix_login"),
        ("MATRIX_LOGIN", "Matrix_Login"),
    ],
    ids=["item_mixed_live_lower", "item_upper_live_mixed"],
)
def test_matrix_twitch_matching_login_case_insensitive(item_login: str, live_login: str) -> None:
    item = _person(twitch_login=item_login)
    live = {"user_login": live_login, "title": "Live now", "started_at": "2026-11-19T08:00:00Z"}
    update = twitch_update(item, live, None)
    assert update is not None
    assert update.lines == ("Live now",)
    assert update.url == f"https://www.twitch.tv/{item_login}"


def test_matrix_twitch_lines_equal_title_and_url_from_item_login() -> None:
    item = _person(twitch_login="ItemCased")
    title = "Stream title"
    live = {"user_login": "itemcased", "title": title, "started_at": "2026-11-19T01:00:00+00:00"}
    update = twitch_update(item, live, "older")
    assert update is not None
    assert update.title == title
    assert update.lines == (title,)
    assert update.url == "https://www.twitch.tv/ItemCased"