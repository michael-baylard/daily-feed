"""Stable ids from display names. Stdlib only."""

from __future__ import annotations

_APOSTROPHES = str.maketrans("", "", "'\u2019")


def to_slug(name: str) -> str:
    """ASCII snake_case. Empty after cleanup raises ValueError."""
    text = name.strip().casefold().replace("&", " and ").translate(_APOSTROPHES)
    parts: list[str] = []
    chunk: list[str] = []
    for char in text:
        if "a" <= char <= "z" or "0" <= char <= "9":
            chunk.append(char)
            continue
        if chunk:
            parts.append("".join(chunk))
            chunk.clear()
    if chunk:
        parts.append("".join(chunk))
    slug = "_".join(parts)
    if not slug:
        raise ValueError("empty slug after cleanup")
    return slug


def search_key(name: str) -> str:
    """Lowercase letters and digits only, no underscores. Same cleanup as to_slug."""
    return to_slug(name).replace("_", "")
