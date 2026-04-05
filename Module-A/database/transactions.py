from __future__ import annotations
import itertools
from typing import Any
from .wal import OP_INSERT, OP_UPDATE, OP_DELETE


# Global transaction id counter — each BEGIN gets a unique positive int.
# TXN_AUTO = 0 is reserved for auto-commit so we start from 1.
_txn_id_counter = itertools.count(1)


class Transaction:
    """
    Manages a single transaction across one or more Table objects.

    Usage:
        txn = Transaction(users_table, orders_table)
        txn.begin()
        try:
            txn.insert(users_table,  {"id": 1, "name": "Alice", ...})
            txn.insert(orders_table, {"id": 10, "user_id": 1, ...})
            txn.commit()
        except Exception:
            txn.rollback()
            raise

    Rules:
        - Single-threaded only. No locking — do not mix with auto-commit
          calls on the same tables from other threads during a transaction.
        - Each Transaction instance is single-use: begin -> commit/rollback.
          Create a new Transaction for the next operation.
        - Operations on tables not passed to __init__ are rejected.

    Internals:
        - begin()  : assign a unique txn_id
        - insert / update / delete : call table._insert_txn etc.,
                                     which append to WAL only (heap untouched)
        - commit() : for each table, call wal.get_pending(txn_id),
                     apply each entry to heap via table.apply_txn_entry()
        - rollback(): for each table, call table.revert_txn(txn_id),
                      which marks WAL entries ROLLEDBACK and rebuilds index
    """

    def __init__(self, *tables) -> None:
        if not tables:
            raise ValueError("Transaction requires at least one Table")

        self._tables    = list(tables)
        self._txn_id: int | None = None
        self._active    = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def begin(self) -> None:
        """Open the transaction. Must be called before any DML."""
        if self._active:
            raise RuntimeError("Transaction already active. Commit or rollback first.")
        self._txn_id = next(_txn_id_counter)
        self._active = True

    def commit(self) -> None:
        """
        Apply all staged WAL entries to heap across all tables, in order.

        For each table:
            1. get_pending(txn_id)  -> list of (wal_idx, op, slot, data)
            2. apply each to heap via table.apply_txn_entry()
               which writes to heap + marks WAL entry committed
        """
        self._assert_active()

        for table in self._tables:
            table._wal.write_commit_intent(self._txn_id)

        for table in self._tables:
            pending = table._wal.get_pending(self._txn_id)
            for wal_idx, op, slot, data in pending:
                table.apply_txn_entry(op, slot, data, wal_idx)

        for table in self._tables:
            table._wal.mark_intent_committed(self._txn_id)

        self._active = False

    def rollback(self) -> None:
        """
        Discard all staged WAL entries. Heap was never touched.

        For each table:
            1. mark WAL entries for this txn as ROLLEDBACK
            2. rebuild in-memory index from heap (undo index mutations)
        """
        self._assert_active()

        for table in self._tables:
            table.revert_txn(self._txn_id)

        self._active = False

    # ------------------------------------------------------------------
    # DML — mirrors Table's public API but routes through txn path
    # ------------------------------------------------------------------

    def insert(self, table, row: dict[str, Any]) -> None:
        """Stage an insert on table within this transaction."""
        self._assert_active()
        self._assert_enrolled(table)
        table._insert_txn(row, self._txn_id)

    def update(self, table, pk: Any, changes: dict[str, Any]) -> bool:
        """Stage an update on table within this transaction."""
        self._assert_active()
        self._assert_enrolled(table)
        return table._update_txn(pk, changes, self._txn_id)

    def delete(self, table, pk: Any) -> bool:
        """Stage a delete on table within this transaction."""
        self._assert_active()
        self._assert_enrolled(table)
        return table._delete_txn(pk, self._txn_id)

    def find(self, table, pk: Any):
        """
        Read within the transaction.
        Reads from heap — staged but uncommitted inserts are visible
        via the index (updated in _insert_txn) but the heap slot was
        not yet written, so this returns None for staged inserts.

        For true dirty reads within a txn, caller should track staged
        rows themselves. This is intentional — heap is source of truth.
        """
        self._assert_active()
        self._assert_enrolled(table)
        return table.find(pk)

    # ------------------------------------------------------------------
    # Context manager support  (with Transaction(...) as txn)
    # ------------------------------------------------------------------

    def __enter__(self) -> "Transaction":
        self.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False    # do not suppress exceptions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_active(self) -> None:
        if not self._active:
            raise RuntimeError("No active transaction. Call begin() first.")

    def _assert_enrolled(self, table) -> None:
        if table not in self._tables:
            raise ValueError(
                f"Table '{table.name}' was not enrolled in this transaction. "
                f"Pass it to Transaction(...) at construction time."
            )

    def __repr__(self) -> str:
        state = f"txn_id={self._txn_id}" if self._active else "inactive"
        tables = ", ".join(t.name for t in self._tables)
        return f"Transaction({state}, tables=[{tables}])"