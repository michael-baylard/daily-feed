"""Which NFL stories stay, and which repeats drop."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from daily_feed.models import Kind, Update, WatchItem
from daily_feed.run import collect
from daily_feed.select import dedupe, relevant

NOW = datetime(2026, 11, 19, 21, tzinfo=timezone.utc)


def _nfl(**overrides: object) -> Update:
    data: dict[str, object] = {
        "slug": "nfl",
        "kind": Kind.league,
        "name": "NFL",
        "title": "Story",
        "published_at": NOW,
        "url": "https://www.espn.com/nfl/story/1",
        "lines": ("A sentence.",),
        "source": "nfl",
    }
    data.update(overrides)
    return Update(**data)  # type: ignore[arg-type]


def test_gta_v_is_dropped_and_gta_vi_stays() -> None:
    online = _nfl(
        slug="gta_online",
        kind=Kind.game,
        name="Grand Theft Auto Online",
        title="Take Down the Kortz Center",
        source="steam",
        url="https://store.steampowered.com/news/271590",
    )
    six = _nfl(
        slug="gta_vi",
        kind=Kind.game,
        name="Grand Theft Auto VI",
        title="Grand Theft Auto VI Now Available",
        source="newswire",
        url="https://www.rockstargames.com/newswire/article/vi",
    )
    assert not relevant(online)
    assert relevant(six)
    assert not relevant(_nfl(title="GTA V gets one last coat of paint", source="newswire"))
    assert relevant(_nfl(title="Red Dead Online bonus week", name="Rockstar Games", source="newswire"))


def test_bears_stay_and_a_highlights_package_goes() -> None:
    bears = _nfl(title="Bears' Williams throws four", focus="bears", url="https://www.espn.com/nfl/story/bears")
    highlights = _nfl(title="Colts-Texans highlights", url="https://www.espn.com/nfl/story/highlights")
    hippo = _nfl(title="Fiona the hippo visits the Bengals", url="https://www.espn.com/nfl/story/hippo")
    college = _nfl(
        title="Heisman favorite stays put",
        url="https://www.espn.com/college-football/story/heisman",
        lines=("College football rankings moved.",),
    )
    assert relevant(bears)
    assert not relevant(highlights)
    assert relevant(hippo)
    assert not relevant(college)


def test_dedupe_drops_a_second_writeup_of_one_suspension() -> None:
    main = _nfl(
        title="Rams WR Puka Nacua to serve 3-game suspension while on IR",
        url="https://www.espn.com/nfl/story/_/id/50533560/rams-wr-puka-nacua-serve-3-game-suspension-ir",
    )
    follow = _nfl(
        title="Yates on Nacua's suspension timing",
        url="https://www.espn.com/nfl/story/yates",
    )
    kept = dedupe([main, follow])
    assert len(kept) == 1


def test_a_new_link_to_a_remembered_suspension_is_not_a_new_story(monkeypatch) -> None:
    monkeypatch.setattr("daily_feed.run.describe", lambda *args, **kwargs: ("Still suspended.",))
    item = WatchItem(kind=Kind.league, name="NFL", slug="nfl")
    fetched = {
        "nfl": {
            "article_source": "nfl",
            "articles": [
                {
                    "title": "Yates on Nacua's suspension timing",
                    "url": "https://www.espn.com/nfl/story/yates",
                    "text": "The suspension timing raised questions.",
                    "published_at": NOW,
                    "focus": "bears",
                }
            ],
        }
    }
    state = {
        "seen_ids": [
            "https://www.espn.com/nfl/story/_/id/50533560/rams-wr-puka-nacua-serve-3-game-suspension-ir"
        ]
    }
    assert collect([item], fetched, state, NOW, since=NOW - timedelta(days=7)) == []


def test_dedupe_drops_the_same_game_twice() -> None:
    preview = _nfl(title="Colts vs Texans preview", url="http://www.espn.com/nfl/preview?gameId=1")
    plays = _nfl(
        title="Colts and Texans best plays",
        url="https://www.espn.com/nfl/story/plays",
        lines=("A longer recap of the same night.",),
    )
    kept = dedupe([preview, plays])
    assert len(kept) == 1
    assert kept[0].url.endswith("/plays")


def test_collect_drops_routine_nfl_before_a_card(monkeypatch) -> None:
    monkeypatch.setattr("daily_feed.run.describe", lambda *args, **kwargs: ("A dry line.",))
    item = WatchItem(kind=Kind.league, name="NFL", slug="nfl")
    fetched = {
        "nfl": {
            "article_source": "nfl",
            "articles": [
                {
                    "title": "Bears' Williams throws four touchdowns",
                    "url": "https://www.espn.com/nfl/story/bears",
                    "text": "Caleb Williams threw four scores.",
                    "published_at": NOW,
                    "focus": "bears",
                },
                {
                    "title": "Colts-Texans highlights",
                    "url": "https://www.espn.com/nfl/story/highlights",
                    "text": "Best plays from Thursday night.",
                    "published_at": NOW,
                },
                {
                    "title": "Fiona the hippo visits the Bengals",
                    "url": "https://www.espn.com/nfl/story/hippo",
                    "text": "The hippo stopped by the stadium.",
                    "published_at": NOW,
                },
            ],
        }
    }
    updates = collect([item], fetched, {}, NOW, since=NOW - timedelta(days=7))
    assert [update.title for update in updates] == [
        "Bears' Williams throws four touchdowns",
        "Fiona the hippo visits the Bengals",
    ]


def test_repost_opens_the_day_that_already_ran(monkeypatch) -> None:
    monkeypatch.setattr("daily_feed.run.describe", lambda *args, **kwargs: ("A dry line.",))
    item = WatchItem(kind=Kind.league, name="NFL", slug="nfl")
    fetched = {
        "nfl": {
            "article_source": "nfl",
            "articles": [
                {
                    "title": "Bears' Williams throws four touchdowns",
                    "url": "https://www.espn.com/nfl/story/bears",
                    "text": "Caleb Williams threw four scores.",
                    "published_at": NOW,
                    "focus": "bears",
                }
            ],
        }
    }
    state = {"last_run_day": "2026-11-19", "seen_ids": ["https://www.espn.com/nfl/story/bears"]}
    assert collect([item], fetched, state, NOW, since=NOW - timedelta(days=7)) == []
    reading = {**state, "seen_ids": []}
    again = collect([item], fetched, reading, NOW, since=NOW - timedelta(days=7), force=True)
    assert [update.title for update in again] == ["Bears' Williams throws four touchdowns"]
