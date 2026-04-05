from __future__ import annotations
import json
import os
import threading
from typing import Any, TYPE_CHECKING
from .column import Column
from .bplustree import BPlusTree
from .heapfile import HeapFile
from .wal import WALFile, OP_INSERT, OP_UPDATE, OP_DELETE, TXN_AUTO
from .secondaryindex import SecondaryIndex
from .foreignkey import ForeignKey

if TYPE_CHECKING:
    from .query import Query


class Table:
    """
    Table backed by:
      - HeapFile   : fixed-width binary file on disk (source of truth)
      - WALFile    : binary write-ahead log (crash safety)
      - BPlusTree  : in-RAM primary key index  pk -> slot_id
      - meta JSON  : bookkeeping only (schema, next_slot, free_list)
      - Lock       : one lock per table for thread-safe auto-commit 

    Two write modes:

    Auto-commit  (normal usage, thread-safe):
        insert / update / delete acquire the table lock and do:
            1. append to WAL  (TXN_AUTO, uncommitted)
            2. write to heap
            3. mark WAL entry committed
        Each operation is fully atomic from the caller's perspective.

    Transaction mode  (single-threaded, driven by Transaction class):  
        _insert_txn / _update_txn / _delete_txn do:
            1. append to WAL  (txn_id, uncommitted)
            -- stop here, do NOT touch heap --
        Transaction.commit() later calls apply_txn_entry() per entry.
        Transaction.rollback() calls wal.mark_rolledback(txn_id).

    Startup / crash recovery:
        1. WAL replay  -> apply any uncommitted TXN_AUTO entries to heap
        2. Delete WAL  -> data is consistent, fresh WAL opened
        3. Rebuild index from heap
    """

    #can we combine transaction with multiple users (remcheck)

    def __init__(
        self,
        name: str,
        primary_key: str,
        schema: list[Column],
        order: int = 4,
    ) -> None:
        self.name        = name
        self.primary_key = primary_key
        self._meta_path  = f"{name}.meta.json"
        self._heap_path  = f"{name}.heap"
        self._wal_path   = f"{name}.wal"

        self.schema: dict[str, Column] = {col.name: col for col in schema}
        if self.primary_key not in self.schema:
            raise ValueError(f"Primary key '{primary_key}' not in schema")

        self._index     = BPlusTree(order=order)
        self._next_slot = 0
        self._free_list: list[int] = []
        self._lock      = threading.Lock()      # protects auto-commit path

        # Foreign Key & Secondary Index tracking
        self._secondary_indexes: dict[str, SecondaryIndex] = {}
        self._foreign_keys: list[ForeignKey] = []
        self._referenced_by: list[tuple[Table, ForeignKey]] = []  # Allows parents to trigger cascades on children

        if os.path.exists(self._meta_path):
            self._load_meta()

        self._heap = HeapFile(self._heap_path, self.schema)
        self._wal  = WALFile(self._wal_path, self._heap.record_size())

        self._startup()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _startup(self) -> None:
        """
        1. Replay uncommitted TXN_AUTO WAL entries onto heap.
           (Uncommitted txn entries are skipped — txn never committed.)
        2. Delete WAL — heap is consistent. (remcheck) -> dont delete rather append ahead with offset, so that we have logs for all the operations that have been performed over database
        3. Open fresh WAL for this session. 
        4. Rebuild B+ tree index from heap.
        """

        to_apply = self._wal.replay()

        for op, slot, data in to_apply:
            if op in (OP_INSERT, OP_UPDATE):
                self._heap.write_raw(slot, data)
            elif op == OP_DELETE:
                self._heap.delete(slot)

        self._wal.delete()
        self._wal = WALFile(self._wal_path, self._heap.record_size())

        self._rebuild_index()

    # ------------------------------------------------------------------
    # Public API — auto-commit (thread-safe)
    # ------------------------------------------------------------------
    def create_index(self, col_name: str) -> None:
        """Create a secondary index on a column."""
        if col_name not in self.schema:
            raise KeyError(f"Column '{col_name}' not found for secondary index.")
        if col_name in self._secondary_indexes:
            return  # Already exists
        index = SecondaryIndex(col_name)
        self._secondary_indexes[col_name] = index

        # Populate from existing data
        free_set = set(self._free_list)
        for slot in range(self._next_slot):
            if slot in free_set:
                continue
            row = self._heap.read(slot)
            if row is not None:
                val = row.get(col_name)
                if val is not None:
                    index.insert(val, row[self.primary_key])
                
    def add_foreign_key(self, col_name: str, references: Table, ref_col: str = "id", on_delete: str = "RESTRICT", on_update: str = "RESTRICT") -> None:
        """Add a foreign key constraint and ensure secondary index exists."""
        if col_name not in self.schema:
            raise KeyError(f"Column '{col_name}' not found.")
        
        fk = ForeignKey(col_name, references, ref_col, on_delete, on_update)
        self._foreign_keys.append(fk)
        self.create_index(col_name)
        references._referenced_by.append((self, fk))

    def where(self, column: str, op: str, value: Any = None) -> Query:
        from .query import Query
        from .conditions import LeafCondition
        return Query(self, LeafCondition(column, op, value))

    def insert(self, row: dict[str, Any]) -> None:
        """Insert a new row. Thread-safe. Raises if pk already exists."""
        row = self._apply_defaults(row)
        self._validate_row(row)
        pk = self._extract_pk(row)

        # Check FK constraints
        for fk in self._foreign_keys:
            fk.check_insert(row)

        with self._lock:
            if self._index.search(pk) is not None:
                raise ValueError(f"Primary key {pk!r} already exists in '{self.name}'")

            slot = self._alloc_slot()
            data = self._heap.pack_row(row)

            wal_idx = self._wal.append(OP_INSERT, slot, data, TXN_AUTO)  # 1. WAL
            self._heap.write_raw(slot, data)                              # 2. heap
            self._wal.mark_committed(wal_idx)                             # 3. committed

            self._index.insert(pk, slot)
            
            # Update secondary indexes
            for col_name, idx in self._secondary_indexes.items():
                val = row.get(col_name)
                if val is not None:
                    idx.insert(val, pk)
                
            self._save_meta()

    def find(self, pk: Any) -> dict[str, Any] | None:
        """Exact lookup by primary key. Returns a copy or None."""
        with self._lock:
            slot = self._index.search(pk)
            if slot is None:
                return None
            return self._heap.read(slot)

    def update(self, pk: Any, changes: dict[str, Any]) -> bool:
        """
        Apply changes to the row with the given pk in-place.
        Only that one record is rewritten on disk.
        Returns True if found and updated, False if not found.
        """
        if self.primary_key in changes:
            raise ValueError("Cannot change the primary key via update()")
        self._validate_partial(changes)

        with self._lock:
            slot = self._index.search(pk)
            if slot is None:
                return False

            row = self._heap.read(slot)
            old_row = dict(row)
            row.update(changes)
            
            # Check FK constraints based on new row
            for fk in self._foreign_keys:
                if fk.col in changes:
                    fk.check_insert(row)

            # Apply Cascade updates if any children reference this table
            for child_table, fk in self._referenced_by:
                for col_name, new_val in changes.items():
                    if col_name == fk.ref_col:
                        fk.on_parent_update(child_table, old_row[col_name], new_val)

            data = self._heap.pack_row(row)

            wal_idx = self._wal.append(OP_UPDATE, slot, data, TXN_AUTO)  # 1. WAL
            self._heap.write_raw(slot, data)                              # 2. heap
            self._wal.mark_committed(wal_idx)                             # 3. committed
            
            # Update secondary indexes
            for col_name, idx in self._secondary_indexes.items():
                if col_name in changes:
                    old_val = old_row.get(col_name)
                    new_val = changes[col_name]
                    if old_val != new_val:
                        if old_val is not None:
                            idx.delete(old_val, pk)
                        if new_val is not None:
                            idx.insert(new_val, pk)
                        
            return True

    def delete(self, pk: Any) -> bool:
        """
        Delete the row with the given pk.
        Flips tombstone on disk, recycles the slot.
        Returns True if deleted, False if not found.
        """
        with self._lock:
            slot = self._index.search(pk)
            if slot is None:
                return False
                
            row = self._heap.read(slot)

            # Apply Cascade deletes if any children reference this table
            for child_table, fk in self._referenced_by:
                fk.on_parent_delete(child_table, row[fk.ref_col])

            empty = bytes(self._heap.record_size())
            wal_idx = self._wal.append(OP_DELETE, slot, empty, TXN_AUTO)  # 1. WAL
            self._heap.delete(slot)                                         # 2. heap
            self._wal.mark_committed(wal_idx)                               # 3. committed

            self._index.delete(pk)
            self._free_list.append(slot)
            
            # Update secondary indexes
            for col_name, idx in self._secondary_indexes.items():
                val = row.get(col_name)
                if val is not None:
                    idx.delete(val, pk)
                
            self._save_meta()
            return True

    def range_find(self, start_pk: Any, end_pk: Any) -> list[dict[str, Any]]:
        """Return all rows whose pk is in [start_pk, end_pk]."""
        with self._lock:
            results = self._index.range_query(start_pk, end_pk)
            return [self._heap.read(slot) for _, slot in results]

    def all_rows(self) -> list[dict[str, Any]]:
        """Return every row in primary-key order."""
        with self._lock:
            return [self._heap.read(slot) for _, slot in self._index.get_all()]

    def __len__(self) -> int:
        return self._next_slot - len(self._free_list)

    def __repr__(self) -> str:
        return f"Table(name={self.name!r}, pk={self.primary_key!r}, rows={len(self)})"

    def close(self) -> None:
        """Flush and close heap + WAL. Call before process exit."""
        self._heap.close()
        self._wal.close()

    # ------------------------------------------------------------------
    # Internal API — transaction path (called by Transaction only)
    # ------------------------------------------------------------------

    def _get_txn_row(self, slot: int, txn_id: int) -> dict[str, Any] | None:
        """
        Get the current state of a row within a transaction,
        merging uncommitted WAL changes over the heap data.
        """
        # Read base row from heap
        row = self._heap.read(slot)
        
        # Overlay pending changes from WAL for this transaction
        pending = self._wal.get_pending(txn_id)
        for _, op, s, data in pending:
            if s == slot:
                if op == OP_DELETE:
                    row = None
                elif op in (OP_INSERT, OP_UPDATE):
                    row = self._heap.unpack_row(data)
                    
        return row

    def _insert_txn(self, row: dict[str, Any], txn_id: int) -> int:
        """
        Stage an insert for txn_id. WAL only — heap untouched.
        Returns the allocated slot so Transaction can track it.
        Caller (Transaction) must hold no lock — single-threaded txn.
        """
        row = self._apply_defaults(row)
        self._validate_row(row)
        pk = self._extract_pk(row)

        # Check FK constraints
        for fk in self._foreign_keys:
            fk.check_insert(row)

        if self._index.search(pk) is not None:
            raise ValueError(f"Primary key {pk!r} already exists in '{self.name}'")

        slot = self._alloc_slot()
        data = self._heap.pack_row(row)
        self._wal.append(OP_INSERT, slot, data, txn_id)

        # Update index immediately so subsequent txn operations within
        # the same transaction can see this row (dirty read within txn)
        self._index.insert(pk, slot)
        
        # Update secondary indexes
        for col_name, idx in self._secondary_indexes.items():
            val = row.get(col_name)
            if val is not None:
                idx.insert(val, pk)
                
        return slot

    def _update_txn(self, pk: Any, changes: dict[str, Any], txn_id: int) -> bool:
        """
        Stage an update for txn_id. WAL only — heap untouched.
        Reads current heap value, merges changes, stages result.
        """
        if self.primary_key in changes:
            raise ValueError("Cannot change the primary key via update()")
        self._validate_partial(changes)

        slot = self._index.search(pk)
        if slot is None:
            return False

        row = self._get_txn_row(slot, txn_id)
        if row is None:
            return False

        old_row = dict(row)
        row.update(changes)
        
        # Check FK constraints based on new row
        for fk in self._foreign_keys:
            if fk.col in changes:
                fk.check_insert(row)

        # Apply Cascade updates if any children reference this table
        for child_table, fk in self._referenced_by:
            for col_name, new_val in changes.items():
                if col_name == fk.ref_col:
                    fk.on_parent_update(child_table, old_row[col_name], new_val, txn_id=txn_id)

        data = self._heap.pack_row(row)
        self._wal.append(OP_UPDATE, slot, data, txn_id)
        
        # Update secondary indexes immediately directly for dirty reads
        for col_name, idx in self._secondary_indexes.items():
            if col_name in changes:
                old_val = old_row.get(col_name)
                new_val = changes[col_name]
                if old_val != new_val:
                    if old_val is not None:
                        idx.delete(old_val, pk)
                    if new_val is not None:
                        idx.insert(new_val, pk)
                        
        return True

    def _delete_txn(self, pk: Any, txn_id: int) -> bool:
        """
        Stage a delete for txn_id. WAL only — heap untouched.
        Removes from index immediately so subsequent txn reads see it gone.
        """
        slot = self._index.search(pk)
        if slot is None:
            return False

        row = self._get_txn_row(slot, txn_id)
        if row is None:
            return False

        # Apply Cascade deletes if any children reference this table
        for child_table, fk in self._referenced_by:
            fk.on_parent_delete(child_table, row[fk.ref_col], txn_id=txn_id)

        empty = bytes(self._heap.record_size())
        self._wal.append(OP_DELETE, slot, empty, txn_id)

        self._index.delete(pk)
        self._free_list.append(slot)
        
        # Update secondary indexes immediately directly for dirty reads
        for col_name, idx in self._secondary_indexes.items():
            val = row.get(col_name)
            if val is not None:
                idx.delete(val, pk)

        return True

    def apply_txn_entry(self, op: int, slot: int, data: bytes, wal_idx: int) -> None:
        """
        Apply one committed WAL entry to heap + index.
        Called by Transaction.commit() for each pending entry.

        After writing to heap, marks the WAL entry committed.
        Index was already updated in _insert_txn / _delete_txn,
        so we only touch the heap here.
        """
        if op in (OP_INSERT, OP_UPDATE):
            self._heap.write_raw(slot, data)
        elif op == OP_DELETE:
            self._heap.delete(slot)

        self._wal.mark_committed(wal_idx)
        self._save_meta()

    def revert_txn(self, txn_id: int) -> None:
        """
        Undo in-memory index changes made during a rolled-back transaction.
        Heap was never touched so only the index needs fixing.
        Rebuilds index cleanly from heap (source of truth).
        Called by Transaction.rollback().
        """
        self._wal.mark_rolledback(txn_id)

        # Rebuild index from heap to undo any _insert_txn / _delete_txn
        # index mutations that happened during the transaction
        # `_rebuild_index` will clear the tree and secondary index trees
        # also restore free_list and next_slot from meta (pre-txn state)
        self._load_meta()
        self._rebuild_index()

    # ------------------------------------------------------------------
    # Meta persistence
    # ------------------------------------------------------------------

    def _save_meta(self) -> None:
        """Persist bookkeeping — schema, next_slot, free_list. NOT heap data."""
        data = {
            "primary_key": self.primary_key,
            "schema":      [col.to_dict() for col in self.schema.values()],
            "next_slot":   self._next_slot,
            "free_list":   self._free_list,
        }
        tmp = self._meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self._meta_path)

    def _load_meta(self) -> None:
        with open(self._meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._next_slot = data["next_slot"]
        self._free_list = data["free_list"]
        self.schema = {
            col["name"]: Column.from_dict(col)
            for col in data["schema"]
        }

    def _rebuild_index(self) -> None:
        """Scan every alive slot in heap and populate the B+ tree & secondary indexes."""
        # Clear existing indexes
        self._index = BPlusTree(order=self._index.order)
        for idx in self._secondary_indexes.values():
            idx.tree = BPlusTree(order=self._index.order)

        free_set = set(self._free_list)     # O(1) lookup vs O(n) list
        for slot in range(self._next_slot):
            if slot in free_set:
                continue
            row = self._heap.read(slot)
            if row is None:
                continue
            pk = row[self.primary_key]
            self._index.insert(pk, slot)
            
            # Rebuild secondary indexes
            for col_name, idx in self._secondary_indexes.items():
                val = row.get(col_name)
                if val is not None:
                    idx.insert(val, pk)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _alloc_slot(self) -> int:
        """Return next available slot, reusing freed slots first."""
        if self._free_list:
            return self._free_list.pop()
        slot = self._next_slot
        self._next_slot += 1
        return slot

    def _apply_defaults(self, row: dict) -> dict:
        row = dict(row)
        for name, col in self.schema.items():
            if name not in row and col.default is not None:
                row[name] = col.default
        return row

    def _validate_row(self, row: dict) -> None:
        for name, col in self.schema.items():
            col.validate(row.get(name))

    def _validate_partial(self, changes: dict) -> None:
        for name, value in changes.items():
            if name not in self.schema:
                raise KeyError(f"Column '{name}' does not exist in '{self.name}'")
            self.schema[name].validate(value)

    def _extract_pk(self, row: dict[str, Any]) -> Any:
        if self.primary_key not in row:
            raise KeyError(f"Row missing primary key '{self.primary_key}'")
        return row[self.primary_key]
    