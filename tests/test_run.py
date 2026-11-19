"""Daily collect, render, state, and CLI. No network."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from daily_feed.cli import fetch_url, main
from daily_feed.hashing import content_hash
from daily_feed.models import Kind, Update, WatchItem
from daily_feed.run import collect, page_prompts, remember, render_day
from daily_feed.state import load_state, save_state

NOW = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)


def _blank() -> dict:
    return {"last_run_day": None, "hashes": {}, "seen_ids": [], "twitch_titles": {}}


def _steam(gid: str, stamp: int, title: str, url: str) -> dict:
    return {
        "steam": {
            "appnews": {
                "newsitems": [
                    {
                        "gid": gid,
                        "title": title,
                        "url": url,
                        "contents": "Patch line",
                        "date": stamp,
                    }
                ]
            }
        }
    }


def test_collect_ignores_slug_not_on_the_watchlist() -> None:
    game = WatchItem(kind=Kind.game, name="Hades", slug="hades", steam_app_id=1)
    fetched = {
        "hades": _steam("1", 100, "Visible", "https://example.com/visible"),
        "secret": _steam("2", 50, "Hidden", "https://example.com/hidden"),
    }
    updates = collect([game], fetched, _blank(), NOW)
    assert [item.slug for item in updates] == ["hades"]
    assert [item.title for item in updates] == ["Visible"]


def test_older_patch_posts_before_a_newer_one() -> None:
    older = WatchItem(kind=Kind.game, name="Old Game", slug="old_game", steam_app_id=1)
    newer = WatchItem(kind=Kind.game, name="New Game", slug="new_game", steam_app_id=2)
    fetched = {
        "new_game": _steam("n", 2_000, "New patch", "https://example.com/new"),
        "old_game": _steam("o", 1_000, "Old patch", "https://example.com/old"),
    }
    updates = collect([newer, older], fetched, _blank(), NOW)
    assert [item.title for item in updates] == ["Old patch", "New patch"]
    assert updates[0].published_at < updates[1].published_at


def test_render_day_output_has_no_everyone() -> None:
    update = Update(
        slug="hades",
        kind=Kind.game,
        name="Hades",
        title="Patch",
        published_at=NOW,
        url="https://example.com/hades",
        lines=("@everyone join the raid",),
        source="steam",
    )
    messages = render_day([update])
    assert len(messages) == 1
    assert "@everyone" not in messages[0].lower()
    assert "join the raid" in messages[0]


def test_render_day_keeps_the_sorted_order() -> None:
    older = Update(
        slug="old_game",
        kind=Kind.game,
        name="Old Game",
        title="Old patch",
        published_at=datetime.fromtimestamp(1_000, tz=timezone.utc),
        url="https://example.com/old",
        lines=("first",),
        source="steam",
    )
    newer = Update(
        slug="new_game",
        kind=Kind.game,
        name="New Game",
        title="New patch",
        published_at=datetime.fromtimestamp(2_000, tz=timezone.utc),
        url="https://example.com/new",
        lines=("second",),
        source="steam",
    )
    messages = render_day([older, newer])
    combined = "\n".join(messages)
    assert combined.index("Old patch") < combined.index("New patch")
    assert all("@everyone" not in message for message in messages)


def test_collect_person_uses_twitch_only() -> None:
    person = WatchItem(kind=Kind.person, name="Lirik", slug="lirik", twitch_login="lirik")
    fetched = {
        "lirik": {
            "page_text": "this page must not post",
            "page_url": "https://example.com/lirik",
            "twitch": None,
        }
    }
    assert collect([person], fetched, _blank(), NOW) == []
    fetched["lirik"]["twitch"] = {
        "user_login": "pokimane",
        "title": "nope",
        "started_at": "2026-11-19T21:00:00Z",
    }
    assert collect([person], fetched, _blank(), NOW) == []
    fetched["lirik"]["twitch"] = {
        "user_login": "Lirik",
        "title": "ranked",
        "started_at": "2026-11-19T21:00:00Z",
    }
    updates = collect([person], fetched, _blank(), NOW)
    assert [item.source for item in updates] == ["twitch"]
    assert updates[0].lines == ("ranked",)


def test_collect_movie_page_skips_when_hash_matches() -> None:
    movie = WatchItem(
        kind=Kind.movie,
        name="The Batman",
        slug="the_batman",
        urls=("https://example.com/batman",),
    )
    text = "same slate"
    fetched = {"the_batman": {"page_text": text, "page_url": "https://example.com/batman"}}
    state = _blank()
    state["hashes"] = {"the_batman": content_hash(text)}
    assert collect([movie], fetched, state, NOW) == []
    fresh = collect([movie], fetched, _blank(), NOW)
    assert len(fresh) == 1
    assert fresh[0].source == "page"
    assert fresh[0].lines == ()
    assert fresh[0].title == "The Batman"


def test_collect_game_page_text_is_not_a_page_update() -> None:
    game = WatchItem(kind=Kind.game, name="Hades", slug="hades")
    fetched = {"hades": {"page_text": "patch", "page_url": "https://example.com/hades"}}
    assert collect([game], fetched, _blank(), NOW) == []


def test_page_prompts_only_when_a_page_hash_changes() -> None:
    publisher = WatchItem(
        kind=Kind.publisher,
        name="Marvel",
        slug="marvel",
        urls=("https://www.marvel.com/articles",),
    )
    text = "New Marvel slate"
    fetched = {"marvel": {"page_text": text, "page_url": "https://www.marvel.com/articles"}}
    updates = collect([publisher], fetched, _blank(), NOW)
    prompts = page_prompts([publisher], updates, fetched)
    assert len(prompts) == 1
    assert "marvel" in prompts[0]
    assert text in prompts[0]
    assert "exactly 3 plain lines" in prompts[0]
    state = _blank()
    state["hashes"] = {"marvel": content_hash(text)}
    assert collect([publisher], fetched, state, NOW) == []
    assert page_prompts([publisher], [], fetched) == []


def test_steam_update_does_not_ask_for_a_model() -> None:
    game = WatchItem(kind=Kind.game, name="Hades", slug="hades", steam_app_id=1)
    fetched = {"hades": _steam("9", 100, "Patch 1.2", "https://example.com/hades")}
    updates = collect([game], fetched, _blank(), NOW)
    assert updates[0].source == "steam"
    assert updates[0].lines == ("Patch line",)
    assert page_prompts([game], updates, fetched) == []


def test_collect_show_uses_the_chicago_day() -> None:
    show = WatchItem(kind=Kind.show, name="Shogun", slug="shogun", tvmaze_id=43031)
    episode = {
        "name": "Tomorrow",
        "season": 1,
        "number": 2,
        "airdate": "2026-11-20",
        "url": "https://www.tvmaze.com/episodes/2",
    }
    fetched = {"shogun": {"episode": episode}}
    assert collect([show], fetched, _blank(), NOW) == []
    episode["airdate"] = "2026-11-19"
    updates = collect([show], fetched, _blank(), NOW)
    assert len(updates) == 1
    assert updates[0].source == "tvmaze"
    assert updates[0].title == "Season 1, Episode 2"
    assert page_prompts([show], updates, fetched) == []


def test_load_state_missing_file_is_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    state = load_state(missing)
    assert state == {
        "last_run_day": None,
        "hashes": {},
        "seen_ids": [],
        "twitch_titles": {},
    }
    state["hashes"]["x"] = "y"
    assert load_state(missing)["hashes"] == {}


def test_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    original = {
        "last_run_day": "2026-11-19",
        "hashes": {"dc_comics": "abc"},
        "seen_ids": ["9", "2"],
        "twitch_titles": {"lirik": "ranked"},
    }
    save_state(path, original)
    assert load_state(path) == original


def test_remember_records_the_day_without_reposting_old_gids() -> None:
    game = WatchItem(kind=Kind.game, name="Hades", slug="hades", steam_app_id=1)
    movie = WatchItem(
        kind=Kind.movie,
        name="The Batman",
        slug="the_batman",
        urls=("https://example.com/batman",),
    )
    person = WatchItem(kind=Kind.person, name="Lirik", slug="lirik", twitch_login="lirik")
    fetched = {
        "hades": {
            "steam": {
                "appnews": {
                    "newsitems": [
                        {
                            "gid": "old",
                            "title": "Old",
                            "url": "https://example.com/old",
                            "contents": "a",
                            "date": 100,
                        },
                        {
                            "gid": "new",
                            "title": "New",
                            "url": "https://example.com/new",
                            "contents": "b",
                            "date": 200,
                        },
                    ]
                }
            }
        },
        "the_batman": {"page_text": "slate", "page_url": "https://example.com/batman"},
        "lirik": {
            "twitch": {
                "user_login": "lirik",
                "title": "ranked",
                "started_at": "2026-11-19T21:00:00Z",
            }
        },
    }
    state = _blank()
    updates = collect([movie, person, game], fetched, state, NOW)
    stored = remember(state, updates, fetched, NOW)
    assert stored["last_run_day"] == "2026-11-19"
    assert stored["seen_ids"] == ["new", "old"]
    assert stored["hashes"]["the_batman"] == content_hash("slate")
    assert stored["twitch_titles"]["lirik"] == "ranked"
    assert state["seen_ids"] == []
    assert state["hashes"] == {}


def test_due_command_prints_no_before_3pm(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["due", "--now", "2026-11-19T14:00:00-06:00"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "no"


def test_due_command_prints_yes_at_3pm(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["due", "--now", "2026-11-19T15:00:00-06:00"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "yes"


def test_due_command_prints_no_when_today_already_ran(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "state.json"
    save_state(path, _blank() | {"last_run_day": "2026-11-19"})
    code = main(["due", "--now", "2026-11-19T16:00:00-06:00", "--state", str(path)])
    assert code == 0
    assert capsys.readouterr().out.strip() == "no"


def test_dry_run_prints_not_due(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    watchlist = tmp_path / "watch.yaml"
    watchlist.write_text("items: []\n", encoding="utf-8")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    state = tmp_path / "state.json"

    def boom(url: str) -> str:
        raise AssertionError(url)

    monkeypatch.setattr("daily_feed.cli.fetch_url", boom)
    code = main(
        [
            "run",
            "--watchlist",
            str(watchlist),
            "--state",
            str(state),
            "--inbox",
            str(inbox),
            "--dry-run",
            "--demo",
            "--now",
            "2026-11-19T14:00:00-06:00",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == "not due"
    assert not state.exists()


def test_dry_run_demo_prints_markdown_without_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    watchlist = tmp_path / "watch.yaml"
    watchlist.write_text(
        "items:\n"
        "  - kind: game\n"
        "    name: Hades\n"
        "    urls:\n"
        "      - https://store.steampowered.com/app/1145360/Hades/\n"
        "    steam_app_id: 1145360\n",
        encoding="utf-8",
    )
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "add.txt").write_text(
        "type: movie\nname: The Batman\nurl: https://www.dc.com/movies/the-batman\n",
        encoding="utf-8",
    )
    state = tmp_path / "state.json"
    before = watchlist.read_text(encoding="utf-8")

    def boom(url: str) -> str:
        raise AssertionError(url)

    monkeypatch.setattr("daily_feed.cli.fetch_url", boom)
    code = main(
        [
            "run",
            "--watchlist",
            str(watchlist),
            "--state",
            str(state),
            "--inbox",
            str(inbox),
            "--dry-run",
            "--demo",
            "--now",
            "2026-11-19T15:00:00-06:00",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "not due" not in out
    assert "Hades" in out
    assert "The Batman" in out
    assert "@everyone" not in out.lower()
    assert "-# steam" in out
    assert "-# page" in out
    assert out.index("Hades") < out.index("The Batman")
    assert watchlist.read_text(encoding="utf-8") == before
    assert not state.exists()


def test_fetch_url_raises_without_calling_the_network() -> None:
    with pytest.raises(NotImplementedError):
        fetch_url("https://example.com/page")


def test_live_run_raises_before_a_socket(tmp_path: Path) -> None:
    watchlist = tmp_path / "watch.yaml"
    watchlist.write_text(
        "items:\n"
        "  - kind: game\n"
        "    name: Hades\n"
        "    urls:\n"
        "      - https://store.steampowered.com/app/1145360/Hades/\n"
        "    steam_app_id: 1145360\n",
        encoding="utf-8",
    )
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    state = tmp_path / "state.json"
    with pytest.raises(NotImplementedError, match="fetch_url"):
        main(
            [
                "run",
                "--watchlist",
                str(watchlist),
                "--state",
                str(state),
                "--inbox",
                str(inbox),
                "--now",
                "2026-11-19T15:00:00-06:00",
            ]
        )
    assert not state.exists()


def test_demo_without_dry_run_does_not_post(tmp_path: Path) -> None:
    watchlist = tmp_path / "watch.yaml"
    watchlist.write_text(
        "items:\n  - kind: game\n    name: Hades\n    steam_app_id: 1145360\n",
        encoding="utf-8",
    )
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    state = tmp_path / "state.json"
    with pytest.raises(NotImplementedError, match="POST"):
        main(
            [
                "run",
                "--watchlist",
                str(watchlist),
                "--state",
                str(state),
                "--inbox",
                str(inbox),
                "--demo",
                "--now",
                "2026-11-19T15:00:00-06:00",
            ]
        )
    assert not state.exists()
    assert "The Batman" not in watchlist.read_text(encoding="utf-8")
