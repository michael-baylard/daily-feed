"""Long bodies become two lines. The model is injected. No network."""

from __future__ import annotations

from datetime import datetime, timezone

from daily_feed.models import Kind, WatchItem
from daily_feed.run import collect
from daily_feed.summarize import cadence, conduct_lines, condense, describe, joke_prompt, mask_slur


def test_each_story_gets_a_different_sentence_shape() -> None:
    shapes = {cadence(title) for title in ("Fiona the hippo", "Caleb Williams", "Kortz Center", "Patch Notes", "Puka Nacua")}
    assert len(shapes) > 1
    prompt = joke_prompt("NFL", "The hippo ate a hat.", "")
    assert "under 20 words" in prompt
    assert "straight-faced satire desk" in prompt
    assert "Apparently" in prompt
    assert "hard consonant" in prompt


def test_short_news_still_asks_what_happened() -> None:
    def complete(text: str, name: str) -> str:
        assert name == "Rockstar Games"
        assert "Now Available" in text
        return "Grand Theft Auto VI is out on PlayStation 5 and Xbox Series X|S."

    lines = describe(
        "Grand Theft Auto VI Now Available",
        "Grand Theft Auto VI Now Available",
        "Rockstar Games",
        complete=complete,
    )
    assert lines == ("Grand Theft Auto VI is out on PlayStation 5 and Xbox Series X|S.",)


def test_conduct_line_keeps_the_reported_remark_and_the_denial() -> None:
    body = (
        "The league suspended him three games. "
        "A lawsuit accused him of an antisemitic statement and a bite. "
        "He denied the allegations."
    )
    missed = ("The league suspended him three games.",)
    lines = conduct_lines(body, missed)
    assert "antisemitic" in lines[0]
    assert any("denied" in line.casefold() for line in lines)
    kept = ("The suit accused him of an antisemitic statement, and he denied it.",)
    assert conduct_lines(body, kept) == kept


def test_a_quoted_slur_is_blanked_before_the_model_sees_it() -> None:
    def complete(text: str, name: str) -> str:
        assert "faggot" not in text.casefold()
        assert "f****t" in text
        return 'He was suspended after saying "faggot" to a teammate.'

    lines = describe(
        "Ban",
        'He yelled "faggot" and was suspended for a homophobic remark.',
        "Conduct",
        complete=complete,
    )
    assert lines == ('He was suspended after saying "f****t" to a teammate.',)
    assert "faggot" not in lines[0].casefold()
    assert mask_slur("faggot") == "f****t"


def test_conduct_summary_keeps_the_blanked_quote() -> None:
    body = 'The club fired him after he said "faggot" on a stream. He denied it.'
    lines = conduct_lines(body, ("The club fired him for a homophobic remark.",))
    assert lines[0] == 'The club fired him for a homophobic remark, quoted as "f****t".'
    assert "faggot" not in " ".join(lines).casefold()


def test_short_text_stays() -> None:
    assert condense("Patch is live.", "ROB RUN") == ("Patch is live.",)


def test_long_body_without_a_model_is_not_summarized() -> None:
    text = "<p>First sentence. Second sentence. " + ("More detail. " * 20) + "</p>"
    assert condense(text, "GTA") == ()


def test_model_output_drops_pings_and_keeps_two_lines() -> None:
    def complete(text: str, name: str) -> str:
        assert name == "NFL"
        assert "backup" in text
        return "@everyone stay\nSecond line\nThird line"

    lines = condense("x" * 220 + " backup", "NFL", complete=complete)
    assert lines == ("stay", "Second line")


def test_collect_holds_a_long_steam_body_until_the_model(monkeypatch) -> None:
    item = WatchItem(Kind.game, "ROB RUN", "rob_run", steam_app_id=4262460)
    body = (
        "First change is live and it covers the profanity filter plus the report button. "
        "Second change carries progress across regions and adds the mouse option. "
        "Third change is the one that should be left out of the Discord post entirely."
    )
    now = datetime(2026, 11, 19, 21, tzinfo=timezone.utc)
    fetched = {
        "rob_run": {
            "steam": {
                "appnews": {
                    "newsitems": [
                        {
                            "gid": "9",
                            "title": "Patch Notes",
                            "url": "https://store.steampowered.com/news/9",
                            "contents": body,
                            "date": 1790000000,
                        }
                    ]
                }
            }
        }
    }
    held = collect([item], fetched, {}, now)
    assert held[0].lines == ()

    monkeypatch.setattr(
        "daily_feed.run.describe",
        lambda title, body, name: ("The patch adds a profanity filter.",),
    )
    posted = collect([item], fetched, {}, now)
    assert posted[0].lines == ("The patch adds a profanity filter.",)
