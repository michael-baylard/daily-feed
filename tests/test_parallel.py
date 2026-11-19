"""Parallel item work. No network."""

from __future__ import annotations

import time

import pytest

from daily_feed.parallel import run_parallel


def test_empty_input_starts_no_work() -> None:
    calls: list[int] = []

    def worker(item: int) -> int:
        calls.append(item)
        return item

    assert run_parallel([], worker) == []
    assert calls == []


def test_results_stay_in_input_order() -> None:
    def worker(item: int) -> int:
        time.sleep(0.01 * (4 - item))
        return item * 10

    assert run_parallel([1, 2, 3, 4], worker, workers=4) == [10, 20, 30, 40]


def test_every_item_runs() -> None:
    seen: list[str] = []

    def worker(item: str) -> str:
        seen.append(item)
        return item.upper()

    assert run_parallel(["gta", "nfl", "rob"], worker) == ["GTA", "NFL", "ROB"]
    assert sorted(seen) == ["gta", "nfl", "rob"]


def test_waiting_overlaps() -> None:
    def worker(item: int) -> int:
        time.sleep(0.2)
        return item

    started = time.perf_counter()
    assert run_parallel([1, 2, 3, 4], worker, workers=4) == [1, 2, 3, 4]
    elapsed = time.perf_counter() - started
    assert elapsed < 0.55


def test_worker_exception_reaches_the_caller() -> None:
    def worker(item: int) -> int:
        if item == 2:
            raise NotImplementedError(f"fetch_url is not implemented: {item}")
        return item

    with pytest.raises(NotImplementedError, match="fetch_url"):
        run_parallel([1, 2, 3], worker, workers=3)
