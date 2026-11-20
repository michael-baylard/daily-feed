"""A short "what happened" line for a news post.

Grok 4.7 writes it. GitHub Actions passes ``XAI_API_KEY`` from the
repository secret. There is no local summary.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.request
from collections.abc import Callable

from daily_feed.personas import voice
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
_MODEL = "grok-4.7"
_CHAT = "https://api.x.ai/v1/chat/completions"
_CADENCE = (
    "One sentence. The absurd detail is the subject.",
    "Two short sentences. The second is five words or fewer.",
    "One deadpan news sentence. No commentary after it.",
    "Name the person, then the ridiculous fact.",
    "Start with the institution and end on the small hard detail.",
)
_DANGLING = re.compile(
    r"(?:^|\s)(?:a|an|the|to|of|for|and|or|but|with|in|on|at|from|by|as|into|over|after|before)$",
    re.IGNORECASE,
)
_STOCK = re.compile(
    r"^(apparently|naturally|well|so|look|of course|basically|honestly|turns out)\b",
    re.IGNORECASE,
)
_GRIM = re.compile(r"\b(?:died|death|killed|tribute|passed away)\b", re.IGNORECASE)
_FIRST = re.compile(r"\b(?:I|I'm|I'd|I'll|I've|me|Me|my|My|we|We|we're|We've|we've|our|Our|ours|us)\b")

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
    persona: str = "shelf",
) -> tuple[str, ...]:
    """What happened, in the persona's voice. Empty when the model does not answer."""
    plain_title = mask_slur(_plain(title))
    plain_body = mask_slur(_plain(body))
    source = plain_body or plain_title
    if not source:
        return ()
    payload = plain_title if source.casefold() == plain_title.casefold() else f"{plain_title}\n{source}"
    written = complete(payload, name) if complete is not None else _grok(payload, name, note, persona)
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
        finished = _finish(line)
        if finished is None:
            continue
        lines.append(finished)
        if len(lines) == 2:
            break
    return tuple(lines)


def _finish(line: str) -> str | None:
    """Close a finished short line. A cut-off line is dropped."""
    if line[-1:] in ".!?":
        return line
    if len(line) > 40 or _DANGLING.search(line):
        return None
    return f"{line}."


def _seed(text: str) -> int:
    return sum(text.encode()) or 1


def cadence(seed: str) -> str:
    """A sentence shape for this story. The next story gets a different one."""
    return _CADENCE[_seed(seed) % len(_CADENCE)]


def swears(seed: str) -> bool:
    """About three quarters of the cards. The same story keeps the same answer."""
    return (_seed(seed) // len(_CADENCE)) % 4 != 0


def joke_prompt(name: str, text: str, note: str = "", persona: str = "shelf") -> str:
    """Instructions for one card, in that persona's voice."""
    extra = f"{note.strip()}\n" if note.strip() else ""
    return (
        f"Say what happened for a Discord post about {name}.\n"
        f"{voice(persona)}\n"
        f"Shape: {cadence(text)}\n"
        "Two sentences at most. The fact, then the reaction. "
        "End the fact with a period.\n"
        "Second person or third person. No I, me, my, we, our, or us.\n"
        f"{_profanity(text, persona)}\n"
        "Do not invent a stat, a quote, a job, or a place. "
        "On bad news, add one new short reaction after the fact. That reaction is not a new fact. "
        "On good news, stop after the fact. "
        "Do not impersonate the person in the story. Never be cruel to a private person.\n"
        "Do not start with Apparently, Naturally, Well, So, Look, Of course, Basically, Honestly, or Turns out. "
        "Do not mention these instructions, or the words title and text as labels.\n"
        f"{extra}"
        "Use only the text below.\n"
        "No catchphrases. No hashtags. No links. No @ mentions. No HTML. No slur.\n\n"
        f"{text[:4000]}"
    )


def _blocks_curse(text: str, persona: str) -> bool:
    return persona == "conduct" or _GRIM.search(text) is not None


def _profanity(text: str, persona: str) -> str:
    if _blocks_curse(text, persona):
        return "No profanity in this one."
    return (
        "Interceptions, fumbles, a loss, an injury, a player ruled out, a missed kick, or a dumb penalty "
        "get one new short curse after the fact. Do not copy a mood sample. "
        "Any other story stops after the fact."
    )


def _grok(text: str, name: str, note: str = "", persona: str = "shelf") -> str | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("XAI_MODEL", "").strip() or _MODEL
    prompt = joke_prompt(name, text, note, persona)
    written = _complete(key, model, prompt)
    if written and (_stock(written) or first_person(written)):
        fix = (
            "\nCut the stock opener. Second person or third person. "
            "No I, me, my, we, our, or us. A new reaction only when the news is bad."
        )
        retry = _complete(key, model, prompt + fix) or ""
        if _lines(retry) and not first_person(retry):
            written = retry
        elif first_person(written):
            written = ""
    return written or None


def first_person(text: str) -> bool:
    """True when the card talks as I or we."""
    return _FIRST.search(text) is not None


def _stock(text: str) -> bool:
    first = text.strip().split("\n", 1)[0]
    folded = first.casefold()
    meta = "same bit" in folded or ("title" in folded and "text" in folded)
    bare = first[-1:] not in ".!?"
    return bool(_STOCK.match(first)) or "apparently" in folded or meta or bare


def _complete(key: str, model: str, prompt: str) -> str | None:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 120,
            "reasoning_effort": "low",
        }
    ).encode()
    request = urllib.request.Request(
        _CHAT,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
    written = message.get("content")
    return written if isinstance(written, str) else None
