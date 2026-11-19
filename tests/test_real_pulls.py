"""Parsers against Steam responses captured on 2026-11-19. No network."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from daily_feed.discord_md import render
from daily_feed.models import Kind, WatchItem
from daily_feed.run import worth_sending
from daily_feed.sources import page_update, steam_news_update

_FIXTURE = Path(__file__).parent / "fixtures" / "steam_2026_11_19.json"
_WEEK = datetime(2026, 11, 12, tzinfo=timezone.utc)


def _payload(key: str) -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))[key]


def _news(key: str) -> dict:
    return _payload(key)["appnews"]["newsitems"][0]


def _when(key: str) -> datetime:
    return datetime.fromtimestamp(int(_news(key)["date"]), tz=timezone.utc)


def _post(name: str, app_id: int, key: str) -> str:
    item = WatchItem(Kind.game, name, "row", steam_app_id=app_id)
    update = steam_news_update(item, _payload(key), set())
    assert update is not None
    assert worth_sending(update)
    return render(update)


def test_unfiltered_gta_today_is_a_pc_gamer_column() -> None:
    news = _news("gta_newest")
    assert news["feedlabel"] == "PC Gamer"
    assert _when("gta_newest") >= _WEEK
    text = _post("Grand Theft Auto Online", 271590, "gta_newest")
    assert "It's time for GTA 5's last challenge" in text
    assert "<a " not in text
    assert "say goodbye" in text


def test_official_gta_post_is_older_than_this_week() -> None:
    news = _news("gta_official")
    assert news["feedlabel"] == "Community Announcements"
    assert _when("gta_official") < _WEEK
    text = _post("Grand Theft Auto Online", 271590, "gta_official")
    assert "Kortz Center" in text


def test_rob_run_week_is_the_patch_and_the_faq() -> None:
    assert _news("rob_patch")["title"] == "Patch Notes"
    assert _news("rob_faq")["title"].startswith("ROB RUN: Answering")
    assert _when("rob_patch") >= _WEEK
    assert _when("rob_faq") >= _WEEK
    patch = _post("ROB RUN", 4262460, "rob_patch")
    faq = _post("ROB RUN", 4262460, "rob_faq")
    assert "Patch Notes" in patch
    assert "profanity filter" in patch
    assert "Frequently Asked Questions" in faq


def test_gta_vi_page_is_held_until_a_model_writes_a_line() -> None:
    item = WatchItem(
        Kind.game,
        "Grand Theft Auto VI",
        "grand_theft_auto_vi",
        urls=("https://www.rockstargames.com/VI",),
    )
    page = "Grand Theft Auto VI Now Available\nNovember 19, 2026\nWelcome to Leonida"
    update = page_update(
        item,
        page,
        previous_hash=None,
        url=item.urls[0],
        published_at=datetime(2026, 11, 19, tzinfo=timezone.utc),
    )
    assert update is not None
    assert update.lines == ()
    assert not worth_sending(update)
