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


def ids(rows: list[dict]) -> list[int]:
    return sorted(row["id"] for row in rows)


# ------------------------------------------------------------------
# Schema + seed
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


def seed(users: Table) -> None:
    users.insert({"id": 1, "name": "Alice", "age": 30, "score": 95.5, "active": True})
    users.insert({"id": 2, "name": "Bob", "age": 22, "score": 70.0, "active": False})
    users.insert({"id": 3, "name": "Carol", "age": 28, "score": 88.0, "active": True})
    users.insert({"id": 4, "name": "Dave", "age": 19, "score": None, "active": True})
    users.insert({"id": 5, "name": "Eve", "score": None})  # age default=0, active default=True
    users.insert({"id": 6, "name": "Frank", "age": 35, "score": 60.0, "active": False})


# ------------------------------------------------------------------
# Brutal tests for table.where(...)
# ------------------------------------------------------------------

def test_leaf_ops(users: Table) -> None:
    sep("TEST 1: LEAF OPS")

    assert_equal(ids(users.where("id", "=", 3).fetch()), [3], "id = should match exactly")
    assert_equal(ids(users.where("id", "IN", [1, 3, 6]).fetch()), [1, 3, 6], "id IN should match set")
    assert_equal(ids(users.where("id", "BETWEEN", (2, 4)).fetch()), [2, 3, 4], "id BETWEEN should be inclusive")

    assert_equal(ids(users.where("age", ">", 25).fetch()), [1, 3, 6], "age > should match rows")
    assert_equal(ids(users.where("age", "<=", 22).fetch()), [2, 4, 5], "age <= should include defaults")
    assert_equal(ids(users.where("name", "!=", "Alice").fetch()), [2, 3, 4, 5, 6], "!= should exclude one")

    assert_equal(ids(users.where("score", "IS NULL").fetch()), [4, 5], "IS NULL should match nulls")
    assert_equal(ids(users.where("score", "IS NOT NULL").fetch()), [1, 2, 3, 6], "IS NOT NULL should exclude nulls")

    print("Leaf operator tests passed.")


def test_fluent_combinators(users: Table) -> None:
    sep("TEST 2: FLUENT COMBINATORS")

    q1 = users.where("age", ">", 20).and_("active", "=", True)
    assert_equal(ids(q1.fetch()), [1, 3], "AND should narrow results")

    q2 = users.where("active", "=", False).or_("score", "IS NULL")
    assert_equal(ids(q2.fetch()), [2, 4, 5, 6], "OR should union branches")

    q3 = users.where("active", "=", True).and_not("score", "IS NULL")
    assert_equal(ids(q3.fetch()), [1, 3], "AND NOT should exclude null score among active")

    q4 = users.where("name", "=", "Alice").or_not("active", "=", True)
    assert_equal(ids(q4.fetch()), [1, 2, 6], "OR NOT should include rows where NOT(active=True)")

    print("Fluent combinator tests passed.")


def test_count_first(users: Table) -> None:
    sep("TEST 3: COUNT + FIRST")

    query = users.where("age", ">=", 28)
    assert_equal(query.count(), 3, "count should match fetch length")

    first = users.where("id", "=", 2).first()
    assert_true(first is not None, "first should return row when available")
    assert_equal(first["name"], "Bob", "first should return expected row")

    none_row = users.where("id", "=", 999).first()
    assert_equal(none_row, None, "first should return None for no matches")

    print("Count/first tests passed.")


def test_validation_and_errors(users: Table) -> None:
    sep("TEST 4: VALIDATION + ERROR PATHS")

    bad_op_raised = False
    try:
        users.where("age", "LIKE", "2%")
    except ValueError:
        bad_op_raised = True
    assert_true(bad_op_raised, "unsupported op should raise ValueError")

    bad_between_raised = False
    try:
        users.where("age", "BETWEEN", (10,))
    except ValueError:
        bad_between_raised = True
    assert_true(bad_between_raised, "invalid BETWEEN payload should raise")

    missing_col_raised = False
    try:
        users.where("unknown_col", "=", 1).fetch()
    except KeyError:
        missing_col_raised = True
    assert_true(missing_col_raised, "unknown column in row evaluation should raise")

    print("Validation/error tests passed.")


def test_transaction_visibility(users: Table, orders: Table) -> None:
    sep("TEST 5: TRANSACTION VISIBILITY + WHERE")

    # Commit path: newly committed rows must be visible to where().
    with Transaction(users, orders) as txn:
        txn.insert(users, {"id": 100, "name": "TxnCommit", "age": 40, "score": 99.0, "active": True})
        txn.insert(orders, {"order_id": 900, "user_id": 100, "amount": 123.45, "status": "paid"})

    committed = users.where("id", "=", 100).first()
    assert_true(committed is not None, "committed txn row should be visible")

    # Rollback path: staged rows must not survive.
    rollback_seen = False
    try:
        with Transaction(users, orders) as txn:
            txn.insert(users, {"id": 101, "name": "TxnRollback", "age": 50, "score": 1.0, "active": False})
            txn.insert(orders, {"order_id": 901, "user_id": 101, "amount": 9.99})
            raise RuntimeError("force rollback")
    except RuntimeError:
        rollback_seen = True

    assert_true(rollback_seen, "forced rollback exception should propagate")
    assert_equal(users.where("id", "=", 101).first(), None, "rolled back user should not be visible")

    print("Transaction visibility tests passed.")


def test_reload(users_name: str, users: Table) -> Table:
    sep("TEST 6: RELOAD BEHAVIOR")

    users.close()
    users = Table(users_name, primary_key="id", schema=USERS_SCHEMA)

    # Pre-existing committed row
    assert_true(users.where("id", "=", 100).first() is not None, "committed txn row should persist")
    # Rolled back row should remain absent
    assert_equal(users.where("id", "=", 101).first(), None, "rolled back row should remain absent")

    print("Reload tests passed.")
    return users


def test_mini_stress(users: Table) -> None:
    sep("TEST 7: MINI STRESS (CHAINED WHERE)")

    for i in range(30):
        pk = 1000 + i
        users.insert(
            {
                "id": pk,
                "name": f"U{pk}",
                "age": 18 + (i % 10),
                "score": None if i % 7 == 0 else float(i),
                "active": i % 3 != 0,
            }
        )

    result = (
        users.where("id", ">=", 1000)
        .and_("id", "<=", 1029)
        .and_("age", "BETWEEN", (20, 25))
        .and_not("score", "IS NULL")
        .or_("name", "=", "Alice")
        .fetch()
    )

    # We cannot precompute exact IDs here without duplicating logic,
    # but we can enforce strong sanity constraints.
    assert_true(len(result) > 0, "stress query should return at least one row")

    for row in result:
        in_stress_band = (
            1000 <= row["id"] <= 1029
            and 20 <= row["age"] <= 25
            and row["score"] is not None
        )
        assert_true(in_stress_band or row["name"] == "Alice", "result row must satisfy full predicate")

    print("Mini stress tests passed.")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    users_name = "users3"
    orders_name = "orders3"

    cleanup(users_name, orders_name)

    users = Table(users_name, primary_key="id", schema=USERS_SCHEMA)
    orders = Table(orders_name, primary_key="order_id", schema=ORDERS_SCHEMA)

    try:
        seed(users)
        test_leaf_ops(users)
        test_fluent_combinators(users)
        test_count_first(users)
        test_validation_and_errors(users)
        test_transaction_visibility(users, orders)
        users = test_reload(users_name, users)
        test_mini_stress(users)

        sep("ALL WHERE/QUERY BRUTAL TESTS PASSED")
    finally:
        users.close()
        orders.close()
        cleanup(users_name, orders_name)


if __name__ == "__main__":
    main()
