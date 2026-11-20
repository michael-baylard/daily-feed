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
