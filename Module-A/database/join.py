from __future__ import annotations
from typing import Any, TYPE_CHECKING
from .conditions import Condition, LeafCondition, AndCondition

if TYPE_CHECKING:
    from table import Table


# Join types
INNER = "INNER"
LEFT  = "LEFT"


class Join:
    """
    Join two tables on a condition.

    Strategy (auto-selected):
        if right_col == right_table.primary_key:
            Index Nested Loop Join  — O(n log m)
            for each left row, call right_table.find(join_val) directly
        else:
            Nested Loop Join        — O(n * m)
            for each left row, scan all right rows and match

    Usage:
        # INNER JOIN (default)
        result = Join(orders, users) \\
            .on("user_id", "id") \\
            .fetch()

        # LEFT JOIN
        result = Join(orders, users) \\
            .on("user_id", "id") \\
            .left() \\
            .fetch()

        # with WHERE filter on left table
        result = Join(orders, users) \\
            .on("user_id", "id") \\
            .where("amount", ">", 100) \\
            .fetch()

    Result:
        List of merged dicts. If both tables share a column name,
        left table column keeps its name, right table column gets
        prefixed with right_table.name:
            {"order_id": 1, "user_id": 1, "users.id": 1, "users.name": "Alice"}

    Foreign key reuse:
        FK constraints internally call Join._execute() directly,
        passing the relevant rows to check/cascade without re-fetching.
    """

    def __init__(self, left: "Table", right: "Table") -> None:
        self._left       = left
        self._right      = right
        self._left_col:  str | None = None
        self._right_col: str | None = None
        self._join_type  = INNER
        self._condition: Condition | None = None   # optional WHERE on left rows

    # ------------------------------------------------------------------
    # Fluent builder
    # ------------------------------------------------------------------

    def on(self, left_col: str, right_col: str) -> "Join":
        """
        Specify join columns.
            left_col  : column in left table
            right_col : column in right table
        """
        if left_col not in self._left.schema:
            raise ValueError(f"Column '{left_col}' not in table '{self._left.name}'")
        if right_col not in self._right.schema:
            raise ValueError(f"Column '{right_col}' not in table '{self._right.name}'")

        self._left_col  = left_col
        self._right_col = right_col
        return self

    def inner(self) -> "Join":
        """INNER JOIN — only rows with a match on both sides."""
        self._join_type = INNER
        return self

    def left(self) -> "Join":
        """
        LEFT JOIN — all left rows, matched right row or None.
        Unmatched left rows get None for all right columns.
        """
        self._join_type = LEFT
        return self

    def where(self, column: str, op: str, value: Any = None) -> "Join":
        """
        Filter left table rows before joining.
        Reduces the number of join iterations.
        """
        new_cond = LeafCondition(column, op, value)
        if self._condition is None:
            self._condition = new_cond
        else:
            self._condition = AndCondition(self._condition, new_cond)
        return self

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def fetch(self) -> list[dict[str, Any]]:
        """Execute the join and return merged rows."""
        self._assert_ready()

        # Get left rows — apply WHERE filter if any
        if self._condition is not None:
            left_rows = [
                row for row in self._left.all_rows()
                if self._condition.evaluate(row)
            ]
        else:
            left_rows = self._left.all_rows()

        # Auto-select strategy based on right join column
        if self._right_col == self._right.primary_key:
            return self._index_nested_loop(left_rows)
        elif self._right_col in self._right._secondary_indexes:
            return self._secondary_index_join(left_rows)
        else:
            return self._nested_loop(left_rows)

    def _index_nested_loop(self, left_rows: list[dict]) -> list[dict]:
        """
        O(n log m) — for each left row, use right table's pk index.
        Used when right_col is the right table's primary key.
        """
        results = []

        for left_row in left_rows:
            join_val  = left_row.get(self._left_col)
            right_row = self._right.find(join_val) if join_val is not None else None

            if right_row is not None:
                results.append(self._merge(left_row, right_row))
            elif self._join_type == LEFT:
                results.append(self._merge(left_row, None))

        return results

    def _secondary_index_join(self, left_rows: list[dict]) -> list[dict]:
        """
        O(n log m + j) — use right table's secondary index.
        Used when right_col has a secondary index.
        """
        results = []
        idx = self._right._secondary_indexes[self._right_col]

        for left_row in left_rows:
            join_val = left_row.get(self._left_col)
            matched  = False

            if join_val is not None:
                right_pks = idx.get_eq(join_val)
                for pk in right_pks:
                    right_row = self._right.find(pk)
                    if right_row is not None:
                        results.append(self._merge(left_row, right_row))
                        matched = True

            if not matched and self._join_type == LEFT:
                results.append(self._merge(left_row, None))

        return results

    def _nested_loop(self, left_rows: list[dict]) -> list[dict]:
        """
        O(n * m) — fallback when right_col is not the pk.
        Scans all right rows for each left row.
        """
        right_rows = self._right.all_rows()
        results    = []

        for left_row in left_rows:
            join_val = left_row.get(self._left_col)
            matched  = False

            for right_row in right_rows:
                if right_row.get(self._right_col) == join_val:
                    results.append(self._merge(left_row, right_row))
                    matched = True

            if not matched and self._join_type == LEFT:
                results.append(self._merge(left_row, None))

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merge(
        self,
        left_row: dict[str, Any],
        right_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Merge left and right row into a single dict.

        Collision resolution:
            If both tables have a column with the same name,
            right table column is prefixed with "{right_table_name}."
            Left table columns always keep their original names.

        Example:
            left:  {"id": 1, "user_id": 1, "amount": 250.0}
            right: {"id": 1, "name": "Alice", "age": 30}
            merged: {"id": 1, "user_id": 1, "amount": 250.0,
                     "users.id": 1, "users.name": "Alice", "users.age": 30}
        """
        merged = dict(left_row)

        if right_row is None:
            # LEFT JOIN with no match — fill right columns with None
            for col in self._right.schema:
                key = f"{self._right.name}.{col}" if col in merged else col
                merged[key] = None
            return merged

        for col, val in right_row.items():
            key = f"{self._right.name}.{col}" if col in merged else col
            merged[key] = val

        return merged

    def _assert_ready(self) -> None:
        if self._left_col is None or self._right_col is None:
            raise RuntimeError("Call .on(left_col, right_col) before .fetch()")

    def __repr__(self) -> str:
        return (
            f"Join({self._left.name!r} {self._join_type} JOIN {self._right.name!r} "
            f"ON {self._left_col}={self._right_col})"
        )