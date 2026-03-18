from __future__ import annotations

from .table import Table


class DatabaseManager:
    """Manages multiple in-memory tables."""

    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}

    def create_table(self, table_name: str, order: int = 4) -> Table:
        if table_name in self._tables:
            raise ValueError(f"Table '{table_name}' already exists")
        table = Table(name=table_name, order=order)
        self._tables[table_name] = table
        return table

    def drop_table(self, table_name: str) -> bool:
        return self._tables.pop(table_name, None) is not None

    def get_table(self, table_name: str) -> Table:
        if table_name not in self._tables:
            raise KeyError(f"Table '{table_name}' does not exist")
        return self._tables[table_name]

    def list_tables(self) -> list[str]:
        return sorted(self._tables.keys())
