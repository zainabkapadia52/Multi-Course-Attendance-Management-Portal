from __future__ import annotations

from typing import Any


class BruteForceDB:
    """Simple linear baseline used for performance comparison."""

    def __init__(self) -> None:
        self.data: list[tuple[int, Any]] = []

    def insert(self, key: int, value: Any) -> None:
        for i, (existing_key, _) in enumerate(self.data):
            if existing_key == key:
                self.data[i] = (key, value)
                return
        self.data.append((key, value))

    def search(self, key: int) -> Any | None:
        for existing_key, value in self.data:
            if existing_key == key:
                return value
        return None

    def delete(self, key: int) -> bool:
        for i, (existing_key, _) in enumerate(self.data):
            if existing_key == key:
                del self.data[i]
                return True
        return False

    def update(self, key: int, value: Any) -> bool:
        for i, (existing_key, _) in enumerate(self.data):
            if existing_key == key:
                self.data[i] = (key, value)
                return True
        return False

    def range_query(self, start: int, end: int) -> list[tuple[int, Any]]:
        return [(k, v) for (k, v) in self.data if start <= k <= end]

    def get_all(self) -> list[tuple[int, Any]]:
        return list(self.data)
