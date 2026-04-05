from __future__ import annotations
import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.column import Column
from database.table import Table
from database.transactions import Transaction


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def sep(title: str) -> None:
    print(f"\n{'='*55}")
    print(f"  {title}")
    print('='*55)

def cleanup(*names: str) -> None:
    for name in names:
        for ext in (".heap", ".wal", ".meta.json", ".meta.json.tmp"):
            path = f"{name}{ext}"
            if os.path.exists(path):
                os.remove(path)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

USERS_SCHEMA = [
    Column("id",      "INT",         nullable=False),
    Column("name",    "VARCHAR(50)", nullable=False),
    Column("age",     "INT",         nullable=True,  default=0),
    Column("score",   "FLOAT",       nullable=True),
    Column("active",  "BOOLEAN",     nullable=False, default=True),
]

ORDERS_SCHEMA = [
    Column("order_id", "INT",         nullable=False),
    Column("user_id",  "INT",         nullable=False),
    Column("amount",   "FLOAT",       nullable=False),
    Column("status",   "VARCHAR(20)", nullable=False, default="pending"),
]


# ------------------------------------------------------------------
# Test 1 — Auto-commit: basic insert + find
# ------------------------------------------------------------------

sep("TEST 1: auto-commit insert + find")
cleanup("users", "orders")

users = Table("users", primary_key="id", schema=USERS_SCHEMA)
users.insert({"id": 1, "name": "Alice", "age": 30, "score": 95.5, "active": True})
users.insert({"id": 2, "name": "Bob",   "age": 25, "score": 80.0, "active": False})
users.insert({"id": 3, "name": "Carol", "age": 28, "score": 88.3, "active": True})

print("find(1):", users.find(1))
print("find(2):", users.find(2))
print("find(99):", users.find(99))   # None


# ------------------------------------------------------------------
# Test 2 — Auto-commit: update in place
# ------------------------------------------------------------------

sep("TEST 2: auto-commit update")

users.update(1, {"age": 31, "score": 97.0})
print("after update(1):", users.find(1))

users.update(2, {"active": True})
print("after update(2):", users.find(2))


# ------------------------------------------------------------------
# Test 3 — Auto-commit: delete + slot recycling
# ------------------------------------------------------------------

sep("TEST 3: auto-commit delete + slot recycling")

print("len before delete:", len(users))
users.delete(2)
print("len after delete(2):", len(users))
print("find(2) after delete:", users.find(2))   # None
print("free_list:", users._free_list)           # slot for Bob

users.insert({"id": 4, "name": "Dave", "age": 22, "score": 70.0, "active": True})
print("free_list after reuse:", users._free_list)   # empty
print("find(4):", users.find(4))


# ------------------------------------------------------------------
# Test 4 — Auto-commit: range_find + all_rows
# ------------------------------------------------------------------

sep("TEST 4: range_find + all_rows")

print("range_find(1, 3):", users.range_find(1, 3))
print("range_find(1, 4):", users.range_find(1, 4))
print("all_rows:")
for row in users.all_rows():
    print(" ", row)


# ------------------------------------------------------------------
# Test 5 — Auto-commit: defaults + nulls
# ------------------------------------------------------------------

sep("TEST 5: defaults + nulls")

users.insert({"id": 5, "name": "Eve", "score": None})
print("find(5) with defaults:", users.find(5))
# age should be 0, active should be True, score should be None


# ------------------------------------------------------------------
# Test 6 — Auto-commit: duplicate pk raises
# ------------------------------------------------------------------

sep("TEST 6: duplicate pk raises")

try:
    users.insert({"id": 1, "name": "Dup", "age": 99, "score": 0.0, "active": False})
    print("ERROR: should have raised")
except ValueError as e:
    print("Correctly raised ValueError:", e)


# ------------------------------------------------------------------
# Test 7 — Persist + reload (simulates restart)
# ------------------------------------------------------------------

sep("TEST 7: persist + reload")

users.close()
print("Table closed. Reopening from disk...")

users = Table("users", primary_key="id", schema=USERS_SCHEMA)
print("all_rows after reload:")
for row in users.all_rows():
    print(" ", row)

print("find(2) after reload (was deleted):", users.find(2))  # None


# ------------------------------------------------------------------
# Test 8 — Transaction: commit across two tables
# ------------------------------------------------------------------

sep("TEST 8: transaction COMMIT across two tables")

orders = Table("orders", primary_key="order_id", schema=ORDERS_SCHEMA)

with Transaction(users, orders) as txn:
    txn.insert(users,  {"id": 6, "name": "Frank", "age": 35, "score": 60.0, "active": True})
    txn.insert(orders, {"order_id": 101, "user_id": 6, "amount": 250.0, "status": "paid"})
    txn.insert(orders, {"order_id": 102, "user_id": 1, "amount": 89.99})  # default status

print("users.find(6) after commit:", users.find(6))
print("orders.find(101) after commit:", orders.find(101))
print("orders.find(102) after commit:", orders.find(102))


# ------------------------------------------------------------------
# Test 9 — Transaction: rollback leaves both tables untouched
# ------------------------------------------------------------------

sep("TEST 9: transaction ROLLBACK")

txn = Transaction(users, orders)
txn.begin()
txn.insert(users,  {"id": 7, "name": "Ghost", "age": 99, "score": 0.0, "active": False})
txn.insert(orders, {"order_id": 999, "user_id": 7, "amount": 1.0})
txn.rollback()

print("users.find(7) after rollback:", users.find(7))     # None
print("orders.find(999) after rollback:", orders.find(999))  # None
print("users.all_rows() — Ghost should not appear:")
for row in users.all_rows():
    print(" ", row)


# ------------------------------------------------------------------
# Test 10 — Transaction: rollback on exception via context manager
# ------------------------------------------------------------------

sep("TEST 10: auto-rollback on exception")

try:
    with Transaction(users, orders) as txn:
        txn.insert(users, {"id": 8, "name": "Temp", "age": 20, "score": 50.0, "active": True})
        raise RuntimeError("something went wrong mid-transaction")
except RuntimeError as e:
    print("Caught expected exception:", e)

print("users.find(8) after auto-rollback:", users.find(8))  # None


# ------------------------------------------------------------------
# Test 11 — Transaction: update + delete within txn, then commit
# ------------------------------------------------------------------

sep("TEST 11: transaction update + delete then commit")

txn = Transaction(users, orders)
txn.begin()
txn.update(users, 1, {"score": 99.9})         # update Alice's score
txn.delete(orders, 102)                        # delete order 102
txn.commit()

print("users.find(1) score should be 99.9:", users.find(1))
print("orders.find(102) should be None:", orders.find(102))


# ------------------------------------------------------------------
# Test 12 — Reload after transactions (crash simulation)
# ------------------------------------------------------------------

sep("TEST 12: reload after transactions")

users.close()
orders.close()

users  = Table("users",  primary_key="id",       schema=USERS_SCHEMA)
orders = Table("orders", primary_key="order_id", schema=ORDERS_SCHEMA)

print("users.all_rows() after reload:")
for row in users.all_rows():
    print(" ", row)

print("orders.all_rows() after reload:")
for row in orders.all_rows():
    print(" ", row)

users.close()
orders.close()
cleanup("users", "orders")
print("\nAll tests done.")