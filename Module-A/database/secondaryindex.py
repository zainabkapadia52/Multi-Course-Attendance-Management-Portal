from __future__ import annotations
from typing import Any
from .bplustree import BPlusTree


class SecondaryIndex:
    """
    Secondary index on a non-primary-key column.

    Backed by a B+ tree with composite keys: (col_value, pk)
    Value stored is just pk (redundant but useful for retrieval).

    Why composite key:
        - Handles duplicate col_values naturally
        - (age=25, pk=1) and (age=25, pk=3) are distinct keys
        - Range scans work naturally via B+ tree leaf traversal
        - Exactly how real DBs implement secondary indexes (InnoDB, PostgreSQL)

    Example — index on "age":
        insert(age=25, pk=1)  ->  B+ tree key=(25, 1),  value=1
        insert(age=25, pk=3)  ->  B+ tree key=(25, 3),  value=3
        insert(age=30, pk=2)  ->  B+ tree key=(30, 2),  value=2

    Lookup age=25 returns pks [1, 3] via range_query((25, min), (25, max))
    Range age BETWEEN 25 AND 30 returns pks [1, 3, 2]
    """

    # Sentinels for range scan boundaries
    # We need a value smaller/larger than any possible pk
    _PK_MIN =  -(2 ** 31)   # smaller than any valid pk
    _PK_MAX =   (2 ** 31)   # larger than any valid pk

    def __init__(self, col_name: str, order: int = 4) -> None:
        self.col_name = col_name
        self._tree    = BPlusTree(order=order)

    # ------------------------------------------------------------------
    # Mutations  (called by Table on insert / update / delete)
    # ------------------------------------------------------------------

    def insert(self, col_value: Any, pk: Any) -> None:
        """Add a (col_value, pk) entry to the index."""
        self._tree.insert((col_value, pk), pk)

    def delete(self, col_value: Any, pk: Any) -> None:
        """Remove the (col_value, pk) entry from the index."""
        self._tree.delete((col_value, pk))

    def update(self, old_col_value: Any, new_col_value: Any, pk: Any) -> None:
        """
        Column value changed — remove old composite key, insert new one.
        Called by Table.update() when the indexed column is in changes.
        """
        self.delete(old_col_value, pk)
        self.insert(new_col_value, pk)

    # ------------------------------------------------------------------
    # Lookups  (used by Query optimizer)
    # ------------------------------------------------------------------

    def get_eq(self, col_value: Any) -> list[Any]:
        """
        Exact match: return all pks where col == col_value.
        Range scan from (col_value, PK_MIN) to (col_value, PK_MAX).
        """
        results = self._tree.range_query(
            (col_value, self._PK_MIN),
            (col_value, self._PK_MAX),
        )
        return [pk for _, pk in results]

    def get_range(self, low: Any, high: Any) -> list[Any]:
        """
        Range scan: return all pks where low <= col <= high.
        Range scan from (low, PK_MIN) to (high, PK_MAX).
        """
        results = self._tree.range_query(
            (low,  self._PK_MIN),
            (high, self._PK_MAX),
        )
        return [pk for _, pk in results]

    def get_lt(self, col_value: Any) -> list[Any]:
        """Return all pks where col < col_value."""
        # No clean lower bound — use a practical minimum sentinel
        results = self._tree.range_query(
            (self._PK_MIN, self._PK_MIN),
            (col_value,    self._PK_MIN),   # exclusive upper: stop just before col_value
        )
        # Filter out any entry where col_value == boundary (strict less than)
        return [pk for (cv, _), pk in results if cv < col_value]

    def get_lte(self, col_value: Any) -> list[Any]:
        """Return all pks where col <= col_value."""
        results = self._tree.range_query(
            (self._PK_MIN, self._PK_MIN),
            (col_value,    self._PK_MAX),
        )
        return [pk for _, pk in results]

    def get_gt(self, col_value: Any) -> list[Any]:
        """Return all pks where col > col_value."""
        results = self._tree.range_query(
            (col_value,    self._PK_MAX),   # start just after col_value
            (self._PK_MAX, self._PK_MAX),
        )
        return [pk for (cv, _), pk in results if cv > col_value]

    def get_gte(self, col_value: Any) -> list[Any]:
        """Return all pks where col >= col_value."""
        results = self._tree.range_query(
            (col_value,    self._PK_MIN),
            (self._PK_MAX, self._PK_MAX),
        )
        return [pk for _, pk in results]

    def get_in(self, values: set) -> list[Any]:
        """
        Return all pks where col IN values.
        One get_eq call per value, union results.
        """
        pks: list[Any] = []
        for v in values:
            pks.extend(self.get_eq(v))
        return pks

    # ------------------------------------------------------------------
    # Rebuild  (called by Table._rebuild_index on startup)
    # ------------------------------------------------------------------

    def rebuild(self, rows: list[dict[str, Any]], pk_col: str) -> None:
        """
        Rebuild the entire secondary index from a list of rows.
        Called once on startup after heap scan.
        """
        self._tree = BPlusTree(order=self._tree.order)
        for row in rows:
            col_value = row.get(self.col_name)
            pk        = row[pk_col]
            if col_value is not None:       # NULL values are not indexed
                self.insert(col_value, pk)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"SecondaryIndex(col={self.col_name!r})"