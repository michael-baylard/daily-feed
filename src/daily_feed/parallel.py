"""Run independent item work at the same time. Stdlib threads. No network here."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_parallel(items: Iterable[T], worker: Callable[[T], R], workers: int = 8) -> list[R]:
    """Call ``worker`` once per item. Results stay in input order.

    Threads overlap waiting. A worker exception is raised to the caller.
    An empty input returns an empty list and starts no pool.
    """
    batch = list(items)
    if not batch:
        return []
    count = max(1, min(int(workers), len(batch)))
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(worker, item) for item in batch]
        return [future.result() for future in futures]
