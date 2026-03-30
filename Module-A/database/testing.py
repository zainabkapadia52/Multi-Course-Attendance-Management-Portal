from table import Table
from bplustree import BPlusTree

tree = BPlusTree()
tree.insert(1, {"user_id": 1, "name": "Alice", "balance": 500})
tree.search(1)

# With Table
users = Table("users", primary_key="user_id")
users.insert({"user_id": 1, "name": "Alice", "balance": 500})  # key extracted automatically
print(users.get(1))