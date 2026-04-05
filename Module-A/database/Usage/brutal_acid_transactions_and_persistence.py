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
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def cleanup(*names: str) -> None:
    for name in names:
        for ext in (".heap", ".wal", ".meta.json", ".meta.json.tmp"):
            path = f"{name}{ext}"
            if os.path.exists(path):
                os.remove(path)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message} | expected={expected!r}, actual={actual!r}")


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

USERS_SCHEMA = [
    Column("id", "INT", nullable=False),
    Column("name", "VARCHAR(50)", nullable=False),
    Column("age", "INT", nullable=True, default=0),
    Column("score", "FLOAT", nullable=True),
    Column("active", "BOOLEAN", nullable=False, default=True),
]

ORDERS_SCHEMA = [
    Column("order_id", "INT", nullable=False),
    Column("user_id", "INT", nullable=False),
    Column("amount", "FLOAT", nullable=False),
    Column("status", "VARCHAR(20)", nullable=False, default="pending"),
]

AUDIT_SCHEMA = [
    Column("event_id", "INT", nullable=False),
    Column("message", "VARCHAR(100)", nullable=False),
]


# ------------------------------------------------------------------
# Test groups
# ------------------------------------------------------------------

def brutal_auto_commit_tests(users: Table, orders: Table) -> None:
    sep("AUTO-COMMIT BRUTAL TESTS")

    # Insert baseline users with mixed values
    users.insert({"id": 1, "name": "Alice", "age": 30, "score": 95.5, "active": True})
    users.insert({"id": 2, "name": "Bob", "age": 21, "score": 72.0, "active": False})
    users.insert({"id": 3, "name": "Carol", "age": 26, "score": 88.8, "active": True})

    assert_equal(users.find(1)["name"], "Alice", "find should return inserted row")
    assert_equal(users.find(999), None, "find for missing key should return None")

    # Update and verify only that record changed
    updated = users.update(2, {"active": True, "score": 77.7})
    assert_true(updated, "update should succeed for existing pk")
    assert_equal(users.find(2)["active"], True, "update should persist active")
    assert_equal(users.find(2)["score"], 77.7, "update should persist score")

    # Delete and verify non-existence + slot reuse on next insert
    deleted = users.delete(3)
    assert_true(deleted, "delete should succeed for existing pk")
    assert_equal(users.find(3), None, "deleted row should not be found")

    users.insert({"id": 4, "name": "Dave", "age": 23, "score": 65.0, "active": True})
    assert_equal(users.find(4)["name"], "Dave", "insert after delete should still work")

    # Defaults and null handling
    users.insert({"id": 5, "name": "Eve", "score": None})
    eve = users.find(5)
    assert_equal(eve["age"], 0, "default age should be applied")
    assert_equal(eve["active"], True, "default active should be applied")
    assert_equal(eve["score"], None, "explicit null should remain null")

    # Duplicate PK must fail
    duplicate_failed = False
    try:
        users.insert({"id": 1, "name": "Dup", "age": 0, "score": 0.0, "active": False})
    except ValueError:
        duplicate_failed = True
    assert_true(duplicate_failed, "duplicate primary key insert must raise")

    # Orders auto-commit smoke
    orders.insert({"order_id": 10, "user_id": 1, "amount": 100.0})
    orders.insert({"order_id": 11, "user_id": 2, "amount": 50.5, "status": "paid"})
    assert_equal(orders.find(10)["status"], "pending", "order default status should apply")
    assert_equal(orders.find(11)["status"], "paid", "explicit status should persist")

    print("Auto-commit tests passed.")


def brutal_transaction_tests(users: Table, orders: Table, audit: Table) -> None:
    sep("TRANSACTION BRUTAL TESTS")

    # Context-manager commit across two tables
    with Transaction(users, orders) as txn:
        txn.insert(users, {"id": 100, "name": "Frank", "age": 35, "score": 60.0, "active": True})
        txn.insert(orders, {"order_id": 1000, "user_id": 100, "amount": 250.0, "status": "paid"})
        txn.insert(orders, {"order_id": 1001, "user_id": 1, "amount": 89.99})

    assert_equal(users.find(100)["name"], "Frank", "txn commit should persist users row")
    assert_equal(orders.find(1000)["status"], "paid", "txn commit should persist order row")
    assert_equal(orders.find(1001)["status"], "pending", "txn defaults should apply")

    # Explicit begin/rollback should leave no traces
    txn = Transaction(users, orders)
    txn.begin()
    txn.insert(users, {"id": 101, "name": "Ghost", "age": 99, "score": 0.0, "active": False})
    txn.insert(orders, {"order_id": 1002, "user_id": 101, "amount": 1.0})

    # The index is updated inside txn, but heap has no row until commit.
    assert_equal(txn.find(users, 101), None, "staged insert should not be readable from heap")

    txn.rollback()
    assert_equal(users.find(101), None, "rollback should remove staged user")
    assert_equal(orders.find(1002), None, "rollback should remove staged order")

    # Exception in context manager must auto-rollback
    exception_seen = False
    try:
        with Transaction(users, orders) as failing_txn:
            failing_txn.insert(users, {"id": 102, "name": "Temp", "age": 20, "score": 50.0, "active": True})
            raise RuntimeError("force failure")
    except RuntimeError:
        exception_seen = True

    assert_true(exception_seen, "expected runtime error should propagate")
    assert_equal(users.find(102), None, "auto-rollback should remove temp row")

    # Table enrollment checks: operations on non-enrolled table should fail
    not_enrolled_failed = False
    try:
        with Transaction(users, orders) as wrong_txn:
            wrong_txn.insert(audit, {"event_id": 1, "message": "should fail"})
    except ValueError:
        not_enrolled_failed = True
    assert_true(not_enrolled_failed, "txn should reject non-enrolled tables")

    print("Transaction tests passed.")


def cross_table_atomic_commit_tests(users: Table, orders: Table) -> None:
    sep("CROSS-TABLE ATOMIC COMMIT TESTS")

    # Success path: both tables commit together.
    with Transaction(users, orders) as txn:
        txn.insert(users, {"id": 200, "name": "Ivy", "age": 29, "score": 91.0, "active": True})
        txn.insert(orders, {"order_id": 2000, "user_id": 200, "amount": 450.0, "status": "paid"})

    assert_true(users.find(200) is not None, "successful cross-table commit should persist user")
    assert_true(orders.find(2000) is not None, "successful cross-table commit should persist order")

    # Failure path: duplicate key in second table should rollback both tables.
    rollback_happened = False
    try:
        with Transaction(users, orders) as txn:
            txn.insert(users, {"id": 201, "name": "Jack", "age": 31, "score": 82.0, "active": True})
            txn.insert(orders, {"order_id": 2000, "user_id": 201, "amount": 9.99})  # duplicate order_id
    except ValueError:
        rollback_happened = True

    assert_true(rollback_happened, "duplicate key should fail and trigger rollback")
    assert_equal(users.find(201), None, "failed cross-table txn must not leave user behind")

    print("Cross-table atomic commit tests passed.")


def persistence_reload_tests(name_users: str, name_orders: str, users: Table, orders: Table) -> tuple[Table, Table]:
    sep("RELOAD / PERSISTENCE CHECK")

    users.close()
    orders.close()

    users = Table(name_users, primary_key="id", schema=USERS_SCHEMA)
    orders = Table(name_orders, primary_key="order_id", schema=ORDERS_SCHEMA)

    assert_true(users.find(100) is not None, "committed transaction user should survive reload")
    assert_true(users.find(101) is None, "rolled back user must stay absent after reload")
    assert_true(users.find(102) is None, "auto-rolled back user must stay absent after reload")
    assert_true(users.find(200) is not None, "cross-table committed user should survive reload")
    assert_true(users.find(201) is None, "failed cross-table txn user must stay absent")

    assert_true(orders.find(1000) is not None, "committed transaction order should survive reload")
    assert_true(orders.find(1002) is None, "rolled back order must stay absent")
    assert_true(orders.find(2000) is not None, "cross-table committed order should survive reload")

    print("Reload tests passed.")
    return users, orders


def mini_stress_test(users: Table, orders: Table) -> None:
    sep("MINI STRESS TEST (MIXED AUTO-COMMIT + TXN)")

    base_user_id = 300
    base_order_id = 3000

    # Alternate successful and failed txns while interleaving auto-commit writes.
    for i in range(20):
        uid = base_user_id + i
        oid = base_order_id + i

        users.insert({"id": 10000 + i, "name": f"Auto{i}", "age": i, "score": float(i), "active": True})

        if i % 2 == 0:
            with Transaction(users, orders) as txn:
                txn.insert(users, {"id": uid, "name": f"Txn{i}", "age": 20 + i, "score": 70.0, "active": True})
                txn.insert(orders, {"order_id": oid, "user_id": uid, "amount": 10.0 + i})
        else:
            try:
                with Transaction(users, orders) as txn:
                    txn.insert(users, {"id": uid, "name": f"Txn{i}", "age": 20 + i, "score": 70.0, "active": True})
                    txn.insert(orders, {"order_id": 2000, "user_id": uid, "amount": 10.0 + i})
            except ValueError:
                pass

    # Validate expected presence/absence pattern for txn inserts.
    for i in range(20):
        uid = base_user_id + i
        if i % 2 == 0:
            assert_true(users.find(uid) is not None, f"txn user {uid} should exist")
        else:
            assert_true(users.find(uid) is None, f"txn user {uid} should have rolled back")

    print("Mini stress test passed.")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    users_name = "users2"
    orders_name = "orders2"
    audit_name = "audit2"

    cleanup(users_name, orders_name, audit_name)

    users = Table(users_name, primary_key="id", schema=USERS_SCHEMA)
    orders = Table(orders_name, primary_key="order_id", schema=ORDERS_SCHEMA)
    audit = Table(audit_name, primary_key="event_id", schema=AUDIT_SCHEMA)

    try:
        brutal_auto_commit_tests(users, orders)
        brutal_transaction_tests(users, orders, audit)
        cross_table_atomic_commit_tests(users, orders)
        users, orders = persistence_reload_tests(users_name, orders_name, users, orders)
        mini_stress_test(users, orders)

        sep("ALL BRUTAL TESTS PASSED")
    finally:
        users.close()
        orders.close()
        audit.close()
        cleanup(users_name, orders_name, audit_name)


if __name__ == "__main__":
    main()
