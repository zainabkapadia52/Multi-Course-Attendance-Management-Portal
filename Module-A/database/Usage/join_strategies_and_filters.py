import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.table import Table
from database.column import Column
from database.join import Join

def clean():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

def print_results(results):
    print("  Results:")
    if not results:
        print("    (Empty)")
    for r in results:
        print("    -", r)

def run_join_tests():
    clean()
    print("=" * 70)
    print("Setting up schema for Join testing...")
    
    # Tables
    categories = Table("categories", "id", [
        Column("id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])
    
    products = Table("products", "id", [
        Column("id", "INT", nullable=False),
        Column("cat_id", "INT", nullable=True),
        Column("name", "VARCHAR(50)"),
        Column("price", "FLOAT")
    ])
    products.add_foreign_key("cat_id", categories, "id", on_delete="CASCADE")
    
    reviews = Table("reviews", "id", [
        Column("id", "INT", nullable=False),
        Column("prod_id", "INT", nullable=True),
        Column("rating", "INT"),
        Column("comment", "VARCHAR(50)")
    ])
    reviews.add_foreign_key("prod_id", products, "id", on_delete="CASCADE")

    print("\nInserting data...")
    print("  Categories:\n    - {1: Electronics, 2: Books, 3: Clothing (Empty)}")
    categories.insert({"id": 1, "name": "Electronics"})
    categories.insert({"id": 2, "name": "Books"})
    categories.insert({"id": 3, "name": "Clothing"}) # No products
    
    print("  Products:\n    - {101: Laptop (cat=1), 102: Smartphone (cat=1), 103: Novel (cat=2), 104: Unknown Item (cat=None)}")
    products.insert({"id": 101, "cat_id": 1, "name": "Laptop", "price": 999.99})
    products.insert({"id": 102, "cat_id": 1, "name": "Smartphone", "price": 499.50})
    products.insert({"id": 103, "cat_id": 2, "name": "Novel", "price": 19.99})
    products.insert({"id": 104, "cat_id": None, "name": "Unknown Item", "price": 5.00}) # Uncategorized
    
    print("  Reviews:\n    - {1001: rating 5 (prod=101), 1002: rating 4 (prod=101), 1003: rating 5 (prod=103)}")
    reviews.insert({"id": 1001, "prod_id": 101, "rating": 5, "comment": "Great!"})
    reviews.insert({"id": 1002, "prod_id": 101, "rating": 4, "comment": "Good"})
    reviews.insert({"id": 1003, "prod_id": 103, "rating": 5, "comment": "Loved it"})
    print("=" * 70)

    # Test 1: PK Join (Child joins Parent on PK) -> _index_nested_loop
    print("\n[TEST 1] PK Join (O(n log m))")
    print("  Query: Products INNER JOIN Categories ON products.cat_id = categories.id")
    print("  Expectation: Matches 101, 102, 103 to their categories, skipping Uncategorized (104)")
    t1 = Join(products, categories).on("cat_id", "id").fetch()
    print_results(t1)
    
    assert len(t1) == 3, f"Expected 3, got {len(t1)}"
    for row in t1:
        assert row["categories.name"] is not None
    print("  Success: PK Join passed.")

    # Test 2: Secondary Index Join (Parent joins Child on FK) -> _secondary_index_join
    print("\n[TEST 2] Secondary Index Join (O(n log m + j))")
    print("  Query: Categories INNER JOIN Products ON categories.id = products.cat_id")
    print("  Expectation: Matches Electronics to 101/102 and Books to 103, Clothing omitted")
    t2 = Join(categories, products).on("id", "cat_id").fetch()
    print_results(t2)
    
    assert len(t2) == 3, f"Expected 3, got {len(t2)}"
    elec_matches = [r for r in t2 if r["id"] == 1]
    assert len(elec_matches) == 2
    print("  Success: Secondary Index Join passed.")

    # Test 3: LEFT JOIN using Secondary Index
    print("\n[TEST 3] LEFT JOIN Secondary Index")
    print("  Query: Categories LEFT JOIN Products ON categories.id = products.cat_id")
    print("  Expectation: Includes all categories (including Clothing) joined with NULLs")
    t3 = Join(categories, products).on("id", "cat_id").left().fetch()
    print_results(t3)
    
    assert len(t3) == 4, f"Expected 4, got {len(t3)}"
    clothing_match = next(r for r in t3 if r["id"] == 3)
    assert clothing_match["products.name"] is None
    print("  Success: LEFT JOIN Secondary Index passed.")

    # Test 4: Nested Loop Join (Unindexed column) -> _nested_loop
    print("\n[TEST 4] Unindexed Nested Loop (O(n * m) fallback)")
    print("  Query: Products INNER JOIN Products ON products.price = products.price")
    print("  Expectation: Un-indexed Join matching prices (4 individual matches since all unique)")
    t4 = Join(products, products).on("price", "price").fetch()
    print_results(t4)
    
    assert len(t4) == 4, f"Expected 4, got {len(t4)}"
    print("  Success: Nested Loop Join passed.")

    # Test 5: Join with WHERE clause
    print("\n[TEST 5] Join with WHERE Clause filtering")
    print("  Query: Categories INNER JOIN Products ON categories.id = products.cat_id WHERE categories.name = 'Electronics'")
    print("  Expectation: Returns exactly 2 overlapping matches for Electronics (Laptop, Smartphone)")
    t5 = Join(categories, products).on("id", "cat_id").where("name", "=", "Electronics").fetch()
    print_results(t5)
    
    assert len(t5) == 2, f"Expected 2, got {len(t5)}"
    print("  Success: Join with WHERE passed.")

    clean()
    print("\n" + "=" * 70)
    print("All tests in usage7.py passed successfully!")

if __name__ == "__main__":
    run_join_tests()

