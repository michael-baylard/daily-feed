"""Webhook body. No network."""

from __future__ import annotations

import pytest

from daily_feed.post import message_body, webhook_url


def test_payload_does_not_attach_a_second_picture() -> None:
    body = message_body("**[Story](https://www.espn.com/nfl/story/1)**", "https://a.espncdn.com/photo/story.jpg")
    assert "embeds" not in body
    assert body["allowed_mentions"] == {"parse": []}


def test_payload_drops_a_non_https_image() -> None:
    body = message_body("hello", "http://example.com/a.jpg")
    assert "embeds" not in body


def test_payload_disables_mentions() -> None:
    body = message_body("## BurntPeanut\n**Live**\n\n[Open person](https://www.twitch.tv/burntpeanut)\n-# twitch")
    assert body["allowed_mentions"] == {"parse": []}
    assert "@" not in body["content"]


def test_payload_rejects_a_ping() -> None:
    with pytest.raises(ValueError):
        message_body("hello @everyone")


def test_webhook_url_comes_from_the_environment() -> None:
    assert webhook_url({"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/secret"}) == (
        "https://discord.com/api/webhooks/1/secret"
    )


def test_missing_webhook_url_raises() -> None:
    with pytest.raises(RuntimeError):
        webhook_url({})
