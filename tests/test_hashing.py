"""Page fingerprints. No network."""

from __future__ import annotations

import hashlib

from daily_feed.hashing import changed, content_hash

_HELLO = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_content_hash_is_sha256_hex() -> None:
    assert content_hash("hello") == _HELLO
    assert content_hash("hello") == hashlib.sha256(b"hello").hexdigest()
    assert content_hash("café") == hashlib.sha256("café".encode("utf-8")).hexdigest()


def test_changed_false_when_text_is_unchanged() -> None:
    text = "studio slate"
    assert changed(content_hash(text), text) is False


def test_changed_true_when_old_hash_missing() -> None:
    assert changed(None, "studio slate") is True


def test_changed_true_when_text_differs() -> None:
    assert changed(content_hash("before"), "after") is True


def test_changed_compares_stored_hash_to_new_text() -> None:
    text = "same bytes"
    assert changed(text, text) is True
    assert changed(content_hash(text), text) is False
