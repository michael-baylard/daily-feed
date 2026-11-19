"""Fingerprints for page text. Stdlib hashlib only."""

from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    """SHA-256 hex digest of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def changed(old: str | None, new: str) -> bool:
    """True when there is no stored hash, or it differs from the new text.

    ``old`` is a previous hex digest, or None. ``new`` is raw page text.
    Comparison is hash-to-hash, never hash-to-raw-text.
    """
    if old is None:
        return True
    return old != content_hash(new)
