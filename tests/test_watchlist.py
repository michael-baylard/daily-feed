"""YAML watchlist load and save. No network."""

from __future__ import annotations

from pathlib import Path

import pytest

from daily_feed.models import Kind, WatchItem, Watchlist
from daily_feed.slug import to_slug
from daily_feed.watchlist import load_watchlist, save_watchlist

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "watchlist.example.yaml"


def test_example_has_required_rows():
    watchlist = load_watchlist(EXAMPLE)
    by_name = {(item.kind, item.name): item for item in watchlist.items}
    game = by_name[Kind.game, "Helldivers 2"]
    assert game.steam_app_id == 553850
    assert any("store.steampowered.com" in url for url in game.urls)
    show = next(item for item in watchlist.items if item.kind is Kind.show)
    assert show.name
    assert show.tvmaze_id == 43031
    movie = by_name[Kind.movie, "Spider-Man: No Way Home"]
    assert any("marvel.com" in url for url in movie.urls)
    dc = by_name[Kind.publisher, "DC Comics"]
    assert "https://www.dc.com/blog" in dc.urls
    marvel = by_name[Kind.publisher, "Marvel"]
    assert "https://www.marvel.com/articles" in marvel.urls
    person = next(item for item in watchlist.items if item.kind is Kind.person)
    assert person.twitch_login == "lirik"
    assert person.twitch_login == person.twitch_login.lower()
    assert "https://www.twitch.tv/lirik" in person.urls


def test_example_omits_slug_and_load_fills_it():
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "slug:" not in text
    loaded = load_watchlist(EXAMPLE)
    assert loaded.items
    assert [item.slug for item in loaded.items] == [to_slug(item.name) for item in loaded.items]


def test_explicit_slug_kept(tmp_path: Path):
    path = tmp_path / "custom.yaml"
    path.write_text(
        "items:\n"
        "  - kind: game\n"
        "    name: Helldivers 2\n"
        "    slug: hd2\n"
        "    urls:\n"
        "      - https://store.steampowered.com/app/553850/Helldivers_2/\n"
        "    steam_app_id: 553850\n",
        encoding="utf-8",
    )
    item = load_watchlist(path).items[0]
    assert item.slug == "hd2"
    assert item.slug != to_slug(item.name)
    assert item.steam_app_id == 553850
    assert item.urls == ("https://store.steampowered.com/app/553850/Helldivers_2/",)


def test_round_trip_save_does_not_drop_urls(tmp_path: Path):
    loaded = load_watchlist(EXAMPLE)
    dest = tmp_path / "watchlist.yaml"
    save_watchlist(dest, loaded)
    again = load_watchlist(dest)
    assert [item.urls for item in again.items] == [item.urls for item in loaded.items]
    assert [item.slug for item in again.items] == [item.slug for item in loaded.items]
    assert [item.steam_app_id for item in again.items] == [
        item.steam_app_id for item in loaded.items
    ]
    assert [item.tvmaze_id for item in again.items] == [item.tvmaze_id for item in loaded.items]
    assert [item.twitch_login for item in again.items] == [
        item.twitch_login for item in loaded.items
    ]
    flat = [url for item in again.items for url in item.urls]
    assert "https://www.dc.com/blog" in flat
    assert "https://www.marvel.com/articles" in flat
    assert any("store.steampowered.com" in url for url in flat)
    assert any("spider-man-no-way-home" in url for url in flat)


def test_round_trip_keeps_custom_slug(tmp_path: Path):
    original = Watchlist(
        items=[
            WatchItem(
                Kind.game,
                "Helldivers 2",
                "hd2",
                urls=("https://store.steampowered.com/app/553850/Helldivers_2/",),
                steam_app_id=553850,
            )
        ]
    )
    path = tmp_path / "one.yaml"
    save_watchlist(path, original)
    loaded = load_watchlist(path).items[0]
    text = path.read_text(encoding="utf-8")
    assert loaded.slug == "hd2"
    assert loaded.urls == original.items[0].urls
    assert loaded.steam_app_id == 553850
    assert "https://store.steampowered.com/app/553850/Helldivers_2/" in text


def test_save_null_optionals_round_trip(tmp_path: Path):
    item = WatchItem(
        Kind.movie,
        "Dune",
        "dune",
        urls=("https://example.com/dune",),
    )
    path = tmp_path / "dune.yaml"
    save_watchlist(path, Watchlist(items=[item]))
    loaded = load_watchlist(path).items[0]
    assert loaded.kind is Kind.movie
    assert loaded.steam_app_id is None
    assert loaded.tvmaze_id is None
    assert loaded.twitch_login is None
    assert loaded.urls == ("https://example.com/dune",)


def test_bad_kind_raises(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "items:\n  - kind: podcast\n    name: Nope\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_watchlist(path)


def test_empty_document_is_empty_watchlist(tmp_path: Path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_watchlist(path).items == []


def test_load_strips_urls(tmp_path: Path):
    path = tmp_path / "urls.yaml"
    path.write_text(
        "items:\n"
        "  - kind: publisher\n"
        "    name: Marvel\n"
        "    urls:\n"
        "      - '  https://www.marvel.com/articles  '\n"
        "      - ''\n"
        "      - https://www.marvel.com\n",
        encoding="utf-8",
    )
    item = load_watchlist(path).items[0]
    assert item.urls == ("https://www.marvel.com/articles", "https://www.marvel.com")
    assert item.slug == to_slug("Marvel")
