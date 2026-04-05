from __future__ import annotations
import os
import struct



# ------------------------------------------------------------------
# Op codes
# ------------------------------------------------------------------

OP_INSERT = 0x01
OP_UPDATE = 0x02
OP_DELETE = 0x03
OP_COMMIT_INTENT = 0xFF

# ------------------------------------------------------------------
# Entry status flags  (stored in the `status` byte)
# ------------------------------------------------------------------

STATUS_UNCOMMITTED = 0x00   # operation in progress, not yet applied to heap
STATUS_COMMITTED   = 0x01   # applied to heap successfully
STATUS_ROLLEDBACK  = 0x02   # transaction was rolled back, never apply to heap

# ------------------------------------------------------------------
# Auto-commit pseudo txn_id
# ------------------------------------------------------------------

TXN_AUTO = 0                # reserved id for auto-commit operations

# ------------------------------------------------------------------
# Entry layout
# ------------------------------------------------------------------
#
#   [op      : 1 byte ]  OP_INSERT / OP_UPDATE / OP_DELETE
#   [slot    : 4 bytes]  heap slot id  (signed int)
#   [txn_id  : 4 bytes]  transaction id (0 = auto-commit)
#   [status  : 1 byte ]  STATUS_UNCOMMITTED / COMMITTED / ROLLEDBACK
#   [data    : N bytes]  packed row bytes from HeapFile.pack_row()
#                        (zeroed N bytes for DELETE — slot is enough)
#
# Fixed entry size = HEADER_SIZE + 1 + record_size
# Entry i starts at byte offset:  i * entry_size
#
# STATUS_OFFSET is the byte within an entry where the status flag lives.
# mark_committed / mark_rolledback seek directly to that byte — O(1).

HEADER_FORMAT  = "=BiI"                          # op(B) + slot(i) + txn_id(I)
HEADER_SIZE    = struct.calcsize(HEADER_FORMAT)  # 1 + 4 + 4 = 9 bytes
STATUS_OFFSET  = HEADER_SIZE                     # status byte sits at offset 9


class WALFile:
    """
    Binary write-ahead log for a single table.

    Supports two modes:

    Auto-commit  (txn_id = TXN_AUTO = 0):
        append() -> heap write -> mark_committed()
        Each operation is its own atomic unit.

    Transaction  (txn_id = some positive int):
        Multiple append() calls with the same txn_id.
        No heap writes until Transaction.commit() calls
        get_pending(txn_id) and applies them.
        On rollback, mark_rolledback(txn_id) flips all
        entries for that txn to STATUS_ROLLEDBACK.

    Startup / crash recovery:
        replay() scans all entries:
            STATUS_COMMITTED   -> already in heap, skip
            STATUS_ROLLEDBACK  -> intentionally discarded, skip
            STATUS_UNCOMMITTED -> crash happened mid-write, apply to heap
        After replay, WAL file is truncated and deleted.
        A fresh WAL is opened for the new session.
    """

    def __init__(self, filepath: str, record_size: int) -> None:
        self.filepath    = filepath
        self.record_size = record_size
        self.entry_size  = HEADER_SIZE + 1 + record_size   # +1 for status byte

        mode = "r+b" if os.path.exists(filepath) else "w+b"
        self._file = open(filepath, mode)

        # Count how many complete entries exist on disk
        self._file.seek(0, 2)
        file_size = self._file.tell()
        self._entry_count = file_size // self.entry_size

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def append(self, op: int, slot: int, data: bytes, txn_id: int = TXN_AUTO) -> int:
        """
        Append one uncommitted entry to the WAL.

        Args:
            op     : OP_INSERT / OP_UPDATE / OP_DELETE
            slot   : heap slot id this operation targets
            data   : packed row bytes (from HeapFile.pack_row())
                     pass bytes(record_size) for deletes
            txn_id : 0 for auto-commit, positive int for a transaction

        Returns:
            entry_idx : position of this entry in the WAL
                        pass back to mark_committed() after heap write
        """
        assert len(data) == self.record_size, (
            f"WAL data must be {self.record_size} bytes, got {len(data)}"
        )

        header = struct.pack(HEADER_FORMAT, op, slot, txn_id)
        entry  = header + bytes([STATUS_UNCOMMITTED]) + data

        self._file.seek(0, 2)           # always append
        self._file.write(entry)
        self._file.flush()              # fsync to OS buffer before heap write

        idx = self._entry_count
        self._entry_count += 1
        return idx

    def mark_committed(self, entry_idx: int) -> None:
        """
        Flip status byte of entry at entry_idx to STATUS_COMMITTED.
        Single byte seek + write — O(1).
        Called after the heap write succeeds.
        """
        self._write_status(entry_idx, STATUS_COMMITTED)

    def mark_rolledback(self, txn_id: int) -> None:
        """
        Flip status byte of ALL entries with this txn_id to STATUS_ROLLEDBACK.
        Called by Transaction.rollback().
        Heap was never touched for these entries so nothing to undo there.
        """
        for i in range(self._entry_count):
            offset = i * self.entry_size
            self._file.seek(offset)
            raw = self._file.read(self.entry_size)

            if len(raw) < self.entry_size:
                break

            _, _, entry_txn_id = struct.unpack_from(HEADER_FORMAT, raw, 0)
            if entry_txn_id == txn_id:
                self._write_status(i, STATUS_ROLLEDBACK)

    def write_commit_intent(self, txn_id: int) -> None:
        """
        Write a sentinel entry marking that this txn has been asked to commit.
        If crash happens after this but before all heap writes complete,
        replay will see this intent and finish the job.
        """
        header = struct.pack(HEADER_FORMAT, OP_COMMIT_INTENT, 0, txn_id)
        # entry  = header + bytes([STATUS_COMMITTED]) + bytes(self.record_size)
        entry  = header + bytes([STATUS_UNCOMMITTED]) + bytes(self.record_size)
        self._file.seek(0, 2)
        self._file.write(entry)
        self._file.flush()
        self._entry_count += 1

    def mark_intent_committed(self, txn_id: int) -> None:
        """
        Flip the COMMIT_INTENT entry for this txn_id to STATUS_COMMITTED.
        Called after all entries for this txn have been applied to heap.
        """
        for i in range(self._entry_count - 1, -1, -1):
            self._file.seek(i * self.entry_size)
            raw = self._file.read(self.entry_size)
            if len(raw) < self.entry_size:
                continue
            op, _, entry_txn_id = struct.unpack_from(HEADER_FORMAT, raw, 0)
            if op == OP_COMMIT_INTENT and entry_txn_id == txn_id:
                self._write_status(i, STATUS_COMMITTED)
                return

    # ------------------------------------------------------------------
    # Transaction support
    # ------------------------------------------------------------------

    def get_pending(self, txn_id: int) -> list[tuple[int, int, int, bytes]]:
        """
        Return all uncommitted entries for txn_id, in order.
        Used by Transaction.commit() to know what to apply to heap.

        Returns list of (entry_idx, op, slot, data).
        entry_idx is needed so commit() can mark each one committed
        after the heap write.
        """
        pending: list[tuple[int, int, int, bytes]] = []

        for i in range(self._entry_count):
            offset = i * self.entry_size
            self._file.seek(offset)
            raw = self._file.read(self.entry_size)

            if len(raw) < self.entry_size:
                break

            op, slot, entry_txn_id = struct.unpack_from(HEADER_FORMAT, raw, 0)
            status = raw[STATUS_OFFSET]
            data   = raw[STATUS_OFFSET + 1:]

            if entry_txn_id == txn_id and status == STATUS_UNCOMMITTED:
                pending.append((i, op, slot, data))

        return pending

    # ------------------------------------------------------------------
    # Startup replay  (called once on boot before anything else)
    # ------------------------------------------------------------------

    def replay(self) -> list[tuple[int, int, bytes]]:
        """
        Scan all WAL entries and return those that need to be applied to heap.

        Rules:
            STATUS_COMMITTED   -> already in heap, skip
            STATUS_ROLLEDBACK  -> intentionally discarded, skip
            STATUS_UNCOMMITTED -> crash happened between heap write and
                                  mark_committed, OR between WAL append
                                  and heap write.
                                  Apply to heap (idempotent).

        If a partial (truncated) entry is found, truncate the WAL file 
        at that point — everything after is garbage from a crash mid-write.

        Returns list of (op, slot, data) to apply, in order.
        """
        committed_txn_id: int | None = None
        if self._entry_count > 0:
            self._file.seek((self._entry_count - 1) * self.entry_size)
            raw = self._file.read(self.entry_size)
            if len(raw) == self.entry_size:
                op, _, txn_id = struct.unpack_from(HEADER_FORMAT, raw, 0)
                status = raw[STATUS_OFFSET]
                if op == OP_COMMIT_INTENT and status == STATUS_UNCOMMITTED:
                    committed_txn_id = txn_id

        to_apply: list[tuple[int, int, bytes]] = []

        for i in range(self._entry_count):
            self._file.seek(i * self.entry_size)
            raw = self._file.read(self.entry_size)

            if len(raw) < self.entry_size:
                self._file.truncate(i * self.entry_size)
                self._file.flush()
                self._entry_count = i
                break

            op, slot, txn_id = struct.unpack_from(HEADER_FORMAT, raw, 0)
            status = raw[STATUS_OFFSET]
            data   = raw[STATUS_OFFSET + 1:]

            if op == OP_COMMIT_INTENT:
                continue
            if status == STATUS_UNCOMMITTED:
                if txn_id == TXN_AUTO or txn_id == committed_txn_id:
                    to_apply.append((op, slot, data))

        return to_apply

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def delete(self) -> None:
        """
        Close and delete the WAL file.
        Called after startup replay verifies heap is consistent.
        A fresh WAL is opened by Table._startup() after this.
        """
        self._file.close()
        if os.path.exists(self.filepath):
            os.remove(self.filepath)

    def close(self) -> None:
        self._file.flush()
        self._file.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_status(self, entry_idx: int, status: int) -> None:
        """Seek to the status byte of entry_idx and write one byte."""
        offset = entry_idx * self.entry_size + STATUS_OFFSET
        self._file.seek(offset)
        self._file.write(bytes([status]))
        self._file.flush()

    def __repr__(self) -> str:
        return (
            f"WALFile(path={self.filepath!r}, "
            f"entry_size={self.entry_size}, "
            f"entries={self._entry_count})"
        )