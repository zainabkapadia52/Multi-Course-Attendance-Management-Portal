from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


# ------------------------------------------------------------------
# Supported operators for leaf conditions
# ------------------------------------------------------------------

VALID_OPS = {"=", "!=", "<", ">", "<=", ">=", "BETWEEN", "IN", "NOT IN", "IS NULL", "IS NOT NULL"}


# ------------------------------------------------------------------
# Base
# ------------------------------------------------------------------

class Condition(ABC):
    """
    Base class for all condition nodes.
    Every node must implement evaluate(row) -> bool.

    Tree structure:
        LeafCondition          — single column check
        AndCondition(l, r)     — l AND r
        OrCondition(l, r)      — l OR r
        NotCondition(inner)    — NOT inner
    """

    @abstractmethod
    def evaluate(self, row: dict[str, Any]) -> bool:
        """Return True if this row satisfies the condition."""
        ...

    # ------------------------------------------------------------------
    # Fluent combinators — let callers write:
    #     Condition(...).and_(Condition(...)).or_(Condition(...))
    # ------------------------------------------------------------------

    def and_(self, other: "Condition") -> "AndCondition":
        return AndCondition(self, other)

    def or_(self, other: "Condition") -> "OrCondition":
        return OrCondition(self, other)

    def not_(self) -> "NotCondition":
        return NotCondition(self)


# ------------------------------------------------------------------
# Leaf — single column condition
# ------------------------------------------------------------------

class LeafCondition(Condition):
    """
    A single predicate on one column.

    Supported ops:
        =, !=, <, >, <=, >=    — standard comparison
        BETWEEN                 — value is (low, high) tuple, inclusive
        IN                      — value is a list/set of allowed values
        NOT IN                  — value is a list/set of disallowed values
        IS NULL                 — no value argument needed
        IS NOT NULL             — no value argument needed

    Examples:
        LeafCondition("age",   ">",        25)
        LeafCondition("age",   "BETWEEN",  (20, 30))
        LeafCondition("id",    "IN",       [1, 2, 3])
        LeafCondition("id",    "NOT IN",   [4, 5])
        LeafCondition("score", "IS NULL")
        LeafCondition("score", "IS NOT NULL")
    """

    def __init__(self, column: str, op: str, value: Any = None) -> None:
        op = op.upper().strip()
        if op not in VALID_OPS:
            raise ValueError(f"Unsupported operator '{op}'. Valid: {VALID_OPS}")

        if op == "BETWEEN":
            if (not isinstance(value, (list, tuple))) or len(value) != 2:
                raise ValueError("BETWEEN requires a (low, high) tuple or list")

        if op in ("IN", "NOT IN"):
            if not isinstance(value, (list, set, tuple)):
                raise ValueError(f"{op} requires a list, set, or tuple of values")
            value = set(value)      # convert to set for O(1) lookup

        if op in ("IS NULL", "IS NOT NULL") and value is not None:
            raise ValueError(f"'{op}' does not take a value argument")

        self.column = column
        self.op     = op
        self.value  = value

    def evaluate(self, row: dict[str, Any]) -> bool:
        if self.column not in row:
            raise KeyError(f"Column '{self.column}' not found in row")

        col_val = row[self.column]

        if self.op == "IS NULL":
            return col_val is None

        if self.op == "IS NOT NULL":
            return col_val is not None

        # For all other ops, NULL propagates as False (SQL semantics)
        if col_val is None:
            return False

        if self.op == "=":
            return col_val == self.value

        if self.op == "!=":
            return col_val != self.value

        if self.op == "<":
            return col_val < self.value

        if self.op == ">":
            return col_val > self.value

        if self.op == "<=":
            return col_val <= self.value

        if self.op == ">=":
            return col_val >= self.value

        if self.op == "BETWEEN":
            low, high = self.value
            return low <= col_val <= high

        if self.op == "IN":
            return col_val in self.value

        if self.op == "NOT IN":
            return col_val not in self.value

        raise RuntimeError(f"Unhandled operator '{self.op}'")  # should never reach

    def __repr__(self) -> str:
        if self.op in ("IS NULL", "IS NOT NULL"):
            return f"{self.column} {self.op}"
        return f"{self.column} {self.op} {self.value!r}"


# ------------------------------------------------------------------
# Compound conditions
# ------------------------------------------------------------------

class AndCondition(Condition):
    def __init__(self, left: Condition, right: Condition) -> None:
        self.left  = left
        self.right = right

    def evaluate(self, row: dict[str, Any]) -> bool:
        return self.left.evaluate(row) and self.right.evaluate(row)

    def __repr__(self) -> str:
        return f"({self.left!r} AND {self.right!r})"


class OrCondition(Condition):
    def __init__(self, left: Condition, right: Condition) -> None:
        self.left  = left
        self.right = right

    def evaluate(self, row: dict[str, Any]) -> bool:
        return self.left.evaluate(row) or self.right.evaluate(row)

    def __repr__(self) -> str:
        return f"({self.left!r} OR {self.right!r})"


class NotCondition(Condition):
    def __init__(self, inner: Condition) -> None:
        self.inner = inner

    def evaluate(self, row: dict[str, Any]) -> bool:
        return not self.inner.evaluate(row)

    def __repr__(self) -> str:
        return f"(NOT {self.inner!r})"