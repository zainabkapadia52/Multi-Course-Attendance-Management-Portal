import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.table import Table
from database.column import Column
from database.transactions import Transaction

def cleanup():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

def test_transactional_cascade():
    cleanup()
    print("Setting up schema...")

    parents = Table("parents", "id", [
        Column("id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])

    children = Table("children", "id", [
        Column("id", "INT", nullable=False),
        Column("parent_id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])
    children.add_foreign_key("parent_id", parents, "id", on_delete="CASCADE")

    parents.insert({"id": 1, "name": "Parent 1"})
    children.insert({"id": 10, "parent_id": 1, "name": "Child A"})
    children.insert({"id": 11, "parent_id": 1, "name": "Child B"})

    print("Initial state:")
    print("Parents:", parents.all_rows())
    print("Children:", children.all_rows())

    # Create transaction to delete parent
    print("\nStarting Transaction 1: Delete Parent 1")
    txn = Transaction(parents, children)
    txn.begin()
    txn.delete(parents, 1)

    print("After txn operations (uncommitted):")
    print("Parents (heap):", parents.all_rows())
    # Note: all_rows uses _index.get_all(), which sees dirty index updates!
    # children should also be deleted via cascade inside _delete_txn
    print("Children (heap dirty read):", children.all_rows())
    
    assert len(parents.all_rows()) == 0, "Parent should be gone from dirty index"
    assert len(children.all_rows()) == 0, "Children should be gone from dirty index due to cascade"

    print("Rolling back Transaction 1")
    txn.rollback()

    print("After Rollback:")
    print("Parents:", parents.all_rows())
    print("Children:", children.all_rows())
    assert len(parents.all_rows()) == 1, "Parent should be back"
    assert len(children.all_rows()) == 2, "Children should be back"

    print("\nStarting Transaction 2: Delete Parent 1 (and commit)")
    txn2 = Transaction(parents, children)
    txn2.begin()
    txn2.delete(parents, 1)
    txn2.commit()

    print("After Commit:")
    print("Parents:", parents.all_rows())
    print("Children:", children.all_rows())
    assert len(parents.all_rows()) == 0, "Parent should be deleted"
    assert len(children.all_rows()) == 0, "Children should be deleted"
    
    cleanup()
    print("\nTransactional Cascade Tests Passed!")

if __name__ == "__main__":
    test_transactional_cascade()
