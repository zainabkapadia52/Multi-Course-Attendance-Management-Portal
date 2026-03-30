"""
database_manager.py
-------------------
SQL-style schema definition with column names, types, constraints,
and full validation on every insert/update.

Supported types
---------------
  INT         – Python int
  FLOAT       – Python float
  VARCHAR(n)  – string with max length n
  CHAR(n)     – fixed-length string of exactly n characters
  STRING      – unbounded string
  BOOL        – True / False

Supported constraints (per column)
------------------------------------
  primary_key=True    – unique, not null, B+ Tree key (must be INT)
  nullable=False      – value cannot be None / missing
  unique=True         – no two rows may share this value
  default=<value>     – used when column is omitted from insert

Usage
-----
    db = DatabaseManager()

    db.create_table("users", columns=[
        Column("user_id",  INT,        primary_key=True),
        Column("name",     VARCHAR(50),nullable=False),
        Column("balance",  FLOAT,      nullable=False, default=0.0),
        Column("city",     VARCHAR(30),nullable=True),
    ])

    users = db.get_table("users")
    users.insert({"user_id": 1, "name": "Alice", "balance": 1000.0, "city": "NY"})
    users.get(1)
    users.update(1, {"balance": 200.0})   # only changed fields needed
    users.delete(1)
    db.show("users")
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from bplustree import BPlusTree


# ═══════════════════════════════════════════════════════════════════════════
# Type system
# ═══════════════════════════════════════════════════════════════════════════

class _ColType:
    name = "BASE"
    def validate(self, value: Any) -> Any:
        raise NotImplementedError


class _IntType(_ColType):
    name = "INT"
    def validate(self, value: Any) -> int:
        if not isinstance(value, int):
            raise TypeError(f"Expected INT, got {type(value).__name__}: {value!r}")
        return value


class _FloatType(_ColType):
    name = "FLOAT"
    def validate(self, value: Any) -> float:
        if isinstance(value, int):
            value = float(value)
        if not isinstance(value, float):
            raise TypeError(f"Expected FLOAT, got {type(value).__name__}: {value!r}")
        return value


class _StringType(_ColType):
    name = "STRING"
    def validate(self, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError(f"Expected STRING, got {type(value).__name__}: {value!r}")
        return value


class _BoolType(_ColType):
    name = "BOOL"
    def validate(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise TypeError(f"Expected BOOL, got {type(value).__name__}: {value!r}")
        return value


class _VarcharType(_ColType):
    def __init__(self, max_len: int) -> None:
        if max_len <= 0:
            raise ValueError("VARCHAR length must be > 0")
        self.max_len = max_len
        self.name = f"VARCHAR({max_len})"

    def validate(self, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError(f"Expected {self.name}, got {type(value).__name__}: {value!r}")
        if len(value) > self.max_len:
            raise ValueError(
                f"Value {value!r} exceeds {self.name} limit (length {len(value)})"
            )
        return value


class _CharType(_ColType):
    def __init__(self, length: int) -> None:
        if length <= 0:
            raise ValueError("CHAR length must be > 0")
        self.length = length
        self.name = f"CHAR({length})"

    def validate(self, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError(f"Expected {self.name}, got {type(value).__name__}: {value!r}")
        if len(value) != self.length:
            raise ValueError(
                f"Value {value!r} has length {len(value)}, "
                f"{self.name} requires exactly {self.length} character(s)"
            )
        return value


# ── Public type singletons / factories ───────────────────────────────────
INT    = _IntType()
FLOAT  = _FloatType()
STRING = _StringType()
BOOL   = _BoolType()

def VARCHAR(n: int) -> _VarcharType:
    return _VarcharType(n)

def CHAR(n: int) -> _CharType:
    return _CharType(n)


# ═══════════════════════════════════════════════════════════════════════════
# Column definition
# ═══════════════════════════════════════════════════════════════════════════

_SENTINEL = object()   # marks "no default provided"

@dataclass
class Column:
    """
    Defines one column in a table schema.

    Parameters
    ----------
    name        : column name
    col_type    : INT | FLOAT | STRING | BOOL | VARCHAR(n) | CHAR(n)
    primary_key : if True, this column is the B+ Tree key (must be INT)
    nullable    : if False, None / missing values are rejected
    unique      : if True, duplicate values are rejected
    default     : value used when column is omitted from an insert
    """
    name:        str
    col_type:    _ColType
    primary_key: bool = False
    nullable:    bool = True
    unique:      bool = False
    default:     Any  = field(default=_SENTINEL)

    def has_default(self) -> bool:
        return self.default is not _SENTINEL

    def __post_init__(self) -> None:
        if self.primary_key:
            if not isinstance(self.col_type, _IntType):
                raise TypeError(
                    f"Primary key '{self.name}' must be INT, got {self.col_type.name}"
                )
            self.nullable = False


# ═══════════════════════════════════════════════════════════════════════════
# Table
# ═══════════════════════════════════════════════════════════════════════════

class Table:
    """
    A single relation with a fixed schema, backed by a B+ Tree.
    All insert / update values are validated against the schema.
    """

    def __init__(self, name: str, columns: list[Column], order: int = 4) -> None:
        self.name = name
        self._tree = BPlusTree(order=order)

        pk_cols = [c for c in columns if c.primary_key]
        if len(pk_cols) != 1:
            raise ValueError(
                f"Table '{name}' must have exactly one primary_key column, "
                f"got {len(pk_cols)}"
            )

        self._columns: dict[str, Column] = {c.name: c for c in columns}
        self._pk_col: Column = pk_cols[0]

        # unique-value sets (includes PK automatically)
        self._unique_index: dict[str, set] = {
            c.name: set() for c in columns if c.unique or c.primary_key
        }

    @property
    def primary_key(self) -> str:
        return self._pk_col.name

    # ── Validation ─────────────────────────────────────────────────────

    def _validate(self, data: dict, is_update: bool = False, existing_key: int | None = None) -> dict:
        """
        Validate and coerce `data` against the schema.
        For updates, only the provided fields are required;
        everything else is filled from the existing record.
        """
        if is_update and existing_key is not None:
            base = dict(self._tree.search(existing_key) or {})
            base.update(data)
            data = base

        # Reject unknown columns
        unknown = set(data) - set(self._columns)
        if unknown:
            raise ValueError(
                f"Unknown column(s): {sorted(unknown)}. "
                f"Valid columns: {list(self._columns)}"
            )

        record = {}
        for col_name, col in self._columns.items():

            # Resolve value
            if col_name in data:
                value = data[col_name]
            elif col.has_default():
                value = col.default
            elif col.primary_key and is_update:
                value = existing_key
            else:
                value = None

            # Nullable check
            if value is None:
                if not col.nullable:
                    raise ValueError(f"Column '{col_name}' is NOT NULL — value required.")
                record[col_name] = None
                continue

            # Type check
            try:
                value = col.col_type.validate(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Column '{col_name}': {exc}") from exc

            # Uniqueness check
            if col_name in self._unique_index:
                old_val = None
                if is_update and existing_key is not None:
                    old_record = self._tree.search(existing_key)
                    if old_record:
                        old_val = old_record.get(col_name)
                if value in self._unique_index[col_name] and value != old_val:
                    raise ValueError(
                        f"Column '{col_name}' has UNIQUE constraint — "
                        f"value {value!r} already exists."
                    )

            record[col_name] = value

        return record

    def _index_add(self, record: dict) -> None:
        for col_name in self._unique_index:
            val = record.get(col_name)
            if val is not None:
                self._unique_index[col_name].add(val)

    def _index_remove(self, record: dict) -> None:
        for col_name in self._unique_index:
            val = record.get(col_name)
            if val is not None:
                self._unique_index[col_name].discard(val)

    # ── CRUD ───────────────────────────────────────────────────────────

    def insert(self, data: dict) -> dict:
        """Validate and insert a new row. Returns the stored record."""
        record = self._validate(data, is_update=False)
        pk = record[self._pk_col.name]
        if self._tree.search(pk) is not None:
            raise ValueError(f"Primary key {pk!r} already exists in '{self.name}'.")
        self._tree.insert(pk, record)
        self._index_add(record)
        return record

    def get(self, key: int) -> dict | None:
        """Return the row with the given primary key, or None."""
        return self._tree.search(key)

    def update(self, key: int, data: dict) -> dict:
        """
        Update columns for the row at `key`.
        Only the fields you want to change need to be supplied.
        Returns the updated record.
        """
        if self._tree.search(key) is None:
            raise KeyError(f"No row with primary key {key!r} in '{self.name}'.")
        old = self._tree.search(key)
        new = self._validate(data, is_update=True, existing_key=key)
        self._index_remove(old)
        self._tree.update(key, new)
        self._index_add(new)
        return new

    def delete(self, key: int) -> bool:
        """Delete the row with the given primary key. Returns True if found."""
        record = self._tree.search(key)
        if record is None:
            return False
        self._index_remove(record)
        return self._tree.delete(key)

    def all(self) -> list[dict]:
        """Return all rows in ascending primary-key order."""
        return [v for _, v in self._tree.get_all()]

    # ── Display ────────────────────────────────────────────────────────

    def print_schema(self) -> None:
        print(f"\n  Schema — {self.name.upper()}")
        for col_name, col in self._columns.items():
            flags = []
            if col.primary_key:   flags.append("PRIMARY KEY")
            if not col.nullable:  flags.append("NOT NULL")
            if col.unique:        flags.append("UNIQUE")
            if col.has_default(): flags.append(f"DEFAULT={col.default!r}")
            flag_str = "  " + ", ".join(flags) if flags else ""
            print(f"    {col_name:<20} {col.col_type.name:<15}{flag_str}")

    def print_rows(self) -> None:
        rows = self.all()
        col_names = list(self._columns.keys())
        widths = {
            c: max(len(c), *(len(str(r.get(c, ""))) for r in rows) if rows else [len(c)])
            for c in col_names
        }
        header  = " | ".join(c.ljust(widths[c]) for c in col_names)
        divider = "-+-".join("-" * widths[c] for c in col_names)
        print(f"\n  {self.name.upper()} ({len(rows)} row(s))")
        print("  " + header)
        print("  " + divider)
        for row in rows:
            print("  " + " | ".join(str(row.get(c, "")).ljust(widths[c]) for c in col_names))
        if not rows:
            print("  (empty)")

    def __repr__(self) -> str:
        return f"Table('{self.name}', pk='{self.primary_key}', rows={len(self.all())})"


# ═══════════════════════════════════════════════════════════════════════════
# DatabaseManager
# ═══════════════════════════════════════════════════════════════════════════

class DatabaseManager:
    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}

    def create_table(self, name: str, columns: list[Column], order: int = 4) -> Table:
        if name in self._tables:
            raise ValueError(f"Table '{name}' already exists.")
        table = Table(name, columns, order)
        self._tables[name] = table
        print(f"[DB] Table '{name}' created.")
        table.print_schema()
        return table

    def get_table(self, name: str) -> Table:
        if name not in self._tables:
            raise ValueError(
                f"Table '{name}' does not exist. Available: {self.list_tables()}"
            )
        return self._tables[name]

    def drop_table(self, name: str) -> None:
        if name not in self._tables:
            raise ValueError(f"Table '{name}' does not exist.")
        del self._tables[name]
        print(f"[DB] Table '{name}' dropped.")

    def list_tables(self) -> list[str]:
        return list(self._tables.keys())

    def show(self, name: str) -> None:
        self.get_table(name).print_rows()

    def show_all(self) -> None:
        for name in self._tables:
            self.show(name)


# ═══════════════════════════════════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    db = DatabaseManager()

    # ── Define schemas ────────────────────────────────────────────────────
    db.create_table("users", columns=[
        Column("user_id",  INT,        primary_key=True),
        Column("name",     VARCHAR(50),nullable=False),
        Column("balance",  FLOAT,      nullable=False, default=0.0),
        Column("city",     VARCHAR(30),nullable=True),
    ])

    db.create_table("products", columns=[
        Column("product_id", INT,         primary_key=True),
        Column("name",       VARCHAR(100), nullable=False, unique=True),
        Column("stock",      INT,          nullable=False, default=0),
        Column("price",      FLOAT,        nullable=False),
    ])

    db.create_table("orders", columns=[
        Column("order_id",   INT,        primary_key=True),
        Column("user_id",    INT,        nullable=False),
        Column("product_id", INT,        nullable=False),
        Column("amount",     FLOAT,      nullable=False),
        Column("status",     VARCHAR(20),nullable=False, default="pending"),
    ])

    # ── Insert rows ───────────────────────────────────────────────────────
    users    = db.get_table("users")
    products = db.get_table("products")
    orders   = db.get_table("orders")

    users.insert({"user_id": 1, "name": "Alice", "balance": 1000.0, "city": "NY"})
    users.insert({"user_id": 2, "name": "Bob",   "balance":  500.0, "city": "LA"})
    users.insert({"user_id": 3, "name": "Carol", "balance":  750.0, "city": "NY"})

    products.insert({"product_id": 10, "name": "Laptop", "stock": 5,  "price": 1200.0})
    products.insert({"product_id": 11, "name": "Phone",  "stock": 20, "price":  800.0})

    orders.insert({"order_id": 100, "user_id": 1, "product_id": 10, "amount": 1200.0})
    orders.insert({"order_id": 101, "user_id": 2, "product_id": 11, "amount":  800.0})

    db.show_all()

    # ── Update (only provide what changes) ────────────────────────────────
    print("\n── Updating Alice's balance to 200.0 ──")
    users.update(1, {"balance": 200.0})
    db.show("users")

    # ── Delete ────────────────────────────────────────────────────────────
    print("\n── Deleting Carol (user_id=3) ──")
    users.delete(3)
    db.show("users")

    # ── Constraint violation demos ────────────────────────────────────────
    print("\n── Constraint checks ──")

    try:
        users.insert({"user_id": 4, "name": 99999, "balance": 100.0})
    except ValueError as e:
        print(f"  [Type error]         {e}")

    try:
        users.insert({"user_id": 5, "balance": 100.0})   # name missing, no default
    except ValueError as e:
        print(f"  [NOT NULL]           {e}")

    try:
        users.insert({"user_id": 6, "name": "A" * 60, "balance": 100.0})
    except ValueError as e:
        print(f"  [VARCHAR too long]   {e}")

    try:
        users.insert({"user_id": 1, "name": "Dupe", "balance": 0.0})
    except ValueError as e:
        print(f"  [Duplicate PK]       {e}")

    try:
        products.insert({"product_id": 99, "name": "Laptop", "stock": 1, "price": 999.0})
    except ValueError as e:
        print(f"  [UNIQUE violation]   {e}")

    try:
        users.insert({"user_id": 7, "name": "Dave", "balance": 50.0, "mood": "happy"})
    except ValueError as e:
        print(f"  [Unknown column]     {e}")

    print("\n[DB] Tables:", db.list_tables())