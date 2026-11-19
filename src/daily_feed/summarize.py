"""A short "what happened" line for a news post.

Gemini 3.8 Flash writes it. GitHub Actions passes ``GEMINI_API_KEY``
from the repository secret. There is no local summary.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.request
from collections.abc import Callable

from daily_feed.safety import find_pings, strip_pings

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_MASKED = re.compile(r"\b[A-Za-z]\*{2,}[A-Za-z]\b")
_SLUR = re.compile(
    r"\b("
    r"niggers|nigger|niggas|nigga|"
    r"faggots|faggot|fags|fag|"
    r"dykes|dyke|trannies|tranny|"
    r"kikes|kike"
    r")\b",
    re.IGNORECASE,
)
_LIMIT = 180
_MODEL = "gemini-3.8-flash"

Complete = Callable[[str, str], str | None]


_REASON = (
    "racial",
    "racist",
    "racism",
    "homophob",
    "anti-gay",
    "antigay",
    "antisemit",
    "slur",
    "lgbt",
)


def describe(
    title: str,
    body: str,
    name: str,
    complete: Complete | None = None,
    note: str = "",
) -> tuple[str, ...]:
    """What happened, in one or two sentences. Empty when the model does not answer."""
    plain_title = mask_slur(_plain(title))
    plain_body = mask_slur(_plain(body))
    source = plain_body or plain_title
    if not source:
        return ()
    payload = f"Title: {plain_title}\nText: {source}"
    written = complete(payload, name) if complete is not None else _gemini(payload, name, note)
    return _mask_lines(_lines(written or ""))


def mask_slur(text: str) -> str:
    """Blank the middle of a slur. ``faggot`` becomes ``f****t``."""

    def _one(match: re.Match[str]) -> str:
        word = match.group(0)
        if len(word) < 3:
            return word[0] + "*"
        return word[0] + ("*" * (len(word) - 2)) + word[-1]

    return _SLUR.sub(_one, text)


def conduct_lines(body: str, written: tuple[str, ...]) -> tuple[str, ...]:
    """Keep a model line that names the remark. Otherwise use the source sentences that do."""
    masked = mask_slur(_plain(body))
    lines = _mask_lines(written)
    quote = _first_mask(masked)
    if lines and _names_remark(" ".join(lines)):
        return _ensure_quote(lines, quote)
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", masked) if part.strip()
    ]
    picked = [line for line in sentences if _names_remark(line)]
    denied = [
        line
        for line in sentences
        if "denied" in line.casefold() or "denies" in line.casefold()
    ]
    lines: list[str] = []
    for line in picked + denied:
        if line not in lines:
            lines.append(line)
        if len(lines) == 2:
            break
    return _ensure_quote(tuple(lines), quote) or written


def condense(text: str, name: str, complete: Complete | None = None) -> tuple[str, ...]:
    """Model lines for a long body. A short body is returned unchanged."""
    plain = _plain(text)
    if not plain:
        return ()
    if len(plain) <= _LIMIT and complete is None:
        return (plain,)
    return describe("", plain, name, complete=complete)


def _names_remark(text: str) -> bool:
    blob = text.casefold()
    return any(word in blob for word in _REASON) or _MASKED.search(text) is not None


def _first_mask(text: str) -> str:
    match = _MASKED.search(text)
    return match.group(0) if match else ""


def _ensure_quote(lines: tuple[str, ...], quote: str) -> tuple[str, ...]:
    if not quote or any(quote in line for line in lines):
        return lines
    if not lines:
        return (f'The reported quote was "{quote}".',)
    first = lines[0].rstrip()
    if first.endswith("."):
        first = first[:-1]
    attached = f'{first}, quoted as "{quote}".'
    return (attached,) if len(lines) == 1 else (attached, lines[1])


def _mask_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(mask_slur(line) for line in lines)


def _plain(text: str) -> str:
    cleaned = html.unescape(_TAGS.sub(" ", text))
    cleaned = strip_pings(cleaned)
    return _SPACES.sub(" ", cleaned).strip()


def _lines(text: str) -> tuple[str, ...]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = _plain(raw)
        if not line or find_pings(line):
            continue
        lines.append(line)
        if len(lines) == 2:
            break
    return tuple(lines)


def _gemini(text: str, name: str, note: str = "") -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "").strip() or _MODEL
    extra = f"{note.strip()}\n" if note.strip() else ""
    prompt = (
        f"Say what happened in one or two short sentences for a Discord post about {name}.\n"
        f"{extra}"
        "Use only the text below. Do not add facts.\n"
        "No links. No @ mentions. No HTML.\n\n"
        f"{text[:4000]}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 256,
                "temperature": 0.2,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not candidates or not isinstance(candidates, list):
        return None
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not parts or not isinstance(parts, list) or not isinstance(parts[0], dict):
        return None
    written = parts[0].get("text")
    return written if isinstance(written, str) else None
