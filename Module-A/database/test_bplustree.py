from .bplustree import BPlusTree
import random


def test_insert_and_search():
    print("Test: insert + search")

    tree = BPlusTree(order=4)
    data = list(range(20))
    random.shuffle(data)

    for x in data:
        tree.insert(x, x * 10)

    for x in data:
        val = tree.search(x)
        assert val == x * 10, f"Search failed for {x}"

    print("PASS")


def test_sorted_order():
    print("Test: sorted order via get_all")

    tree = BPlusTree(order=4)

    nums = [5, 1, 9, 3, 7, 2]
    for x in nums:
        tree.insert(x, x)

    result = tree.get_all()
    keys = [k for k, _ in result]

    assert keys == sorted(nums), "Keys are not sorted"

    print("PASS")


def test_range_query():
    print("Test: range query")

    tree = BPlusTree(order=4)

    for x in range(20):
        tree.insert(x, x)

    res = tree.range_query(5, 10)
    keys = [k for k, _ in res]

    assert keys == list(range(5, 11)), f"Range query failed: {keys}"

    print("PASS")


def test_delete():
    print("Test: delete")

    tree = BPlusTree(order=4)

    for x in range(10):
        tree.insert(x, x)

    # delete some
    for x in [3, 5, 7]:
        assert tree.delete(x), f"Delete failed for {x}"

    # check deleted
    for x in [3, 5, 7]:
        assert tree.search(x) is None, f"{x} should be deleted"

    # check others still exist
    for x in [0, 1, 2, 4, 6, 8, 9]:
        assert tree.search(x) == x

    print("PASS")


def test_random_operations():
    print("Test: random stress test")

    tree = BPlusTree(order=4)
    reference = {}

    for _ in range(1000):
        op = random.choice(["insert", "delete", "search"])
        key = random.randint(0, 50)

        if op == "insert":
            val = random.randint(0, 1000)
            tree.insert(key, val)
            reference[key] = val

        elif op == "delete":
            res1 = tree.delete(key)
            res2 = key in reference
            if key in reference:
                del reference[key]
            assert res1 == res2

        else:  # search
            val1 = tree.search(key)
            val2 = reference.get(key)
            assert val1 == val2

    print("PASS")

import pdb;

if __name__ == "__main__":
    pdb.set_trace()
    test_insert_and_search()
    # test_sorted_order()
    # test_range_query()
    # test_delete()
    # test_random_operations()

    # print("\nAll tests passed")