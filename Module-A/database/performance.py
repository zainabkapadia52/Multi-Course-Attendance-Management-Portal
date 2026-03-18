from __future__ import annotations

import random
import time
import tracemalloc
from dataclasses import dataclass
from typing import Any

from .bplustree import BPlusTree
from .bruteforce import BruteForceDB


@dataclass
class BenchmarkResult:
    size: int
    structure: str
    insert_time_ms: float
    search_time_ms: float
    delete_time_ms: float
    range_time_ms: float
    peak_memory_kb: float


class PerformanceAnalyzer:
    """Benchmarks B+ tree versus a brute-force baseline."""

    def __init__(self, order: int = 16, seed: int = 42) -> None:
        self.order = order
        self.random = random.Random(seed)

    def run(self, sizes: list[int], searches: int = 500, deletes: int = 200, ranges: int = 200) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []

        for size in sizes:
            keys = list(range(size))
            self.random.shuffle(keys)
            search_keys = self.random.sample(keys, min(searches, len(keys)))
            delete_keys = self.random.sample(keys, min(deletes, len(keys)))
            range_pairs = self._build_ranges(size=size, count=ranges)

            results.append(
                self._benchmark_structure(
                    name="BPlusTree",
                    structure=BPlusTree(order=self.order),
                    keys=keys,
                    search_keys=search_keys,
                    delete_keys=delete_keys,
                    range_pairs=range_pairs,
                )
            )

            results.append(
                self._benchmark_structure(
                    name="BruteForceDB",
                    structure=BruteForceDB(),
                    keys=keys,
                    search_keys=search_keys,
                    delete_keys=delete_keys,
                    range_pairs=range_pairs,
                )
            )

        return results

    def to_rows(self, results: list[BenchmarkResult]) -> list[dict[str, Any]]:
        return [
            {
                "size": row.size,
                "structure": row.structure,
                "insert_time_ms": row.insert_time_ms,
                "search_time_ms": row.search_time_ms,
                "delete_time_ms": row.delete_time_ms,
                "range_time_ms": row.range_time_ms,
                "peak_memory_kb": row.peak_memory_kb,
            }
            for row in results
        ]

    def _benchmark_structure(
        self,
        name: str,
        structure,
        keys: list[int],
        search_keys: list[int],
        delete_keys: list[int],
        range_pairs: list[tuple[int, int]],
    ) -> BenchmarkResult:
        tracemalloc.start()

        insert_time_ms = self._measure(lambda: self._bulk_insert(structure, keys))
        search_time_ms = self._measure(lambda: self._bulk_search(structure, search_keys))
        range_time_ms = self._measure(lambda: self._bulk_range(structure, range_pairs))
        delete_time_ms = self._measure(lambda: self._bulk_delete(structure, delete_keys))

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return BenchmarkResult(
            size=len(keys),
            structure=name,
            insert_time_ms=insert_time_ms,
            search_time_ms=search_time_ms,
            delete_time_ms=delete_time_ms,
            range_time_ms=range_time_ms,
            peak_memory_kb=peak / 1024,
        )

    @staticmethod
    def _measure(func) -> float:
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        return (end - start) * 1000

    @staticmethod
    def _bulk_insert(structure, keys: list[int]) -> None:
        for key in keys:
            structure.insert(key, {"id": key})

    @staticmethod
    def _bulk_search(structure, keys: list[int]) -> None:
        for key in keys:
            structure.search(key)

    @staticmethod
    def _bulk_delete(structure, keys: list[int]) -> None:
        for key in keys:
            structure.delete(key)

    @staticmethod
    def _bulk_range(structure, ranges: list[tuple[int, int]]) -> None:
        for start, end in ranges:
            structure.range_query(start, end)

    def _build_ranges(self, size: int, count: int) -> list[tuple[int, int]]:
        pairs: list[tuple[int, int]] = []
        max_key = max(size - 1, 0)
        for _ in range(count):
            a = self.random.randint(0, max_key)
            b = self.random.randint(0, max_key)
            pairs.append((min(a, b), max(a, b)))
        return pairs
