import os
import sys

# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db_manager import DatabaseManager, Column

def run_all_examples():
    import os
    for file in os.listdir("."):
        if file.startswith(("Departments", "Employees", "Tasks")):
            os.remove(file)

    print("Initializing Database Manager...")
    db = DatabaseManager()

    # ---------------------------------------------------------
    # Example 1: Defining Schemas and Creating Tables
    # ---------------------------------------------------------
    print("\n[Example 1] Creating Departments and Employees tables.")
    dept_schema = [
        Column("dept_id", "INT"),
        Column("dept_name", "VARCHAR(50)")
    ]
    db.create_table("Departments", primary_key="dept_id", schema=dept_schema)
    
    emp_schema = [
        Column("emp_id", "INT"),
        Column("name", "VARCHAR(50)"),
        Column("dept_id", "INT"),
        Column("salary", "FLOAT")
    ]
    db.create_table("Employees", primary_key="emp_id", schema=emp_schema)

    # ---------------------------------------------------------
    # Example 2: Retrieving a Table Instance
    # ---------------------------------------------------------
    print("\n[Example 2] Retrieving table instances from the manager.")
    departments = db.get_table("Departments")
    employees = db.get_table("Employees")

    # ---------------------------------------------------------
    # Example 3: Adding Foreign Keys (ON DELETE CASCADE)
    # ---------------------------------------------------------
    print("\n[Example 3] Adding Foreign Key with CASCADE.")
    employees.add_foreign_key("dept_id", departments, "dept_id", on_delete="CASCADE")

    # ---------------------------------------------------------
    # Example 4: Creating a Third Table
    # ---------------------------------------------------------
    print("\n[Example 4] Creating Tasks table.")
    task_schema = [
        Column("task_id", "INT"),
        Column("task_desc", "VARCHAR(50)"),
        Column("emp_id", "INT")
    ]
    tasks = db.create_table("Tasks", primary_key="task_id", schema=task_schema)

    # ---------------------------------------------------------
    # Example 5: Adding Foreign Keys (ON DELETE SET NULL)
    # ---------------------------------------------------------
    print("\n[Example 5] Adding Foreign Key with SET NULL.")
    tasks.add_foreign_key("emp_id", employees, "emp_id", on_delete="SET NULL")

    # ---------------------------------------------------------
    # Example 6: Basic Data Insertion
    # ---------------------------------------------------------
    print("\n[Example 6] Inserting data into Departments.")
    departments.insert({"dept_id": 1, "dept_name": "Engineering"})
    departments.insert({"dept_id": 2, "dept_name": "HR"})

    # ---------------------------------------------------------
    # Example 7: Inserting Relational Data
    # ---------------------------------------------------------
    print("\n[Example 7] Inserting data into Employees.")
    employees.insert({"emp_id": 101, "name": "Alice", "dept_id": 1, "salary": 85000.0})
    employees.insert({"emp_id": 102, "name": "Bob", "dept_id": 1, "salary": 90000.0})
    employees.insert({"emp_id": 103, "name": "Charlie", "dept_id": 2, "salary": 60000.0})

    # ---------------------------------------------------------
    # Example 8: Inserting Deeper Relational Data
    # ---------------------------------------------------------
    print("\n[Example 8] Inserting data into Tasks.")
    tasks.insert({"task_id": 1001, "task_desc": "Write Database Engine", "emp_id": 101})
    tasks.insert({"task_id": 1002, "task_desc": "Review PRs", "emp_id": 102})
    tasks.insert({"task_id": 1003, "task_desc": "Onboarding", "emp_id": 103})

    # ---------------------------------------------------------
    # Example 9: Basic Select (Get All)
    # ---------------------------------------------------------
    print("\n[Example 9] Fetching all employees.")
    for emp in employees.all_rows():
        print(emp)

    # ---------------------------------------------------------
    # Example 10: Select with Condition (Direct Table)
    # ---------------------------------------------------------
    print("\n[Example 10] Fetching employees with salary > 80000.")
    high_earners = employees.where("salary", ">", 80000.0).fetch()
    for emp in high_earners:
        print(emp)

    # ---------------------------------------------------------
    # Example 11: Primary Key Lookup (Fast B+ Tree Search)
    # ---------------------------------------------------------
    print("\n[Example 11] Primary Key Lookup for Employee 102.")
    print(employees.find(102))

    # ---------------------------------------------------------
    # Example 12: Updating Data
    # ---------------------------------------------------------
    print("\n[Example 12] Giving Charlie a raise.")
    employees.update(103, {"salary": 65000.0})
    print(employees.find(103))

    # ---------------------------------------------------------
    # Example 13: Attempting to Update Primary Key (Should Fail)
    # ---------------------------------------------------------
    print("\n[Example 13] Trying to update a Primary Key.")
    try:
        employees.update(102, {"emp_id": 999})
    except Exception as e:
        print(f"Expected error caught: {e}")

    # ---------------------------------------------------------
    # Example 14: Creating a DatabaseManager Join
    # ---------------------------------------------------------
    print("\n[Example 14] Joining Employees and Departments.")
    join_q1 = db.join("Employees", "Departments").on("dept_id", "dept_id")
    for row in join_q1.fetch()[:2]: # Show first 2
        print(row)

    # ---------------------------------------------------------
    # Example 15: DatabaseManager Join with Filters
    # ---------------------------------------------------------
    print("\n[Example 15] Joining Employees and Tasks with filters.")
    join_q2 = db.join("Employees", "Tasks").on("emp_id", "emp_id").where("name", "=", "Alice")
    for row in join_q2.fetch():
        print(row)

    # ---------------------------------------------------------
    # Example 16: Successful ACID Transaction
    # ---------------------------------------------------------
    print("\n[Example 16] Running a successful ACID Transaction.")
    try:
        with db.transaction("Departments", "Employees"):
            departments.insert({"dept_id": 3, "dept_name": "Sales"})
            employees.insert({"emp_id": 104, "name": "David", "dept_id": 3, "salary": 70000.0})
        print("Transaction committed.")
    except Exception as e:
        print(f"Transaction failed: {e}")

    # ---------------------------------------------------------
    # Example 17: Rolled-back ACID Transaction
    # ---------------------------------------------------------
    print("\n[Example 17] Running a failing ACID Transaction (Rollback).")
    try:
        with db.transaction("Employees"):
            employees.update(104, {"salary": 100000.0}) # This happens
            raise ValueError("Oh no! System crash!") # But then an error occurs
    except Exception as e:
        print(f"Transaction caught an exception and rolled back: {e}")
    # Verify David's "salary" is still 70000.0
    print(f"David's salary after rollback: {employees.find(104)['salary']}")

    # ---------------------------------------------------------
    # Example 18: Testing SET NULL ON DELETE
    # ---------------------------------------------------------
    print("\n[Example 18] Deleting Employee Charlie (SET NULL in Tasks).")
    # Charlie is emp_id 103, task is 1003
    employees.delete(103)
    task_1003 = tasks.find(1003)
    print(f"Task 1003 after deleting its owner: {task_1003}") # emp_id should be None

    # ---------------------------------------------------------
    # Example 19: Testing CASCADE ON DELETE
    # ---------------------------------------------------------
    print("\n[Example 19] Deleting Engineering Dept (CASCADE to Employees).")
    # Will delete dept 1, which deletes Alice (101) & Bob (102).
    # Then because Alice/Bob were deleted, SET NULL will hit Tasks for 1001 & 1002.
    departments.delete(1)
    
    print(f"Remaining Employees count: {len(employees.all_rows())}") # Only David (104) should remain
    print("Remaining Tasks (notice emp_ids are None):")
    for t in tasks.all_rows():
        print(t)

    # ---------------------------------------------------------
    # Example 20: Dropping a Table
    # ---------------------------------------------------------
    print("\n[Example 20] Dropping the Departments table and its underlying files.")
    db.drop_table("Departments")
    print(f"Managed tables: {db.list_tables()}")


if __name__ == "__main__":
    run_all_examples()
