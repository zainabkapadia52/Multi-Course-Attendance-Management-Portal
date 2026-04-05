from .table import Table
from .column import Column
from .join import Join
import os

def clean():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

clean()

users = Table("users", "id", [
    Column("id", "INT", nullable=False),
    Column("age", "INT")
])
orders = Table("orders", "id", [
    Column("id", "INT", nullable=False),
    Column("user_age", "INT")
])
users.create_index("age")

users.insert({"id": 1, "age": 20})
users.insert({"id": 2, "age": 20})
users.insert({"id": 3, "age": 30})

orders.insert({"id": 99, "user_age": 20})
orders.insert({"id": 100, "user_age": 30})

j = Join(orders, users).on("user_age", "age").fetch()
print(j)
clean()
