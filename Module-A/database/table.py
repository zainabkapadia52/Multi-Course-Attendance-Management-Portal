"""
table.py
--------
Basic Table abstraction wrapping a BPlusTree.

Each Table represents one relation. The primary key field is used
as the B+ Tree key; the full record dict is stored as the value.
"""

from __future__ import annotations
from bplustree import BPlusTree


class Table:
    def __init__(self, name: str, primary_key: str, order: int = 4) -> None:
        self.name = name
        self.primary_key = primary_key
        self._tree = BPlusTree(order=order)

    def insert(self, record: dict) -> None:
        key = int(record[self.primary_key])
        self._tree.insert(key, record)

    def get(self, key: int) -> dict | None:
        return self._tree.search(key)

    def update(self, key: int, new_record: dict) -> bool:
        if self._tree.search(key) is None:
            return False
        self._tree.update(key, new_record)
        return True

    def delete(self, key: int) -> bool:
        return self._tree.delete(key)

    def all(self) -> list[dict]:
        return [v for _, v in self._tree.get_all()]

    def __repr__(self) -> str:
        return f"Table(name={self.name!r}, pk={self.primary_key!r})"