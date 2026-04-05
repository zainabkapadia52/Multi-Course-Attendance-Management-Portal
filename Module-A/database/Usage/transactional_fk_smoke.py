import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.table import Table
from database.column import Column
from database.transactions import Transaction

def clean():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

clean()

parents = Table("parents2", "id", [
    Column("id", "INT", nullable=False),
    Column("name", "VARCHAR(50)")
])
children = Table("children2", "id", [
    Column("id", "INT", nullable=False),
    Column("parent_id", "INT", nullable=False)
])
children.add_foreign_key("parent_id", parents, "id", on_delete="CASCADE")

txn = Transaction(parents, children)
txn.begin()
txn.insert(parents, {"id": 1, "name": "Txn P"})
txn.insert(children, {"id": 99, "parent_id": 1})
txn.update(children, 99, {"parent_id": 1})
txn.delete(parents, 1)
txn.commit()
print("Success. Children count:", len(children.all_rows()))
clean()
