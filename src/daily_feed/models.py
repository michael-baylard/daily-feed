"""Shared types. Other modules import these. Do not grow this file with I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Kind(str, Enum):
    game = "game"
    show = "show"
    movie = "movie"
    publisher = "publisher"
    person = "person"


@dataclass(frozen=True)
class WatchItem:
    kind: Kind
    name: str
    slug: str
    urls: tuple[str, ...] = ()
    steam_app_id: int | None = None
    tvmaze_id: int | None = None
    twitch_login: str | None = None


@dataclass(frozen=True)
class Update:
    """One new fact, already safe to show in Discord."""

    slug: str
    kind: Kind
    name: str
    title: str
    published_at: datetime
    url: str
    lines: tuple[str, ...]
    source: str


@dataclass
class Watchlist:
    items: list[WatchItem] = field(default_factory=list)

    def by_slug(self, kind: Kind, slug: str) -> WatchItem | None:
        for item in self.items:
            if item.kind is kind and item.slug == slug:
                return item
        return None
