from database.db_manager import DatabaseManager
from database.column import Column

import os


def cleanup():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def run_brutal_test():
    cleanup()
    print("\n=== BRUTAL DATABASE MANAGER TEST ===")

    db = DatabaseManager()

    # --------------------------------------------------
    # 1. CREATE TABLES
    # --------------------------------------------------
    users = db.create_table("users", "id", [
        Column("id", "INT", nullable=False),
        Column("name", "VARCHAR(50)"),
        Column("age", "INT"),
    ])

    orders = db.create_table("orders", "id", [
        Column("id", "INT", nullable=False),
        Column("user_id", "INT"),
        Column("amount", "FLOAT"),
    ])

    payments = db.create_table("payments", "id", [
        Column("id", "INT", nullable=False),
        Column("order_id", "INT"),
        Column("status", "VARCHAR(20)")
    ])

    # FK chain
    orders.add_foreign_key("user_id", users, "id", on_delete="CASCADE")
    payments.add_foreign_key("order_id", orders, "id", on_delete="CASCADE")

    print("Tables created:", db.list_tables())

    # --------------------------------------------------
    # 2. BULK INSERT
    # --------------------------------------------------
    for i in range(1, 6):
        users.insert({"id": i, "name": f"User{i}", "age": 20 + i})

    for i in range(1, 11):
        orders.insert({"id": i, "user_id": (i % 5) + 1, "amount": i * 10.0})

    for i in range(1, 21):
        payments.insert({"id": i, "order_id": (i % 10) + 1, "status": "paid"})

    print("Inserted data")

    # --------------------------------------------------
    # 3. JOIN TESTS
    # --------------------------------------------------
    print("\n--- JOIN TESTS ---")

    j1 = db.join("orders", "users").on("user_id", "id").fetch()
    assert_true(len(j1) == 10, "PK join failed")

    j2 = db.join("users", "orders").on("id", "user_id").fetch()
    assert_true(len(j2) == 10, "Secondary index join failed")

    j3 = db.join("users", "orders").on("id", "user_id").left().fetch()
    assert_true(len(j3) >= 5, "LEFT join failed")

    j4 = db.join("orders", "orders").on("amount", "amount").fetch()
    assert_true(len(j4) == 10, "Nested loop join failed")

    print("Join tests passed")

    # --------------------------------------------------
    # 4. TRANSACTION COMMIT
    # --------------------------------------------------
    print("\n--- TRANSACTION COMMIT ---")

    with db.transaction("users", "orders") as txn:
        txn.insert(users, {"id": 100, "name": "TxnUser", "age": 99})
        txn.insert(orders, {"id": 200, "user_id": 100, "amount": 500.0})

    assert_true(users.find(100) is not None, "Txn commit failed (users)")
    assert_true(orders.find(200) is not None, "Txn commit failed (orders)")

    print("Commit test passed")

    # --------------------------------------------------
    # 5. TRANSACTION ROLLBACK
    # --------------------------------------------------
    print("\n--- TRANSACTION ROLLBACK ---")

    try:
        with db.transaction("users", "orders") as txn:
            txn.insert(users, {"id": 101, "name": "RollbackUser", "age": 50})
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    assert_true(users.find(101) is None, "Rollback failed")

    print("Rollback test passed")

    # --------------------------------------------------
    # 6. CASCADE DELETE
    # --------------------------------------------------
    print("\n--- CASCADE TEST ---")

    users.delete(1)

    for o in orders.all_rows():
        assert_true(o["user_id"] != 1, "Cascade failed (orders)")

    for p in payments.all_rows():
        assert_true(
            orders.find(p["order_id"]) is not None,
            "Cascade failed (payments)"
        )

    print("Cascade test passed")

    # --------------------------------------------------
    # 7. RELOAD TEST
    # --------------------------------------------------
    print("\n--- RELOAD TEST ---")

    users.close()
    orders.close()
    payments.close()

    users = db.create_table("users", "id", [
        Column("id", "INT", nullable=False),
        Column("name", "VARCHAR(50)"),
        Column("age", "INT"),
    ])

    orders = db.create_table("orders", "id", [
        Column("id", "INT", nullable=False),
        Column("user_id", "INT"),
        Column("amount", "FLOAT"),
    ])

    print("Reload complete")

    # --------------------------------------------------
    # 8. DROP TABLE
    # --------------------------------------------------
    print("\n--- DROP TABLE ---")

    assert_true(db.drop_table("payments"), "Drop failed")
    assert_true("payments" not in db.list_tables(), "Drop not reflected")

    print("Drop test passed")

    # --------------------------------------------------
    # 9. EDGE CASES
    # --------------------------------------------------
    print("\n--- EDGE CASES ---")

    try:
        db.create_table("users", "id", [])
        assert False, "Duplicate table allowed"
    except ValueError:
        pass

    try:
        db.get_table("nonexistent")
        assert False, "Nonexistent table accessed"
    except KeyError:
        pass

    print("Edge cases passed")

    cleanup()
    print("\n=== ALL BRUTAL TESTS PASSED ===")


if __name__ == "__main__":
    run_brutal_test()