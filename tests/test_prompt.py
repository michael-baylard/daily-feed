"""Prompt text only. No model call."""

from __future__ import annotations

from daily_feed.models import Kind, WatchItem
from daily_feed.prompt import build_prompt
from daily_feed.slug import to_slug


def _movie() -> WatchItem:
    name = "Spider-Man"
    return WatchItem(kind=Kind.movie, name=name, slug=to_slug(name))


def test_prompt_contains_snake_slug_and_letters_only_form() -> None:
    prompt = build_prompt(_movie(), "studio page")
    assert "spider_man" in prompt
    assert "spiderman" in prompt
    assert "spider_man".replace("_", "") == "spiderman"


def test_prompt_search_form_drops_underscores_and_keeps_digits() -> None:
    name = "Helldivers 2"
    item = WatchItem(kind=Kind.game, name=name, slug=to_slug(name), steam_app_id=553850)
    prompt = build_prompt(item, "notes")
    assert "helldivers_2" in prompt
    assert "helldivers2" in prompt


def test_prompt_includes_kind() -> None:
    prompt = build_prompt(_movie(), "studio page")
    assert "\nKind: movie\n" in prompt


def test_prompt_trims_page_to_4000_chars() -> None:
    body = "B" * 4000 + "TAIL"
    prompt = build_prompt(_movie(), body)
    assert "B" * 4000 in prompt
    assert "B" * 4001 not in prompt
    assert "TAIL" not in prompt


def test_prompt_keeps_a_page_that_is_exactly_4000_chars() -> None:
    body = "C" * 4000
    prompt = build_prompt(_movie(), body)
    assert body in prompt


def test_prompt_asks_for_three_plain_lines_without_mentions_or_links() -> None:
    prompt = build_prompt(_movie(), "Hello page")
    assert "Return exactly 3 plain lines." in prompt
    assert "No @ mentions." in prompt
    assert "No links in the lines." in prompt
    assert "AI only when it is about this title." in prompt
    assert "A general model or tool launch is out of scope." in prompt
