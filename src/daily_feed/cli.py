"""daily-feed run / daily-feed due. Dry-run prints markdown and does not post."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daily_feed.inbox import merge_inbox, parse_request
from daily_feed.live import fetch_conduct, fetch_nfl, fetch_rockstar, fetch_steam, fetch_streams
from daily_feed.models import Kind, WatchItem
from daily_feed.parallel import run_parallel
from daily_feed.post import send_messages
from daily_feed.run import collect, page_prompts, remember, render_day, worth_sending
from daily_feed.schedule import CHICAGO, due, local_day
from daily_feed.state import load_state, save_state
from daily_feed.watchlist import load_watchlist, save_watchlist

_USAGE = """\
usage: daily-feed run --watchlist PATH --state PATH --inbox DIR [--dry-run] [--no-post] [--demo] [--now ISO]
       daily-feed due --now ISO [--state PATH]
"""


class _UsageError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


def fetch_url(url: str) -> str:
    """Live fetch is not implemented. Dry-run and --demo never call this."""
    raise NotImplementedError(f"fetch_url is not implemented: {url}")


def post_messages(messages: list[str], prompts: list[str], images: list[str] | None = None) -> None:
    """POST the messages. ``prompts`` is unused once the summary is already written."""
    del prompts
    send_messages(messages, images)


def load_local_env(directory: Path, environ: dict[str, str] | None = None) -> None:
    """Fill missing keys from ``.env`` then ``.env.local``.

    A key already in the environment stays. GitHub Actions injects
    ``GEMINI_API_KEY`` that way, and a local file does not replace it.
    """
    target = os.environ if environ is None else environ
    found: dict[str, str] = {}
    for name in (".env", ".env.local"):
        path = directory / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                found[key] = value
    for key, value in found.items():
        if key not in target:
            target[key] = value


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        load_local_env(Path.cwd())
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args or args[0] in {"-h", "--help"}:
            print(_USAGE, end="")
            return 0 if args else 2
        if args[0] == "due":
            return _due(args[1:])
        if args[0] == "run":
            return _run(args[1:])
        raise _UsageError(_USAGE)
    except _UsageError as exc:
        message = exc.message if exc.message.endswith("\n") else exc.message + "\n"
        print(message, file=sys.stderr, end="")
        return 2


def _due(argv: list[str]) -> int:
    flags = _flags(argv, {"--now": 1, "--state": 1})
    now_text = flags.get("--now")
    if not isinstance(now_text, str):
        raise _UsageError("due requires --now ISO\n")
    last = _last_run_day(flags.get("--state"))
    print("yes" if due(_parse_now(now_text), last) else "no")
    return 0


def _run(argv: list[str]) -> int:
    flags = _flags(
        argv,
        {
            "--watchlist": 1,
            "--state": 1,
            "--inbox": 1,
            "--now": 1,
            "--dry-run": 0,
            "--no-post": 0,
            "--demo": 0,
        },
    )
    watchlist_path = flags.get("--watchlist")
    state_path = flags.get("--state")
    inbox_dir = flags.get("--inbox")
    if not isinstance(watchlist_path, str) or not isinstance(state_path, str) or not isinstance(inbox_dir, str):
        raise _UsageError("run requires --watchlist, --state, and --inbox\n")
    dry_run = bool(flags.get("--dry-run"))
    no_post = bool(flags.get("--no-post"))
    demo = bool(flags.get("--demo"))
    now_text = flags.get("--now")
    now = _parse_now(now_text) if isinstance(now_text, str) else datetime.now(timezone.utc)

    watchlist = load_watchlist(watchlist_path)
    incoming = _read_inbox(Path(inbox_dir))
    watchlist, _added = merge_inbox(watchlist, incoming)
    state = load_state(state_path)
    day_due = due(now, _coerce_day(state.get("last_run_day")))
    has_streamer = any(item.twitch_login for item in watchlist.items)
    if not day_due and not has_streamer:
        if dry_run:
            print("not due")
        return 0

    fetched = demo_fetched(watchlist.items, now) if demo else {}
    if not demo and not dry_run:
        fetched = _fetch_live(watchlist.items)

    since = _aware(now) - timedelta(days=7)
    updates = collect(watchlist.items, fetched, state, now, since=since)
    if not day_due:
        updates = [update for update in updates if update.source == "twitch"]
    updates = [update for update in updates if worth_sending(update)]
    if not updates and not day_due:
        if dry_run:
            print("not due")
        return 0
    messages = render_day(updates)
    if dry_run or no_post or demo:
        for message in messages:
            print(message)
        return 0

    prompts = page_prompts(watchlist.items, updates, fetched)
    post_messages(messages, prompts, [update.image for update in updates])
    save_state(state_path, remember(state, updates, fetched, now, stamp_day=day_due))
    save_watchlist(watchlist_path, watchlist)
    return 0


def demo_fetched(items: list[WatchItem], now: datetime) -> dict:
    """Fixed payloads for --demo. No sockets."""
    fetched: dict = {}
    stamp = int(_aware(now).timestamp())
    airdate = local_day(now).isoformat()
    started = _aware(now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for item in items:
        if item.twitch_login:
            fetched[item.slug] = {
                "twitch": {
                    "user_login": item.twitch_login,
                    "title": f"{item.name} is live",
                    "started_at": started,
                }
            }
            continue
        if item.kind in (
            Kind.movie,
            Kind.publisher,
            Kind.tool,
            Kind.athlete,
            Kind.league,
            Kind.match,
            Kind.person,
        ):
            url = item.urls[0] if item.urls else ""
            fetched[item.slug] = {
                "page_text": f"Demo page for {item.name}",
                "page_url": url,
            }
            continue
        if item.steam_app_id is not None:
            fetched[item.slug] = {
                "steam": {
                    "appnews": {
                        "newsitems": [
                            {
                                "gid": f"demo-{item.slug}",
                                "title": f"{item.name} update",
                                "url": f"https://store.steampowered.com/news/app/{item.steam_app_id}",
                                "contents": "Line one\nLine two\nLine three\n",
                                "date": stamp,
                            }
                        ]
                    }
                }
            }
            continue
        if item.kind is Kind.game and item.urls:
            url = item.urls[0]
            fetched[item.slug] = {"page_text": f"Demo page for {item.name}", "page_url": url}
            continue
        if item.tvmaze_id is not None:
            fetched[item.slug] = {
                "episode": {
                    "name": "Demo",
                    "season": 1,
                    "number": 1,
                    "airdate": airdate,
                    "url": f"https://www.tvmaze.com/episodes/{item.tvmaze_id}",
                }
            }
    return fetched


def _fetch_live(items: list[WatchItem]) -> dict:
    """Fetch every wired row at the same time.

    Steam, Rockstar's newswire, the NFL feed, the conduct feed, and Twitch are wired.
    A page that is still only ``fetch_url`` is skipped. Twitch returns
    nothing until ``TWITCH_CLIENT_ID`` and ``TWITCH_CLIENT_SECRET`` are set.
    """
    streams = fetch_streams([item.twitch_login or "" for item in items])

    def _one(item: WatchItem) -> tuple[str, dict]:
        if item.twitch_login:
            live = streams.get(item.twitch_login.casefold())
            return item.slug, {"twitch": live} if live else {}
        if _is_rockstar(item):
            return item.slug, {"articles": fetch_rockstar(), "article_source": "newswire"}
        if _is_nfl(item):
            return item.slug, {"articles": fetch_nfl(), "article_source": "nfl"}
        if _is_conduct(item):
            return item.slug, {"articles": fetch_conduct(), "article_source": "conduct"}
        if item.steam_app_id is not None:
            return item.slug, {"steam": fetch_steam(item.steam_app_id)}
        return item.slug, {}

    return dict(run_parallel(items, _one))


def _is_rockstar(item: WatchItem) -> bool:
    return any("rockstargames.com/newswire" in url for url in item.urls)


def _is_nfl(item: WatchItem) -> bool:
    return item.kind is Kind.league and any("nfl.com" in url for url in item.urls)


def _is_conduct(item: WatchItem) -> bool:
    return any("espn.com/search" in url for url in item.urls)


def _read_inbox(directory: Path) -> list[WatchItem]:
    if not directory.is_dir():
        return []
    items: list[WatchItem] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
            continue
        items.extend(parse_request(path.read_text(encoding="utf-8-sig")))
    return items


def _last_run_day(path: object) -> date | None:
    if not isinstance(path, str):
        return None
    return _coerce_day(load_state(path).get("last_run_day"))


def _coerce_day(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _parse_now(text: str) -> datetime:
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHICAGO)
    return parsed


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _flags(argv: list[str], spec: dict[str, int]) -> dict[str, object]:
    found: dict[str, object] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token not in spec:
            raise _UsageError(f"unknown argument: {token}\n")
        if spec[token] == 0:
            found[token] = True
            index += 1
            continue
        if index + 1 >= len(argv):
            raise _UsageError(f"missing value for {token}\n")
        found[token] = argv[index + 1]
        index += 2
    return found
