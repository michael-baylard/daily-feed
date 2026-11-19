"""Rockstar, NFL, and Twitch payloads. No network."""

from __future__ import annotations

from datetime import datetime, timezone

from daily_feed.feeds import (
    espn_articles,
    espn_now_text,
    espn_search_hits,
    image_url,
    is_conduct,
    og_image,
    rockstar_articles,
    twitch_stream,
)
from daily_feed.sources import article_updates
from daily_feed.live import fetch_streams
from daily_feed.models import Kind, WatchItem
from daily_feed.run import collect, remember
from daily_feed.sources import article_update

_ROCKSTAR = {
    "data": {
        "posts": {
            "results": [
                {
                    "id": 17944100058018,
                    "created": "11/19/26, 3:00\u202fPM",
                    "title": "Grand Theft Auto VI Now Available",
                    "url": "/newswire/article/39akk424a9oo53/grand-theft-auto-vi-now-available",
                    "subtitle": None,
                },
                {
                    "id": 17942308758530,
                    "created": "11/09/26, 2:00\u202fPM",
                    "title": "Grand Theft Auto VI: The Festival",
                    "url": "/newswire/article/o39o87a435a25a/grand-theft-auto-vi-the-festival",
                    "subtitle": "November 21 at Mana Wynwood, Miami",
                },
            ]
        }
    }
}

_ESPN = {
    "articles": [
        {
            "id": 1,
            "headline": "Bills get chance to feast on another backup QB",
            "description": "Ed Oliver bristled at the notion of a soft schedule. The Dolphins start a backup.",
            "published": "2026-11-19T22:24:33Z",
            "links": {"web": {"href": "http://www.espn.com/nfl/preview?gameId=401873070"}},
        }
    ]
}


def test_rockstar_post_from_today_is_gta_vi() -> None:
    articles = rockstar_articles(_ROCKSTAR)
    assert articles[0]["title"] == "Grand Theft Auto VI Now Available"
    assert articles[0]["url"].startswith("https://www.rockstargames.com/newswire/")
    assert articles[1]["text"] == "November 21 at Mana Wynwood, Miami"
    item = WatchItem(Kind.publisher, "Rockstar Games", "rockstar_games")
    update = article_update(item, articles, set(), "newswire")
    assert update is not None
    assert update.title == "Grand Theft Auto VI Now Available"


def test_espn_nfl_article_keeps_the_story_link() -> None:
    articles = espn_articles(_ESPN)
    assert articles[0]["title"].startswith("Bills get chance")
    assert "espn.com/nfl" in articles[0]["url"]
    item = WatchItem(Kind.league, "NFL", "nfl")
    update = article_update(item, articles, {articles[0]["url"]}, "nfl")
    assert update is None


def test_twitch_stream_matches_the_login() -> None:
    payload = {
        "data": [
            {
                "user_login": "tfue",
                "title": "GTA and ROB RUN",
                "started_at": "2026-11-19T22:00:00Z",
                "type": "live",
            }
        ]
    }
    assert twitch_stream(payload, "Tfue")["title"] == "GTA and ROB RUN"
    assert twitch_stream(payload, "burntpeanut") is None


def test_twitch_without_secrets_does_not_call_out() -> None:
    assert fetch_streams(["tfue"]) == {}


def test_posted_newswire_url_is_remembered() -> None:
    item = WatchItem(Kind.publisher, "Rockstar Games", "rockstar_games")
    now = datetime(2026, 11, 19, 21, tzinfo=timezone.utc)
    updates = collect(
        [item],
        {
            "rockstar_games": {
                "articles": rockstar_articles(_ROCKSTAR),
                "article_source": "newswire",
            }
        },
        {},
        now,
    )
    assert len(updates) == 1
    stored = remember({}, updates, {}, now)
    assert updates[0].url in stored["seen_ids"]


def test_week_keeps_recent_articles_and_the_picture() -> None:
    now = datetime(2026, 11, 19, 21, tzinfo=timezone.utc)
    articles = [
        {
            "title": "Older",
            "url": "https://www.espn.com/nfl/story/old",
            "text": "Old.",
            "published_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
            "image": "https://a.espncdn.com/photo/old.jpg",
        },
        {
            "title": "This week",
            "url": "https://www.espn.com/nfl/story/new",
            "text": "New.",
            "published_at": datetime(2026, 11, 18, tzinfo=timezone.utc),
            "image": "https://a.espncdn.com/photo/new.jpg",
        },
    ]
    item = WatchItem(Kind.league, "NFL", "nfl")
    found = article_updates(item, articles, set(), "nfl", now.replace(day=12))
    assert [update.title for update in found] == ["This week"]
    assert found[0].image.endswith("new.jpg")
    assert og_image('<meta property="og:image" content="https://media.example/a.jpg">').endswith("a.jpg")
    assert image_url([{"url": "https://a.espncdn.com/photo/x.png"}]).endswith("x.png")


def test_conduct_keeps_a_reported_penalty_and_drops_a_video() -> None:
    hits = espn_search_hits(
        {
            "results": [
                {
                    "contents": [
                        {
                            "id": "50533560",
                            "type": "headlinenews",
                            "displayName": "Rams WR Puka Nacua to serve 3-game suspension while on IR",
                            "date": "2026-11-19T22:47:33.000+00:00",
                            "link": {"web": "https://www.espn.com/nfl/story/_/id/50533560/puka"},
                        },
                        {
                            "id": "9",
                            "type": "video",
                            "displayName": "A clip",
                            "date": "2026-11-19T22:47:33.000+00:00",
                            "link": {"web": "https://www.espn.com/video/9"},
                        },
                    ]
                }
            ]
        }
    )
    assert len(hits) == 1
    text = espn_now_text(
        {
            "headlines": [
                {
                    "description": "Short.",
                    "story": "<p>He was accused of an antisemitic statement and denied it. The NFL suspended him.</p>",
                }
            ]
        }
    )
    assert "<p>" not in text
    assert is_conduct(hits[0]["title"], text)
    assert not is_conduct("Teenager denies sending a racist message", "He was banned.")
    item = WatchItem(Kind.publisher, "Conduct", "conduct")
    update = article_update(
        item,
        [
            {
                "id": hits[0]["id"],
                "title": hits[0]["title"],
                "url": hits[0]["url"],
                "text": text,
                "published_at": hits[0]["published_at"],
            }
        ],
        set(),
        "conduct",
    )
    assert update is not None
    now = datetime(2026, 11, 19, 23, tzinfo=timezone.utc)
    stored = remember({}, [update], {}, now)
    assert update.url in stored["seen_ids"]
