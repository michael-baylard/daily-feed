"""Matrix coverage for run, state, order, hashing, post, and watchlist. No network."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from daily_feed.hashing import changed, content_hash
from daily_feed.models import Kind, Update, WatchItem, Watchlist
from daily_feed.order import sort_updates
from daily_feed.post import WEBHOOK_ENV, message_body, webhook_url
from daily_feed.run import collect, remember, worth_sending
from daily_feed.schedule import local_day
from daily_feed.state import empty_state, load_state, save_state
from daily_feed.watchlist import load_watchlist, save_watchlist

CHICAGO = ZoneInfo("America/Chicago")
AT_3PM = datetime(2026, 11, 19, 15, 0, tzinfo=CHICAGO)
BEFORE_3PM = datetime(2026, 11, 19, 14, 0, tzinfo=CHICAGO)


def _blank() -> dict:
    return empty_state()


def _update(
    *,
    slug: str = "item",
    published_at: datetime | None = None,
    url: str = "https://example.com/x",
    source: str = "page",
    title: str = "title",
    lines: tuple[str, ...] = ("line",),
) -> Update:
    when = published_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Update(
        slug=slug,
        kind=Kind.game,
        name=slug,
        title=title,
        published_at=when,
        url=url,
        lines=lines,
        source=source,
    )


def _tiny_steam(gid: str, stamp: int, title: str = "Patch") -> dict:
    return {
        "steam": {
            "appnews": {
                "newsitems": [
                    {
                        "gid": gid,
                        "title": title,
                        "url": f"https://example.com/{gid}",
                        "contents": "body",
                        "date": stamp,
                    }
                ]
            }
        }
    }


# --- hashing ---


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a",
        "hello",
        "café",
        "same bytes",
        "studio slate",
        "page\vwith\ttabs",
        "unicode—dash",
    ],
)
def test_matrix_content_hash_stable_sha256(text: str) -> None:
    first = content_hash(text)
    second = content_hash(text)
    assert first == second
    assert first == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(first) == 64


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (None, "fresh", True),
        ("not-a-hash", "fresh", True),
        ("deadbeef", "other", True),
    ],
)
def test_matrix_changed_true_when_old_missing_or_mismatch(
    old: str | None, new: str, expected: bool
) -> None:
    assert changed(old, new) is expected


@pytest.mark.parametrize("text", ["alpha", "beta", "gamma", "delta"])
def test_matrix_changed_false_when_hash_matches_text(text: str) -> None:
    assert changed(content_hash(text), text) is False


@pytest.mark.parametrize("text", ["one", "two", "three"])
def test_matrix_changed_true_when_text_differs_from_stored_hash(text: str) -> None:
    assert changed(content_hash(text), f"{text}-mutated") is True


# --- order ---


@pytest.mark.parametrize(
    ("slugs", "expected"),
    [
        (["b", "a"], ["a", "b"]),
        (["z", "m", "a"], ["a", "m", "z"]),
        (["solo"], ["solo"]),
    ],
)
def test_matrix_sort_equal_time_by_slug(slugs: list[str], expected: list[str]) -> None:
    when = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    updates = [_update(slug=slug, published_at=when) for slug in slugs]
    ordered = sort_updates(list(reversed(updates)))
    assert [u.slug for u in ordered] == expected


@pytest.mark.parametrize(
    ("urls", "expected"),
    [
        (["https://x.com/z", "https://x.com/a"], ["https://x.com/a", "https://x.com/z"]),
        (["https://b", "https://a", "https://c"], ["https://a", "https://b", "https://c"]),
    ],
)
def test_matrix_sort_equal_slug_by_url(urls: list[str], expected: list[str]) -> None:
    when = datetime(2026, 5, 2, 12, tzinfo=timezone.utc)
    updates = [_update(slug="tie", published_at=when, url=url) for url in urls]
    ordered = sort_updates(updates)
    assert [u.url for u in ordered] == expected


@pytest.mark.parametrize("count", [2, 3, 4])
def test_matrix_sort_preserves_input_list_identity(count: int) -> None:
    items = [
        _update(
            slug=f"s{i}",
            published_at=datetime(2026, 6, i, tzinfo=timezone.utc),
        )
        for i in range(count, 0, -1)
    ]
    original = list(items)
    ordered = sort_updates(items)
    assert items == original
    assert ordered is not items


# --- worth_sending ---


@pytest.mark.parametrize(
    ("source", "title", "lines", "expected"),
    [
        ("twitch", "", (), False),
        ("twitch", "   ", (), False),
        ("twitch", "Live now", (), True),
        ("countdown", "", (), False),
        ("countdown", "Trailer in 3 days", (), True),
        ("steam", "Patch", ("real line",), True),
        ("steam", "Patch", ("", "  "), False),
        ("page", "Name", (), False),
        ("tvmaze", "S1 E2", ("",), False),
        ("tvmaze", "S1 E2", ("Episode title",), True),
    ],
)
def test_matrix_worth_sending_by_source(
    source: str, title: str, lines: tuple[str, ...], expected: bool
) -> None:
    update = _update(source=source, title=title, lines=lines)
    assert worth_sending(update) is expected


# --- collect ---


@pytest.mark.parametrize("extra_slug", ["orphan", "ghost", "not-listed"])
def test_matrix_collect_drops_fetched_keys_not_on_watchlist(extra_slug: str) -> None:
    game = WatchItem(kind=Kind.game, name="Listed", slug="listed", steam_app_id=1)
    fetched = {
        "listed": _tiny_steam("1", 500, "Visible"),
        extra_slug: _tiny_steam("9", 900, "Hidden"),
    }
    updates = collect([game], fetched, _blank(), AT_3PM)
    assert [u.slug for u in updates] == ["listed"]


def test_matrix_collect_steam_empty_before_3pm_chicago() -> None:
    game = WatchItem(kind=Kind.game, name="Duet", slug="duet", steam_app_id=7)
    fetched = {"duet": _tiny_steam("g1", 1_700_000_000)}
    assert collect([game], fetched, _blank(), BEFORE_3PM) == []


def test_matrix_collect_steam_update_at_3pm_chicago() -> None:
    game = WatchItem(kind=Kind.game, name="Duet", slug="duet", steam_app_id=7)
    fetched = {"duet": _tiny_steam("g1", 1_700_000_000, "Hotfix")}
    updates = collect([game], fetched, _blank(), AT_3PM)
    assert len(updates) == 1
    assert updates[0].source == "steam"
    assert updates[0].title == "Hotfix"


def test_matrix_collect_steam_skipped_when_gid_already_seen() -> None:
    game = WatchItem(kind=Kind.game, name="Duet", slug="duet", steam_app_id=7)
    state = _blank()
    state["seen_ids"] = ["g1"]
    fetched = {"duet": _tiny_steam("g1", 1_700_000_000)}
    assert collect([game], fetched, state, AT_3PM) == []


def test_matrix_game_urls_page_update_at_3pm() -> None:
    game = WatchItem(
        kind=Kind.game,
        name="VI",
        slug="vi",
        urls=("https://example.com/vi",),
    )
    fetched = {"vi": {"page_text": "trailer drop", "page_url": "https://example.com/vi"}}
    updates = collect([game], fetched, _blank(), AT_3PM)
    assert len(updates) == 1
    assert updates[0].source == "page"
    assert updates[0].lines == ()


def test_matrix_game_urls_page_skipped_before_3pm() -> None:
    game = WatchItem(
        kind=Kind.game,
        name="VI",
        slug="vi",
        urls=("https://example.com/vi",),
    )
    fetched = {"vi": {"page_text": "trailer drop", "page_url": "https://example.com/vi"}}
    assert collect([game], fetched, _blank(), BEFORE_3PM) == []


def test_matrix_game_without_urls_ignores_page_text() -> None:
    game = WatchItem(kind=Kind.game, name="Plain", slug="plain")
    fetched = {"plain": {"page_text": "ignored", "page_url": "https://example.com/plain"}}
    assert collect([game], fetched, _blank(), AT_3PM) == []


# --- remember ---


def test_matrix_remember_stores_chicago_day_when_stamp_day_true() -> None:
    stored = remember(_blank(), [], {}, AT_3PM, stamp_day=True)
    assert stored["last_run_day"] == local_day(AT_3PM).isoformat()


def test_matrix_remember_keeps_previous_day_when_stamp_day_false() -> None:
    state = _blank() | {"last_run_day": "2026-11-18"}
    stored = remember(state, [], {}, AT_3PM, stamp_day=False)
    assert stored["last_run_day"] == "2026-11-18"


def test_matrix_remember_writes_page_hash() -> None:
    publisher = WatchItem(
        kind=Kind.publisher,
        name="Pub",
        slug="pub",
        urls=("https://example.com/pub",),
    )
    text = "press release"
    fetched = {"pub": {"page_text": text, "page_url": "https://example.com/pub"}}
    update = _update(slug="pub", source="page", title="Pub", lines=())
    stored = remember(_blank(), [update], fetched, AT_3PM)
    assert stored["hashes"]["pub"] == content_hash(text)


def test_matrix_remember_twitch_title_and_post_stamp() -> None:
    person = WatchItem(kind=Kind.person, name="Caster", slug="caster", twitch_login="caster")
    update = Update(
        slug="caster",
        kind=Kind.person,
        name="Caster",
        title="Caster",
        published_at=AT_3PM.astimezone(timezone.utc),
        url="https://www.twitch.tv/caster",
        lines=("Ranked grind",),
        source="twitch",
    )
    stored = remember(_blank(), [update], {"caster": {"twitch": {"title": "Ranked grind"}}}, AT_3PM)
    assert stored["twitch_titles"]["caster"] == "Ranked grind"
    assert stored["twitch_posts"]["caster"].startswith("2026-11-19")


def test_matrix_remember_steam_gids_at_or_before_posted_stamp() -> None:
    game = WatchItem(kind=Kind.game, name="Duet", slug="duet", steam_app_id=1)
    stamp = 2_000
    fetched = {
        "duet": {
            "steam": {
                "appnews": {
                    "newsitems": [
                        {"gid": "old", "date": 1_000, "url": "https://example.com/old"},
                        {"gid": "new", "date": stamp, "url": "https://example.com/new"},
                        {"gid": "future", "date": stamp + 500, "url": "https://example.com/future"},
                    ]
                }
            }
        }
    }
    update = Update(
        slug="duet",
        kind=Kind.game,
        name="Duet",
        title="New",
        published_at=datetime.fromtimestamp(stamp, tz=timezone.utc),
        url="https://example.com/new",
        lines=("body",),
        source="steam",
    )
    stored = remember(_blank(), [update], fetched, AT_3PM)
    assert stored["seen_ids"] == ["new", "old"]


def test_matrix_remember_does_not_mutate_input_state() -> None:
    state = _blank()
    state["seen_ids"] = ["keep"]
    before_hashes = dict(state["hashes"])
    remember(state, [], {}, AT_3PM)
    assert state["seen_ids"] == ["keep"]
    assert state["hashes"] == before_hashes


# --- state ---


def test_matrix_load_state_missing_file_matches_empty_shape(tmp_path) -> None:
    missing = tmp_path / "nowhere.json"
    assert load_state(missing) == empty_state()


def test_matrix_save_state_creates_parents_and_round_trips(tmp_path) -> None:
    path = tmp_path / "deep" / "state.json"
    payload = {
        "last_run_day": "2026-11-19",
        "hashes": {"a": "1", "b": "2"},
        "seen_ids": ["10", "20"],
        "twitch_titles": {"s1": "title"},
        "twitch_posts": {"s1": "2026-11-19T21:00:00+00:00"},
    }
    save_state(path, payload)
    assert path.is_file()
    assert load_state(path) == payload


@pytest.mark.parametrize(
    "last_run_day",
    [None, "", "2026-01-02"],
)
def test_matrix_save_state_normalizes_last_run_day(tmp_path, last_run_day) -> None:
    path = tmp_path / "state.json"
    save_state(path, _blank() | {"last_run_day": last_run_day})
    loaded = load_state(path)
    if last_run_day in (None, ""):
        assert loaded["last_run_day"] is None
    else:
        assert loaded["last_run_day"] == last_run_day


# --- post ---


def test_matrix_message_body_allowed_mentions_parse_empty() -> None:
    body = message_body("quiet post")
    assert body["content"] == "quiet post"
    assert body["allowed_mentions"] == {"parse": []}


@pytest.mark.parametrize(
    "ping",
    ["@everyone", "@here", "hi <@123>", "role <@&99>"],
)
def test_matrix_message_body_rejects_ping_markers(ping: str) -> None:
    with pytest.raises(ValueError):
        message_body(ping)


def test_matrix_webhook_url_reads_env_key() -> None:
    url = "https://discord.com/api/webhooks/9/secret"
    assert webhook_url({WEBHOOK_ENV: url}) == url
    assert webhook_url({WEBHOOK_ENV: f"  {url}  "}) == url


@pytest.mark.parametrize("env", [{}, {WEBHOOK_ENV: ""}, {WEBHOOK_ENV: "   "}])
def test_matrix_webhook_url_missing_raises_runtime_error(env: dict[str, str]) -> None:
    with pytest.raises(RuntimeError, match=WEBHOOK_ENV):
        webhook_url(env)


# --- watchlist ---


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("just a string\n", "watchlist must be a mapping"),
        ("items: not-a-list\n", "items must be a list"),
    ],
)
def test_matrix_load_watchlist_rejects_bad_root_shape(tmp_path, raw: str, match: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_watchlist(path)


@pytest.mark.parametrize(
    "item_yaml",
    [
        "  - kind: game\n    name: '   '\n",
        "  - kind: game\n",
        "  - name: NoKind\n",
    ],
)
def test_matrix_load_watchlist_rejects_missing_name_or_kind(tmp_path, item_yaml: str) -> None:
    path = tmp_path / "item.yaml"
    path.write_text(f"items:\n{item_yaml}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_watchlist(path)


@pytest.mark.parametrize(
    "bad_int",
    ["items:\n  - kind: game\n    name: G\n    steam_app_id: nope\n", "steam_app_id: true\n"],
)
def test_matrix_load_watchlist_rejects_bad_int(tmp_path, bad_int: str) -> None:
    path = tmp_path / "int.yaml"
    text = bad_int if bad_int.startswith("items:") else f"items:\n  - kind: game\n    name: G\n    {bad_int}"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="expected int"):
        load_watchlist(path)


def test_matrix_empty_yaml_file_is_empty_watchlist(tmp_path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_watchlist(path).items == []


def test_matrix_watchlist_dates_round_trip(tmp_path) -> None:
    item = WatchItem(
        Kind.movie,
        "Film",
        "film",
        urls=("https://example.com/film",),
        trailer_on=date(2026, 12, 1),
        releases_on=date(2026, 12, 15),
    )
    path = tmp_path / "film.yaml"
    save_watchlist(path, Watchlist(items=[item]))
    loaded = load_watchlist(path).items[0]
    assert loaded.trailer_on == date(2026, 12, 1)
    assert loaded.releases_on == date(2026, 12, 15)