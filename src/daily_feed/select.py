"""Which stories are worth a card, and which repeats to drop."""

from __future__ import annotations

import re

from daily_feed.models import Update

_COLLEGE = ("college football", "ncaa", "heisman", "college-football", "cfp ")
_ROUTINE = (
    "highlights",
    "preview",
    "rankings",
    "big board",
    "expects to play",
    "injury report",
    "practice report",
    "inactives",
    "snap count",
    "fantasy",
    "power rankings",
    "waiver",
)
_COMIC = (
    "hippo",
    "mascot",
    "streaker",
    "costume",
    "wedding",
    "proposed",
    "hot dog",
    "alligator",
    "goat",
    "parrot",
    "pizza",
    "apology",
    "apologized",
    "suspended",
    "fined",
    "fashion",
    "hat",
    "banana",
)
_STOP = {"the", "a", "an", "vs", "and", "of", "to", "for", "in", "on", "nfl", "week", "with", "from"}


_GTA_VI = re.compile(r"\b(?:gta[\s-]*(?:vi|6)|grand theft auto[\s-]*(?:vi|6))\b", re.IGNORECASE)
_GTA_V = re.compile(
    r"\b(?:gta[\s-]*(?:v|5)|grand theft auto[\s-]*(?:v|5)|gta online|grand theft auto online)\b",
    re.IGNORECASE,
)


def _gta_vi_only(update: Update) -> bool:
    """GTA posts are GTA VI. GTA V and GTA Online are skipped."""
    blob = f"{update.name}\n{update.title}\n" + " ".join(update.lines)
    if _GTA_VI.search(blob):
        return True
    if _GTA_V.search(blob):
        return False
    return update.name.casefold() not in {"grand theft auto online", "grand theft auto v", "gta v", "gta 5"}


def relevant(update: Update) -> bool:
    """NFL keeps the Bears, and other football only when the item is already a joke.

    College football is skipped unless the item is absurd. GTA V is skipped.
    """
    if not _gta_vi_only(update):
        return False
    if update.source != "nfl":
        return True
    blob = f"{update.title}\n{update.url}\n" + " ".join(update.lines)
    folded = blob.casefold()
    comic = _has(folded, _COMIC)
    if _has(folded, _COLLEGE) and not comic:
        return False
    if update.focus == "bears":
        return True
    if "preview?gameid" in folded or "/preview" in folded:
        return False
    if _has(folded, _ROUTINE):
        return False
    return comic


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def dedupe(updates: list[Update]) -> list[Update]:
    """Drop a repeated URL or a headline that is the same game in different clothes."""
    ranked = sorted(updates, key=lambda update: (update.focus != "bears", -len(" ".join(update.lines))))
    seen_url: set[str] = set()
    seen_title: list[set[str]] = []
    kept: list[Update] = []
    for update in ranked:
        url = _url(update.url)
        tokens = _tokens(update.title)
        if url and url in seen_url:
            continue
        if tokens and any(_same(tokens, previous) for previous in seen_title):
            continue
        if url:
            seen_url.add(url)
        if tokens:
            seen_title.append(tokens)
        kept.append(update)
    kept.sort(key=lambda update: (update.published_at, update.slug, update.url))
    return kept


def _url(value: str) -> str:
    return value.strip().casefold().replace("http://", "https://").split("?")[0].rstrip("/")


def _tokens(title: str) -> set[str]:
    words = re.sub(r"[^a-z0-9]+", " ", title.casefold()).split()
    return {word for word in words if word not in _STOP and len(word) > 2}


def _same(left: set[str], right: set[str]) -> bool:
    if not left or not right:
        return False
    shared = left & right
    if len(shared) < 2:
        return False
    return len(shared) / min(len(left), len(right)) >= 0.6
