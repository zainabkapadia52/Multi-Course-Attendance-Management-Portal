from __future__ import annotations
from typing import Any, TYPE_CHECKING
from .conditions import (
    Condition, LeafCondition,
    AndCondition, OrCondition, NotCondition,
)

if TYPE_CHECKING:
    from table import Table


class Query:
    """
    Fluent WHERE query builder for a Table.

    Usage:
        results = table.where("age", ">", 25) \\
                       .and_("active", "=", True) \\
                       .fetch()

    Execution strategy:
        1. Inspect condition tree for any LeafCondition on the pk column
           with an index-friendly operator (=, <, >, <=, >=, BETWEEN, IN).
        2. If found -> use B+ tree (find / range_find) to get candidates.
        3. Otherwise -> full scan via table.all_rows().
        4. Apply full condition tree as final filter on all candidates.

    Index-friendly operators on pk:
        =         -> table.find(pk)
        BETWEEN   -> table.range_find(low, high)
        >, >=     -> table.range_find(val, MAX_INT)
        <, <=     -> table.range_find(MIN_INT, val)
        IN        -> one table.find(pk) per value

    Non-index operators (always full scan):
        !=, NOT IN, IS NULL, IS NOT NULL, any non-pk column
    """

    _MIN = -(2 ** 31)
    _MAX =   2 ** 31

    def __init__(self, table: "Table", condition: Condition) -> None:
        self._table     = table
        self._condition = condition

    # ------------------------------------------------------------------
    # Fluent combinators
    # ------------------------------------------------------------------

    def and_(self, column: str, op: str, value: Any = None) -> "Query":
        new_cond = LeafCondition(column, op, value)
        return Query(self._table, AndCondition(self._condition, new_cond))

    def or_(self, column: str, op: str, value: Any = None) -> "Query":
        new_cond = LeafCondition(column, op, value)
        return Query(self._table, OrCondition(self._condition, new_cond))

    def and_not(self, column: str, op: str, value: Any = None) -> "Query":
        new_cond = LeafCondition(column, op, value)
        return Query(self._table, AndCondition(self._condition, NotCondition(new_cond)))

    def or_not(self, column: str, op: str, value: Any = None) -> "Query":
        new_cond = LeafCondition(column, op, value)
        return Query(self._table, OrCondition(self._condition, NotCondition(new_cond)))

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def fetch(self) -> list[dict[str, Any]]:
        """
        Execute the query and return matching rows.

        Steps:
            1. Try to extract a pk-based index hint from condition tree
            2. Use index to get candidates if possible, else full scan
            3. Filter all candidates through the full condition tree
        """
        candidates = self._get_candidates()
        return [row for row in candidates if self._condition.evaluate(row)]

    def count(self) -> int:
        """Return number of matching rows."""
        return len(self.fetch())

    def first(self) -> dict[str, Any] | None:
        """Return first matching row or None."""
        results = self.fetch()
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Candidate generation  (index vs full scan decision)
    # ------------------------------------------------------------------

    def _get_candidates(self) -> list[dict[str, Any]]:
        """
        Try to use the pk index to narrow candidates.
        Falls back to full scan if no pk condition found.
        """
        pk   = self._table.primary_key
        hint = self._extract_pk_hint(self._condition, pk)

        if hint is None:
            return self._table.all_rows()

        op, value = hint

        if op == "=":
            row = self._table.find(value)
            return [row] if row is not None else []

        if op == "IN":
            rows = []
            for v in value:
                row = self._table.find(v)
                if row is not None:
                    rows.append(row)
            return rows

        if op == "BETWEEN":
            low, high = value
            return self._table.range_find(low, high)

        if op == ">":
            return self._table.range_find(value + 1, self._MAX)

        if op == ">=":
            return self._table.range_find(value, self._MAX)

        if op == "<":
            return self._table.range_find(self._MIN, value - 1)

        if op == "<=":
            return self._table.range_find(self._MIN, value)

        return self._table.all_rows()

    def _extract_pk_hint(
        self,
        condition: Condition,
        pk: str,
    ) -> tuple[str, Any] | None:
        """
        Walk the condition tree looking for a single LeafCondition
        on the pk column with an index-friendly operator.

        Rules:
            - Only extract from AND branches — narrowing candidates is
              safe under AND (we still filter everything at the end).
            - Never extract from OR branches — under OR we'd miss rows
              that satisfy the other branch, so full scan is required.
            - NOT branches — never extract, inversion breaks range logic.

        Returns (op, value) if found, None otherwise.
        """
        if isinstance(condition, LeafCondition):
            if condition.column == pk and condition.op in (
                "=", ">", ">=", "<", "<=", "BETWEEN", "IN"
            ):
                return condition.op, condition.value
            return None

        if isinstance(condition, AndCondition):
            left_hint = self._extract_pk_hint(condition.left, pk)
            if left_hint is not None:
                return left_hint
            return self._extract_pk_hint(condition.right, pk)

        # OrCondition, NotCondition — cannot safely use index
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Query(table={self._table.name!r}, condition={self._condition!r})"