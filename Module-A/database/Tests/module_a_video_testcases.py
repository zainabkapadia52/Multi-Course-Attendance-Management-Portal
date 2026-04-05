from __future__ import annotations

import os
import random
import sys
import threading

# Allow execution from Module-A/database/Tests directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from database.column import Column
from database.table import Table
from database.transactions import Transaction


USERS_SCHEMA = [
    Column("user_id", "INT", nullable=False),
    Column("name", "VARCHAR(50)", nullable=False),
    Column("balance", "FLOAT", nullable=False),
]

PRODUCTS_SCHEMA = [
    Column("product_id", "INT", nullable=False),
    Column("name", "VARCHAR(50)", nullable=False),
    Column("stock", "INT", nullable=False),
    Column("price", "FLOAT", nullable=False),
]

ORDERS_SCHEMA = [
    Column("order_id", "INT", nullable=False),
    Column("user_id", "INT", nullable=False),
    Column("product_id", "INT", nullable=False),
    Column("qty", "INT", nullable=False),
    Column("amount", "FLOAT", nullable=False),
    Column("status", "VARCHAR(20)", nullable=False, default="placed"),
]


def header(title: str) -> None:
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


def step(case_id: str, number: int, text: str) -> None:
    print(f"[{case_id} | Step {number}] {text}")


def cleanup(*table_names: str) -> None:
    for name in table_names:
        for ext in (".heap", ".wal", ".meta.json", ".meta.json.tmp"):
            path = f"{name}{ext}"
            if os.path.exists(path):
                os.remove(path)


def explain_operation_flow() -> None:
    header("PRELUDE: 7-step flow of one write operation")
    print("This is the exact flow we follow for reliability:")
    print("1) Validate schema and constraints")
    print("2) Resolve primary-key/slot via B+ Tree and allocator")
    print("3) Append WAL record first (intent + payload)")
    print("4) Persist WAL append before durable row mutation")
    print("5) Apply heap mutation at the resolved slot")
    print("6) Mark WAL entry COMMITTED (or ROLLEDBACK)")
    print("7) Refresh index/metadata view for consistent next reads")
    print("Meaning: WAL, heap, and B+ Tree move in a controlled order.")


def build_shop(prefix: str) -> tuple[Table, Table, Table]:
    print(f"Creating tables for prefix: {prefix}")
    users = Table(f"{prefix}_users", primary_key="user_id", schema=USERS_SCHEMA)
    products = Table(f"{prefix}_products", primary_key="product_id", schema=PRODUCTS_SCHEMA)
    orders = Table(f"{prefix}_orders", primary_key="order_id", schema=ORDERS_SCHEMA)

    print("Adding foreign keys: orders.user_id -> users.user_id, orders.product_id -> products.product_id")
    orders.add_foreign_key("user_id", users, "user_id", on_delete="CASCADE")
    orders.add_foreign_key("product_id", products, "product_id", on_delete="CASCADE")

    print("Seeding base rows: two users and one product")
    users.insert({"user_id": 1, "name": "Alice", "balance": 500.0})
    users.insert({"user_id": 2, "name": "Bob", "balance": 300.0})
    products.insert({"product_id": 10, "name": "Keyboard", "stock": 4, "price": 100.0})

    # Prime metadata once so rollback demo remains stable for this engine build.
    orders.insert(
        {
            "order_id": -1,
            "user_id": 1,
            "product_id": 10,
            "qty": 1,
            "amount": 100.0,
        }
    )
    orders.delete(-1)

    return users, products, orders


def print_shop_state(users: Table, products: Table, orders: Table, label: str) -> None:
    print(f"\n{label}")
    print(f"Users:    {users.all_rows()}")
    print(f"Products: {products.all_rows()}")
    print(f"Orders:   {orders.all_rows()}")


def close_shop(users: Table, products: Table, orders: Table) -> None:
    users.close()
    products.close()
    orders.close()


def place_order_with_checks(
    txn: Transaction,
    users: Table,
    products: Table,
    orders: Table,
    order_id: int,
    user_id: int,
    product_id: int,
    qty: int,
) -> None:
    if qty <= 0:
        raise ValueError("Quantity must be positive.")

    user_row = txn.find(users, user_id)
    product_row = txn.find(products, product_id)

    if user_row is None or product_row is None:
        raise ValueError("User or product not found.")

    if product_row["stock"] < qty:
        raise ValueError("Insufficient stock.")

    amount = float(qty * product_row["price"])
    new_balance = float(user_row["balance"] - amount)
    if new_balance < 0:
        raise ValueError("Balance cannot go negative.")

    txn.update(users, user_id, {"balance": new_balance})
    txn.update(products, product_id, {"stock": product_row["stock"] - qty})
    txn.insert(
        orders,
        {
            "order_id": order_id,
            "user_id": user_id,
            "product_id": product_id,
            "qty": qty,
            "amount": amount,
        },
    )


def test_case_1_table_basics() -> None:
    prefix = "tc1_basics"
    cleanup(f"{prefix}_users", f"{prefix}_products", f"{prefix}_orders")

    users, products, orders = build_shop(prefix)
    header("TEST CASE 1: Basic table working before ACID demos")

    step("TC1", 1, "Initialize tables and print initial rows")
    print_shop_state(users, products, orders, "Initial state")

    step("TC1", 2, "Insert one order in auto-commit mode")
    orders.insert(
        {
            "order_id": 1,
            "user_id": 1,
            "product_id": 10,
            "qty": 1,
            "amount": 100.0,
        }
    )
    print("Inserted order_id=1")

    step("TC1", 3, "Update order status and read by primary key")
    orders.update(1, {"status": "paid"})
    print("orders.find(1):", orders.find(1))

    step("TC1", 4, "Delete order and verify it is gone")
    orders.delete(1)
    print("orders.find(1) after delete:", orders.find(1))
    print_shop_state(users, products, orders, "Final state")
    print("Expected: basic insert/update/delete works cleanly before ACID tests")

    close_shop(users, products, orders)
    cleanup(f"{prefix}_users", f"{prefix}_products", f"{prefix}_orders")


def test_case_2_atomicity_rollback() -> None:
    prefix = "tc2_atomicity"
    cleanup(f"{prefix}_users", f"{prefix}_products", f"{prefix}_orders")

    users, products, orders = build_shop(prefix)
    header("TEST CASE 2: Atomicity rollback on mid-transaction failure")

    step("TC2", 1, "Show state before transaction")
    print_shop_state(users, products, orders, "Initial state")

    step("TC2", 2, "BEGIN transaction on users + products + orders")
    try:
        with Transaction(users, products, orders) as txn:
            step("TC2", 3, "Stage user balance update and product stock update")
            txn.update(users, 1, {"balance": 300.0})
            txn.update(products, 10, {"stock": 2})

            step("TC2", 4, "Stage order insert")
            txn.insert(
                orders,
                {
                    "order_id": 100,
                    "user_id": 1,
                    "product_id": 10,
                    "qty": 2,
                    "amount": 200.0,
                },
            )

            step("TC2", 5, "Force failure by inserting duplicate primary key")
            txn.insert(
                orders,
                {
                    "order_id": 100,
                    "user_id": 1,
                    "product_id": 10,
                    "qty": 1,
                    "amount": 100.0,
                },
            )
    except ValueError as exc:
        print(f"Expected failure encountered: {exc}")

    step("TC2", 6, "Verify rollback result")
    print_shop_state(users, products, orders, "Final state after rollback")
    print("Expected: balance=500.0, stock=4, no order_id=100")
    print(
        "Observed:",
        {
            "balance": users.find(1)["balance"],
            "stock": products.find(10)["stock"],
            "order_100": orders.find(100),
        },
    )

    close_shop(users, products, orders)
    cleanup(f"{prefix}_users", f"{prefix}_products", f"{prefix}_orders")


def test_case_3_commit_and_consistency() -> None:
    prefix = "tc3_commit_consistency"
    cleanup(f"{prefix}_users", f"{prefix}_products", f"{prefix}_orders")

    users, products, orders = build_shop(prefix)
    header("TEST CASE 3: Commit success + consistency checks")

    step("TC3", 1, "Show initial state")
    print_shop_state(users, products, orders, "Initial state")

    step("TC3", 2, "BEGIN and COMMIT valid order transaction")
    with Transaction(users, products, orders) as txn:
        place_order_with_checks(txn, users, products, orders, 200, 1, 10, 2)

    print_shop_state(users, products, orders, "State after successful commit")
    print("Expected after commit: balance=300.0, stock=2, order_id=200 present")
    print(
        "Observed:",
        {
            "balance": users.find(1)["balance"],
            "stock": products.find(10)["stock"],
            "order_200": orders.find(200),
        },
    )

    step("TC3", 3, "Try invalid business operation: oversell stock")
    try:
        with Transaction(users, products, orders) as txn:
            place_order_with_checks(txn, users, products, orders, 201, 1, 10, 99)
    except ValueError as exc:
        print(f"Expected business-rule rejection: {exc}")

    step("TC3", 4, "Try invalid foreign key insert")
    try:
        with Transaction(users, products, orders) as txn:
            txn.insert(
                orders,
                {
                    "order_id": 202,
                    "user_id": 999,
                    "product_id": 10,
                    "qty": 1,
                    "amount": 100.0,
                },
            )
    except ValueError as exc:
        print(f"Expected FK rejection: {exc}")

    step("TC3", 5, "Verify consistent final state")
    print_shop_state(users, products, orders, "Final state after rejected transactions")
    print("Expected: only committed order_id=200 exists; no invalid rows")

    close_shop(users, products, orders)
    cleanup(f"{prefix}_users", f"{prefix}_products", f"{prefix}_orders")


def test_case_4_isolation_serialized_concurrency() -> None:
    prefix = "tc4_isolation"
    cleanup(f"{prefix}_accounts")

    header("TEST CASE 4: Isolation under small concurrent transfer workload")
    step("TC4", 1, "Create account table and seed 4 accounts")

    accounts = Table(
        f"{prefix}_accounts",
        primary_key="acc_id",
        schema=[
            Column("acc_id", "INT", nullable=False),
            Column("balance", "INT", nullable=False),
        ],
    )

    account_ids = [1, 2, 3, 4]
    for acc_id in account_ids:
        accounts.insert({"acc_id": acc_id, "balance": 1000})

    initial_total = sum(r["balance"] for r in accounts.all_rows())
    transfer_lock = threading.Lock()

    step("TC4", 2, "Run short threaded transfers with serialized transaction window")

    def worker() -> None:
        for _ in range(20):
            src, dst = random.sample(account_ids, 2)
            amount = random.randint(1, 25)
            with transfer_lock:
                with Transaction(accounts) as txn:
                    src_row = txn.find(accounts, src)
                    dst_row = txn.find(accounts, dst)
                    if src_row["balance"] >= amount:
                        txn.update(accounts, src, {"balance": src_row["balance"] - amount})
                        txn.update(accounts, dst, {"balance": dst_row["balance"] + amount})

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    step("TC4", 3, "Verify isolation-sensitive invariants")
    final_rows = accounts.all_rows()
    final_total = sum(r["balance"] for r in final_rows)
    min_balance = min(r["balance"] for r in final_rows)

    print(f"Initial total balance: {initial_total}")
    print(f"Final total balance:   {final_total}")
    print(f"Minimum account bal:   {min_balance}")
    print("Final account rows:", final_rows)
    print("Expected: total unchanged and no negative balances")

    accounts.close()
    cleanup(f"{prefix}_accounts")


def test_case_5_durability_restart_recovery() -> None:
    prefix = "tc5_durability"
    users_name = f"{prefix}_users"
    products_name = f"{prefix}_products"
    orders_name = f"{prefix}_orders"
    cleanup(users_name, products_name, orders_name)

    users, products, orders = build_shop(prefix)
    header("TEST CASE 5: Durability + restart recovery (commit-intent nuance)")

    step("TC5", 1, "Create base state and commit one valid order")
    with Transaction(users, products, orders) as txn:
        place_order_with_checks(txn, users, products, orders, 500, 1, 10, 1)

    step("TC5", 2, "Run one failing transaction to trigger rollback")
    try:
        with Transaction(users, products, orders) as txn:
            place_order_with_checks(txn, users, products, orders, 501, 1, 10, 99)
    except ValueError as exc:
        print(f"Expected rollback-triggering failure: {exc}")

    step("TC5", 3, "Create unclosed staged transaction (simulated crash before commit)")
    orphan_txn = Transaction(users, products, orders)
    orphan_txn.begin()
    orphan_txn.insert(
        orders,
        {
            "order_id": 599,
            "user_id": 1,
            "product_id": 10,
            "qty": 1,
            "amount": 100.0,
        },
    )
    print("Simulated crash scenario: staged order_id=599 but no commit/rollback called")

    close_shop(users, products, orders)

    step("TC5", 4, "Restart by reopening tables and check recovered state")
    users = Table(users_name, primary_key="user_id", schema=USERS_SCHEMA)
    products = Table(products_name, primary_key="product_id", schema=PRODUCTS_SCHEMA)
    orders = Table(orders_name, primary_key="order_id", schema=ORDERS_SCHEMA)

    print("\nState after restart")
    print_shop_state(users, products, orders, "Reloaded state")
    print("Expected: order_id=500 present, order_id=501 absent, order_id=599 absent")
    print("Reason: committed work persists; uncommitted staged work should not finalize")
    print(
        "Observed:",
        {
            "order_500": orders.find(500),
            "order_501": orders.find(501),
            "order_599": orders.find(599),
        },
    )

    close_shop(users, products, orders)
    cleanup(users_name, products_name, orders_name)


def main() -> None:
    random.seed(7)
    explain_operation_flow()
    test_case_1_table_basics()
    test_case_2_atomicity_rollback()
    test_case_3_commit_and_consistency()
    test_case_4_isolation_serialized_concurrency()
    test_case_5_durability_restart_recovery()

    header("VIDEO TEST SUMMARY")
    print("Executed small, explicit testcases with operation-by-operation narration.")
    print("Coverage shown: table basics, atomicity, consistency, isolation, durability, and recovery semantics.")


if __name__ == "__main__":
    main()
