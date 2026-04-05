"""
This usage example demonstrates the power and simplicity of the new `db_manager.py`.

A new user can import EVERYTHING they need directly from `db_manager.py` without worrying
about the inner workings of Transactions, Heaps, B+ Trees, or Joins.

This script creates:
1. A users table
2. An orders table
3. Links them, joins them, and transacts on them.
"""

import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.db_manager import DatabaseManager, Column

def run_db_platform():
    import os
    for file in os.listdir("."):
        if file.startswith(("app_users", "app_orders")):
            os.remove(file)

    print("--- Database Platform Initialization ---")
    
    # 1. Start the Facade Manager
    db = DatabaseManager()

    # 2. Define Schemas simply
    users_schema = [
        Column("user_id", "INT"),
        Column("name", "VARCHAR(50)"),
        Column("balance", "FLOAT")
    ]
    
    orders_schema = [
        Column("order_id", "INT"),
        Column("user_id", "INT"),
        Column("total", "FLOAT")
    ]

    print("\n[+] Creating Tables...")
    users_table = db.create_table("app_users", primary_key="user_id", schema=users_schema)
    orders_table = db.create_table("app_orders", primary_key="order_id", schema=orders_schema)

    # 3. Add Foreign Key Rules directly to the managed table
    print("[+] Defining Foreign Keys...")
    orders_table.add_foreign_key(
        col_name="user_id", 
        references=users_table, 
        ref_col="user_id", 
        on_delete="CASCADE"
    )

    # 4. Use Transactions directly from the DB Manager
    print("\n[+] Inserting Data Securely within an ACID Transaction...")
    txn = db.transaction("app_users", "app_orders")
    
    try:
        with txn:
            users_table.insert({"user_id": 101, "name": "Alice Wonderland", "balance": 1500.00})
            users_table.insert({"user_id": 102, "name": "Bob Builder", "balance": 50.00})
            
            # Insert orders mapping back to the users
            orders_table.insert({"order_id": 5001, "user_id": 101, "total": 200.00})
            orders_table.insert({"order_id": 5002, "user_id": 101, "total": 350.00})
            orders_table.insert({"order_id": 5003, "user_id": 102, "total": 10.00})
            
        print("    -> Transaction Committed successfully.")
    except Exception as e:
        print(f"    -> Transaction Failed and Rolled Back: {e}")

    # 5. Perform Advanced Queries (Joins) Directly via the Manager
    print("\n[+] Executing Cross-Table Joins...")
    
    # Notice we can pass the table string names! The manager resolves them.
    join_query = db.join("app_users", "app_orders")
    
    # We want Alice's orders exceeding $250
    # The Join.where() applies pre-join filters on the left table ("app_users")
    results = (join_query
               .on("user_id", "user_id")
               .where("name", "=", "Alice Wonderland")
               .fetch())

    # Post-join filtering for the right table condition
    results = [r for r in results if r["total"] > 250.00]

    print(f"\nResults for High-Value Orders from Alice:")
    for row in results:
        print(f"  - Order #{row['order_id']} | User: {row['name']} | "
              f"Current Bal: ${row['balance']} | Order Total: ${row['total']}")

    # 6. Test Cascading Cleanup
    print("\n[+] Deleting Alice... (Cascading to Orders)")
    users_table.delete(101)
    
    remaining_orders = orders_table.all_rows()
    print(f"Remaining Orders in System (Should only be Bob's): {len(remaining_orders)}")
    for order in remaining_orders:
        print(f"  - {order}")


if __name__ == "__main__":
    run_db_platform()
