from __future__ import annotations
from typing import Any

# Expose everything a user needs to build a DB securely from one file
from .table import Table
from .column import Column
from .join import Join
from .transactions import Transaction

class DatabaseManager:
    """
    Central orchestrator for the Database Engine.
    Handles table creation, drops, cross-table queries (Joins), and Transactions.
    """

    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}

    def create_table(self, table_name: str, primary_key: str, schema: list[Column], order: int = 4) -> Table:
        """Creates a table, tracks it, and immediately returns it for data population."""
        if table_name in self._tables:
            raise ValueError(f"Table '{table_name}' already exists")
        
        table = Table(name=table_name, primary_key=primary_key, schema=schema, order=order)
        self._tables[table_name] = table
        return table

    def drop_table(self, table_name: str) -> bool:
        """Removes the table from management and cleans up its disk files."""
        table = self._tables.pop(table_name, None)
        if table is not None:
            table.close()
            import os
            # drop associated files from disk
            for ext in (".heap", ".wal", ".meta.json"):
                path = f"{table_name}{ext}"
                if os.path.exists(path):
                    os.remove(path)
            return True
        return False

    def get_table(self, table_name: str) -> Table:
        """Retrieves an existing active table."""
        if table_name not in self._tables:
            raise KeyError(f"Table '{table_name}' does not exist")
        return self._tables[table_name]

    def list_tables(self) -> list[str]:
        return sorted(self._tables.keys())

    # ------------------------------------------------------------- #
    # RELATIONSHIPS & ADVANCED QUERY EXPOSURE
    # ------------------------------------------------------------- #
    def join(self, left_table: str | Table, right_table: str | Table) -> Join:
        """
        Starts a JOIN operation between two tables. 
        Returns a customizable `Join` query builder object.
        """
        left = self.get_table(left_table) if isinstance(left_table, str) else left_table
        right = self.get_table(right_table) if isinstance(right_table, str) else right_table
        return Join(left, right)

    def transaction(self, *tables: str | Table) -> Transaction:
        """
        Starts an ACID transaction safely bounding all operations across designated tables.
        """
        resolved_tables = [self.get_table(t) if isinstance(t, str) else t for t in tables]
        return Transaction(*resolved_tables)
