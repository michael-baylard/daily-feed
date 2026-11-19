"""Checkers over already-fetched payloads. No HTTP."""

from __future__ import annotations

from datetime import date, datetime, timezone

from daily_feed.hashing import content_hash
from daily_feed.models import Kind, WatchItem
from daily_feed.sources import (
    countdown_update,
    page_update,
    steam_news_update,
    tvmaze_episode_update,
    twitch_update,
)


def _game(**overrides: object) -> WatchItem:
    fields: dict[str, object] = {
        "kind": Kind.game,
        "name": "Hades",
        "slug": "hades",
        "steam_app_id": 1145360,
    }
    fields.update(overrides)
    return WatchItem(**fields)  # type: ignore[arg-type]


def _news(gid: str, stamp: int, title: str, contents: str = "Line") -> dict:
    return {
        "gid": gid,
        "title": title,
        "url": f"https://store.steampowered.com/news/{gid}",
        "contents": contents,
        "date": stamp,
    }


def _payload(*items: dict) -> dict:
    return {"appnews": {"newsitems": list(items)}}


def test_steam_ignores_gid_already_seen() -> None:
    payload = _payload(_news("seen", 200, "Skipped"), _news("fresh", 100, "Kept"))
    update = steam_news_update(_game(), payload, {"seen"})
    assert update is not None
    assert update.title == "Kept"
    assert update.source == "steam"
    assert steam_news_update(_game(), _payload(_news("seen", 200, "Skipped")), {"seen"}) is None


def test_steam_ignores_item_without_steam_app_id() -> None:
    item = _game(steam_app_id=None)
    payload = _payload(_news("1", 100, "Patch"))
    assert steam_news_update(item, payload, set()) is None


def test_steam_picks_newest_unseen_gid() -> None:
    payload = _payload(_news("old", 100, "Old patch"), _news("new", 300, "New patch"))
    update = steam_news_update(_game(), payload, set())
    assert update is not None
    assert update.title == "New patch"
    assert update.published_at == datetime.fromtimestamp(300, tz=timezone.utc)
    assert update.url == "https://store.steampowered.com/news/new"


def test_steam_lines_drop_bracket_tags_and_keep_three() -> None:
    contents = "[b]One[/b]\n\n[url=https://example.com]Two[/url]\nThree\nFour"
    update = steam_news_update(_game(), _payload(_news("1", 50, "Patch", contents)), set())
    assert update is not None
    assert update.lines == ("One", "Two", "Three")


def test_tvmaze_returns_none_on_a_different_airdate() -> None:
    item = WatchItem(kind=Kind.show, name="Shogun", slug="shogun", tvmaze_id=43031)
    episode = {
        "name": "The Pilot",
        "season": 2,
        "number": 4,
        "airdate": "2026-11-18",
        "url": "https://www.tvmaze.com/episodes/1",
    }
    assert tvmaze_episode_update(item, episode, date(2026, 11, 19)) is None


def test_tvmaze_returns_update_on_todays_airdate() -> None:
    item = WatchItem(kind=Kind.show, name="Shogun", slug="shogun", tvmaze_id=43031)
    episode = {
        "name": "The Pilot",
        "season": 2,
        "number": 4,
        "airdate": "2026-11-19",
        "url": "https://www.tvmaze.com/episodes/1",
    }
    update = tvmaze_episode_update(item, episode, date(2026, 11, 19))
    assert update is not None
    assert update.title == "Season 2, Episode 4"
    assert update.lines == ("The Pilot",)
    assert update.source == "tvmaze"
    assert update.published_at == datetime(2026, 11, 19, tzinfo=timezone.utc)
    assert update.url == "https://www.tvmaze.com/episodes/1"


def test_tvmaze_returns_none_without_tvmaze_id() -> None:
    item = WatchItem(kind=Kind.show, name="Shogun", slug="shogun")
    episode = {
        "name": "The Pilot",
        "season": 2,
        "number": 4,
        "airdate": "2026-11-19",
        "url": "https://www.tvmaze.com/episodes/1",
    }
    assert tvmaze_episode_update(item, episode, date(2026, 11, 19)) is None


def test_tvmaze_omits_an_empty_episode_name() -> None:
    item = WatchItem(kind=Kind.show, name="Shogun", slug="shogun", tvmaze_id=1)
    episode = {"name": "  ", "season": 1, "number": 1, "airdate": "2026-11-19", "url": ""}
    update = tvmaze_episode_update(item, episode, date(2026, 11, 19))
    assert update is not None
    assert update.lines == ()


def test_page_update_returns_none_when_hash_matches() -> None:
    item = WatchItem(
        kind=Kind.publisher,
        name="DC Comics",
        slug="dc_comics",
        urls=("https://www.dc.com/blog",),
    )
    text = "same slate"
    when = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)
    assert page_update(item, text, content_hash(text), item.urls[0], when) is None


def test_page_update_emits_when_hash_changes() -> None:
    item = WatchItem(
        kind=Kind.movie,
        name="The Batman",
        slug="the_batman",
        urls=("https://example.com/batman",),
    )
    when = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)
    update = page_update(item, "new slate", None, item.urls[0], when)
    assert update is not None
    assert update.source == "page"
    assert update.title == "The Batman"
    assert update.lines == ()
    assert update.url == "https://example.com/batman"
    assert update.published_at == when


def test_twitch_returns_none_for_a_different_login() -> None:
    item = WatchItem(kind=Kind.person, name="Lirik", slug="lirik", twitch_login="lirik")
    live = {
        "user_login": "pokimane",
        "title": "not this channel",
        "started_at": "2026-11-19T21:05:00Z",
    }
    assert twitch_update(item, live, None) is None


def test_twitch_returns_none_when_offline() -> None:
    item = WatchItem(kind=Kind.person, name="Lirik", slug="lirik", twitch_login="lirik")
    assert twitch_update(item, None, None) is None
    assert twitch_update(item, None, "old title") is None


def test_twitch_returns_none_without_a_login() -> None:
    item = WatchItem(kind=Kind.person, name="Lirik", slug="lirik")
    live = {"user_login": "lirik", "title": "hi", "started_at": "2026-11-19T21:05:00Z"}
    assert twitch_update(item, live, None) is None


def test_twitch_skips_when_the_title_is_unchanged() -> None:
    item = WatchItem(kind=Kind.person, name="Lirik", slug="lirik", twitch_login="Lirik")
    live = {"user_login": "lirik", "title": "ranked", "started_at": "2026-11-19T21:05:00Z"}
    assert twitch_update(item, live, "ranked") is None


def test_twitch_missing_started_at_does_not_raise() -> None:
    item = WatchItem(kind=Kind.person, name="BurntPeanut", slug="burntpeanut", twitch_login="burntpeanut")
    live = {"user_login": "burntpeanut", "title": "ranked", "started_at": ""}
    update = twitch_update(item, live, None)
    assert update is not None
    assert update.published_at == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_twitch_posts_matching_login_with_started_at_utc() -> None:
    item = WatchItem(kind=Kind.person, name="Lirik", slug="lirik", twitch_login="Lirik")
    live = {"user_login": "lirik", "title": "ranked", "started_at": "2026-11-19T21:05:00Z"}
    update = twitch_update(item, live, None)
    assert update is not None
    assert update.source == "twitch"
    assert update.lines == ("ranked",)
    assert update.published_at == datetime(2026, 11, 19, 21, 5, tzinfo=timezone.utc)
    assert update.url == "https://www.twitch.tv/Lirik"


def test_countdown_starts_seven_days_out_and_stops_after() -> None:
    item = WatchItem(
        kind=Kind.movie,
        name="The Batman",
        slug="the_batman",
        urls=("https://example.com/the-batman",),
        trailer_on=date(2026, 11, 26),
    )
    early = countdown_update(item, date(2026, 11, 18))
    first = countdown_update(item, date(2026, 11, 19))
    day_of = countdown_update(item, date(2026, 11, 26))
    after = countdown_update(item, date(2026, 11, 27))
    assert early is None
    assert after is None
    assert first is not None and first.title == "Trailer in 7 days" and first.lines == ()
    assert day_of is not None and day_of.title == "Trailer today"
    assert first.source == "countdown"
    assert first.url == "https://example.com/the-batman"


def test_countdown_keeps_the_second_date_as_its_own_line() -> None:
    item = WatchItem(
        kind=Kind.movie,
        name="The Batman",
        slug="the_batman",
        urls=("https://example.com/the-batman",),
        trailer_on=date(2026, 11, 21),
        releases_on=date(2026, 11, 26),
    )
    update = countdown_update(item, date(2026, 11, 19))
    assert update is not None
    assert update.title == "Trailer in 2 days"
    assert update.lines == ("In theaters in 7 days",)
    assert update.title not in update.lines
