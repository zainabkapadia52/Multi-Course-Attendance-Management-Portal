import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.table import Table
from database.column import Column

def clean():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

def print_table(name, table):
    print(f"  Table: {name}")
    rows = table.all_rows()
    if not rows:
        print("    (Empty)")
    for r in rows:
        print("    -", r)

def run_cascade_tests():
    clean()
    print("=" * 70)
    print("Setting up schema for Deep Cascading testing...")
    
    # 1. Departments Table
    departments = Table("departments", "dept_id", [
        Column("dept_id", "INT", nullable=False),
        Column("dept_name", "VARCHAR(50)")
    ])
    
    # 2. Employees Table (Deletes/Updates CASCADE)
    employees = Table("employees", "emp_id", [
        Column("emp_id", "INT", nullable=False),
        Column("dept_id", "INT", nullable=True),
        Column("name", "VARCHAR(50)")
    ])
    employees.add_foreign_key("dept_id", departments, "dept_id", on_delete="CASCADE", on_update="CASCADE")
    
    # 3. Tasks Table (Deletes CASCADE, Updates CASCADE)
    tasks = Table("tasks", "task_id", [
        Column("task_id", "INT", nullable=False),
        Column("emp_id", "INT", nullable=True),
        Column("task_desc", "VARCHAR(50)")
    ])
    tasks.add_foreign_key("emp_id", employees, "emp_id", on_delete="CASCADE", on_update="CASCADE")
    
    # 4. Assets Table (Deletes SET NULL)
    assets = Table("assets", "asset_id", [
        Column("asset_id", "INT", nullable=False),
        Column("emp_id", "INT", nullable=True),
        Column("asset_name", "VARCHAR(50)")
    ])
    assets.add_foreign_key("emp_id", employees, "emp_id", on_delete="SET NULL")

    print("\nInserting data...")
    # Insert Departments
    departments.insert({"dept_id": 1, "dept_name": "Engineering"})
    departments.insert({"dept_id": 2, "dept_name": "HR"})
    
    # Insert Employees
    employees.insert({"emp_id": 10, "dept_id": 1, "name": "Alice"})
    employees.insert({"emp_id": 11, "dept_id": 1, "name": "Bob"})
    employees.insert({"emp_id": 12, "dept_id": 2, "name": "Charlie"})
    
    # Insert Tasks
    tasks.insert({"task_id": 100, "emp_id": 10, "task_desc": "Write Code"})
    tasks.insert({"task_id": 101, "emp_id": 10, "task_desc": "Review PR"})
    tasks.insert({"task_id": 102, "emp_id": 12, "task_desc": "Screen Resumes"})
    
    # Insert Assets
    assets.insert({"asset_id": 900, "emp_id": 10, "asset_name": "MacBook Pro"})
    assets.insert({"asset_id": 901, "emp_id": 11, "asset_name": "Monitor"})

    print("Initial State:")
    print_table("Departments", departments)
    print_table("Employees", employees)
    print_table("Tasks", tasks)
    print_table("Assets", assets)
    print("=" * 70)

    # Test 1: Update CASCADE NOT SUPPORTED BY ENGINE PK directly, skipping PK update.
    # We will instead test ON UPDATE CASCADE by updating a reference if we could.
    # WAIT: If PK updates aren't allowed, ON UPDATE CASCADE on a parent PK is inherently restricted by the DB.
    # We will safely skip PK update tests here and focus deeply on DELETE Cascades!

    # Test 2: DELETE CASCADE (Deep Delete to Tasks) + SET NULL (to Assets)
    print("\n[TEST 2] DELETE CASCADE and SET NULL")
    print("  Action: Delete Engineering Department (dept_id = 1)")
    print("  Expectation: Alice & Bob are cascade deleted. Alice's tasks are deleted. Alice & Bob's assets get emp_id = NULL")
    departments.delete(1)
    
    print_table("Departments", departments)
    print_table("Employees", employees)
    print_table("Tasks", tasks)
    print_table("Assets", assets)
    
    # Verify Employees deleted
    assert len([e for e in employees.all_rows() if e["dept_id"] == 1]) == 0, "Employees were not deleted!"
    
    # Verify Tasks deleted deep cascade
    assert len([t for t in tasks.all_rows() if t["emp_id"] == 10]) == 0, "Tasks were not cascade deleted!"
    
    # Verify Assets set to NULL
    macbook = assets.find(900)
    assert macbook["emp_id"] is None, f"Expected None, got {macbook['emp_id']}"
    monitor = assets.find(901)
    assert monitor["emp_id"] is None, f"Expected None, got {monitor['emp_id']}"
    
    print("  Success: DELETE CASCADE and SET NULL deep cascade passed.")
    print("\n" + "=" * 70)
    print("All cascade tests in usage8.py passed successfully!")
    clean()

if __name__ == "__main__":
    run_cascade_tests()