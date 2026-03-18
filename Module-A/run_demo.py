from database import BPlusTree, DatabaseManager, PerformanceAnalyzer


def smoke_test() -> None:
    tree = BPlusTree(order=4)
    for key in [10, 20, 5, 6, 12, 30, 7, 17]:
        tree.insert(key, {"id": key, "value": key * 2})

    assert tree.search(12)["value"] == 24
    assert tree.update(12, {"id": 12, "value": 99})
    assert tree.search(12)["value"] == 99
    assert [k for k, _ in tree.range_query(6, 17)] == [6, 7, 10, 12, 17]
    assert tree.delete(6)
    assert tree.search(6) is None

    db = DatabaseManager()
    members = db.create_table("members", order=4)
    members.insert(1, {"name": "Alex"})
    members.insert(2, {"name": "Sam"})
    assert members.select(1) == {"name": "Alex"}

    analyzer = PerformanceAnalyzer(order=16)
    results = analyzer.run(sizes=[100, 1000], searches=50, deletes=20, ranges=20)
    for row in analyzer.to_rows(results):
        print(row)


if __name__ == "__main__":
    smoke_test()
    print("Module A smoke test passed")
