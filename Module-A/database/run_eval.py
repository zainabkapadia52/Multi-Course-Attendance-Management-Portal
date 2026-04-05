from .table import Table
from .column import Column
from .join import Join
import os
def clean():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"): os.remove(f)
clean()
parents = Table("parents", "id", [Column("id", "INT", nullable=False), Column("name", "VARCHAR(50)")])
children = Table("children", "id", [Column("id", "INT", nullable=False), Column("parent_id", "INT", nullable=True)])
children.add_foreign_key("parent_id", parents, "id")
parents.insert({"id": 1, "name": "A"}); parents.insert({"id": 2, "name": "B"})
children.insert({"id": 10, "parent_id": 1}); children.insert({"id": 11, "parent_id": 1})
j1 = Join(parents, children).on("id", "parent_id").fetch()
print("PK -> Sec counts:", len(j1))
j2 = Join(children, parents).on("parent_id", "id").fetch()
print("Sec -> PK counts:", len(j2))
j3 = Join(parents, children).on("id", "parent_id").left().fetch()
print("LEFT PK -> Sec counts:", len(j3))
clean()
