"""Discord webhook body. Mentions are disabled on the payload."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from daily_feed.safety import assert_no_pings

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


def message_body(content: str, image: str = "") -> dict:
    """One webhook JSON body. Discord will not ping anyone from this payload.

    The article link unfurls the source picture. A second embed would show
    the same story twice, so ``image`` is accepted and not attached.
    """
    del image
    assert_no_pings(content)
    return {"content": content, "allowed_mentions": {"parse": []}}


def send_messages(messages: list[str], images: list[str] | None = None) -> None:
    """POST each message to the channel webhook. Raises without the URL."""
    url = webhook_url()
    pictures = images or []
    for index, content in enumerate(messages):
        picture = pictures[index] if index < len(pictures) else ""
        request = urllib.request.Request(
            url,
            data=json.dumps(message_body(content, picture)).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "daily-feed/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status not in (200, 204):
                    raise RuntimeError(f"Discord returned {response.status}")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Discord returned {exc.code}") from None
        if index + 1 < len(messages):
            time.sleep(0.4)


def webhook_url(environ: dict[str, str] | None = None) -> str:
    """Read the channel URL from the environment. The URL is not stored in git."""
    source = os.environ if environ is None else environ
    url = source.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise RuntimeError(f"missing {WEBHOOK_ENV}")
    return url
