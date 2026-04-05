from __future__ import annotations
import os
import struct
from typing import Any
from .column import Column


# Maps Column base type -> (struct_char, byte_size)
# CHAR and VARCHAR are handled separately since size depends on _limit
TYPE_FORMAT: dict[str, tuple[str, int]] = {
    "INT":     ("i", 4),
    "FLOAT":   ("d", 8),
    "BOOLEAN": ("?", 1),
}

TOMBSTONE_ALIVE   = b'\x01' # this is to mark whether the data still exists or has been zeroed out
TOMBSTONE_DELETED = b'\x00'
TOMBSTONE_SIZE    = 1 # just one at the end;
NULL_FLAG_SIZE    = 1


class HeapFile:
    """
    Fixed-width binary heap file.

    Record layout (all records are exactly `record_size` bytes):

        [tombstone: 1 byte]
        for each column in schema order:
            [null_flag: 1 byte]
            [data:      N bytes]   <- N depends on column type

    tombstone:
        0x01 = alive
        0x00 = deleted (slot is on the free list, data bytes are stale)

    null_flag:
        0x01 = value is NULL  (data bytes are zeroed, meaningless)
        0x00 = value is present
    """

    def __init__(self, filepath: str, schema: dict[str, Column]) -> None:
        self.filepath = filepath
        self.schema   = schema                          # ordered dict, insertion order = column order

        self._col_order: list[str] = list(schema.keys())
        self._fmt, self._col_offsets, self._record_size = self._build_format()

        # Open existing file in read/write binary, create if missing
        mode = "r+b" if os.path.exists(filepath) else "w+b"
        self._file = open(filepath, mode)

    # ------------------------------------------------------------------
    # Format builder
    # ------------------------------------------------------------------

    def _build_format(self) -> tuple[str, dict[str, int], int]:
        """
        Build the struct format string and per-column byte offsets.

        Returns:
            fmt          : full struct format string (without the leading tombstone byte,
                           that is handled manually since it is a single raw byte)
            col_offsets  : {col_name: byte_offset_from_start_of_record}
            record_size  : total bytes per record including tombstone
        """
        fmt_parts: list[str] = []
        col_offsets: dict[str, int] = {}

        # Current offset starts after tombstone byte
        offset = TOMBSTONE_SIZE

        for name in self._col_order:
            col = self.schema[name]
            col_offsets[name] = offset

            # null flag
            fmt_parts.append("B")           # unsigned char, 1 byte
            offset += NULL_FLAG_SIZE

            base = col._base_type
            if base in TYPE_FORMAT:
                char, size = TYPE_FORMAT[base]
                fmt_parts.append(char)
                offset += size
            elif base in ("CHAR", "VARCHAR"):
                n = col._limit                  # guaranteed not None after Column validation
                fmt_parts.append(f"{n}s")       # n-byte string
                offset += n
            else:
                raise ValueError(f"Unsupported column type '{base}' in HeapFile")

        fmt = "=" + "".join(fmt_parts)      # "=" -> native byte order, no alignment padding
        record_size = offset
        return fmt, col_offsets, record_size

    # ------------------------------------------------------------------
    # Core read / write
    # ------------------------------------------------------------------

    def unpack_row(self, raw: bytes) -> dict[str, Any] | None:
        """Unpack a raw byte string into a row dictionary."""
        if len(raw) < self._record_size:
            return None

        tombstone = raw[0:1]
        if tombstone == TOMBSTONE_DELETED:
            return None

        values = struct.unpack_from(self._fmt, raw, offset=TOMBSTONE_SIZE)
        row: dict[str, Any] = {}
        val_idx = 0

        for name in self._col_order:
            col       = self.schema[name]
            null_flag = values[val_idx];  val_idx += 1
            raw_val   = values[val_idx];  val_idx += 1

            if null_flag == 1:
                row[name] = None
            else:
                row[name] = self._decode(col, raw_val)

        return row

    def read(self, slot: int) -> dict[str, Any] | None:
        """
        Read the record at `slot`.
        Returns the row dict if alive, None if the slot is deleted/empty.
        """
        self._file.seek(slot * self._record_size)
        raw = self._file.read(self._record_size)
        return self.unpack_row(raw)
    
    def pack_row(self, row: dict[str, Any]) -> bytes:
        packed_values: list[Any] = []
        for name in self._col_order:
            col   = self.schema[name]
            value = row.get(name)
            if value is None:
                packed_values.append(1)
                packed_values.append(self._null_placeholder(col))
            else:
                packed_values.append(0)
                packed_values.append(self._encode(col, value))
        data   = struct.pack(self._fmt, *packed_values)
        record = TOMBSTONE_ALIVE + data
        assert len(record) == self._record_size
        return record

    def write_raw(self, slot: int, data: bytes) -> None:
        assert len(data) == self._record_size
        self._file.seek(slot * self._record_size)
        self._file.write(data)
        self._file.flush()

    def write(self, slot: int, row: dict[str, Any]) -> None:
        """
        Pack `row` into bytes and write it at `slot`.
        Marks the record as alive (tombstone = 0x01).
        """
        packed_values: list[Any] = []

        for name in self._col_order:
            col   = self.schema[name]
            value = row.get(name)           # missing key treated as None

            if value is None:
                packed_values.append(1)     # null_flag = 1
                packed_values.append(self._null_placeholder(col))
            else:
                packed_values.append(0)     # null_flag = 0
                packed_values.append(self._encode(col, value))

        data = struct.pack(self._fmt, *packed_values)
        record = TOMBSTONE_ALIVE + data     # prepend tombstone

        assert len(record) == self._record_size, (
            f"Record size mismatch: expected {self._record_size}, got {len(record)}"
        )

        self._file.seek(slot * self._record_size)
        self._file.write(record)
        self._file.flush()                  # make sure it hits the OS buffer

    def delete(self, slot: int) -> None:
        """
        Flip the tombstone byte to 0x00.
        Data bytes are left as-is (stale), slot goes onto the free list.
        """
        self._file.seek(slot * self._record_size)
        self._file.write(TOMBSTONE_DELETED)
        self._file.flush()

    # ------------------------------------------------------------------
    # Encode / decode helpers
    # ------------------------------------------------------------------

    def _encode(self, col: Column, value: Any) -> Any:
        """Convert a Python value to what struct.pack expects."""
        base = col._base_type
        if base == "INT":
            return int(value)
        if base == "FLOAT":
            return float(value)
        if base == "BOOLEAN":
            return bool(value)
        if base in ("CHAR", "VARCHAR"):
            encoded = value.encode("utf-8")
            # Pad with \x00 to exactly _limit bytes, truncate if somehow over
            return encoded.ljust(col._limit, b'\x00')[:col._limit]
        raise ValueError(f"Cannot encode type '{base}'")

    def _decode(self, col: Column, raw: Any) -> Any:
        """Convert what struct.unpack returned back to a Python value."""
        base = col._base_type
        if base in ("INT", "FLOAT", "BOOLEAN"):
            return raw
        if base in ("CHAR", "VARCHAR"):
            # raw is bytes — strip trailing \x00 padding, decode to str
            return raw.rstrip(b'\x00').decode("utf-8")
        raise ValueError(f"Cannot decode type '{base}'")

    def _null_placeholder(self, col: Column) -> Any:
        """Return a zero-value placeholder for the data bytes when null_flag=1."""
        base = col._base_type
        if base == "INT":
            return 0
        if base == "FLOAT":
            return 0.0
        if base == "BOOLEAN":
            return False
        if base in ("CHAR", "VARCHAR"):
            return b'\x00' * col._limit
        raise ValueError(f"No placeholder for type '{base}'")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def record_size(self) -> int:
        return self._record_size

    def close(self) -> None:
        self._file.flush()
        self._file.close()

    def __repr__(self) -> str:
        return (
            f"HeapFile(path={self.filepath!r}, "
            f"record_size={self._record_size}, "
            f"columns={self._col_order})"
        )