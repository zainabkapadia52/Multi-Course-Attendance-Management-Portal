from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BPlusTreeNode:
    leaf: bool
    keys: list[int] = field(default_factory=list)
    children: list["BPlusTreeNode"] = field(default_factory=list)
    values: list[Any] = field(default_factory=list)
    next: "BPlusTreeNode | None" = None


class BPlusTree:
    """In-memory B+ tree supporting exact and range lookups."""

    def __init__(self, order: int = 4) -> None:
        if order < 3:
            raise ValueError("order must be at least 3")
        self.order = order
        self.max_keys = order - 1
        self.root = BPlusTreeNode(leaf=True)

    def search(self, key: int) -> Any | None:
        leaf = self._find_leaf(key)
        idx = bisect_left(leaf.keys, key)
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            return leaf.values[idx]
        return None

    def insert(self, key: int, value: Any) -> None:
        if len(self.root.keys) == self.max_keys:
            old_root = self.root
            self.root = BPlusTreeNode(leaf=False, children=[old_root])
            self._split_child(self.root, 0)

        self._insert_non_full(self.root, key, value)
        self._refresh_separators(self.root)

    def _insert_non_full(self, node: BPlusTreeNode, key: int, value: Any) -> None:
        if node.leaf:
            idx = bisect_left(node.keys, key)
            if idx < len(node.keys) and node.keys[idx] == key:
                node.values[idx] = value
                return
            node.keys.insert(idx, key)
            node.values.insert(idx, value)
            return

        idx = bisect_right(node.keys, key)
        child = node.children[idx]
        if len(child.keys) == self.max_keys:
            self._split_child(node, idx)
            idx = bisect_right(node.keys, key)
        self._insert_non_full(node.children[idx], key, value)

    def _split_child(self, parent: BPlusTreeNode, index: int) -> None:
        child = parent.children[index]
        new_sibling = BPlusTreeNode(leaf=child.leaf)
        mid = len(child.keys) // 2

        if child.leaf:
            new_sibling.keys = child.keys[mid:]
            new_sibling.values = child.values[mid:]
            child.keys = child.keys[:mid]
            child.values = child.values[:mid]

            new_sibling.next = child.next
            child.next = new_sibling

            parent.keys.insert(index, new_sibling.keys[0])
            parent.children.insert(index + 1, new_sibling)
            return

        promoted = child.keys[mid]
        new_sibling.keys = child.keys[mid + 1 :]
        new_sibling.children = child.children[mid + 1 :]

        child.keys = child.keys[:mid]
        child.children = child.children[: mid + 1]

        parent.keys.insert(index, promoted)
        parent.children.insert(index + 1, new_sibling)

    def delete(self, key: int) -> bool:
        deleted = self._delete(self.root, key)

        if not self.root.leaf and len(self.root.keys) == 0:
            self.root = self.root.children[0]

        self._refresh_separators(self.root)
        return deleted

    def _delete(self, node: BPlusTreeNode, key: int) -> bool:
        if node.leaf:
            idx = bisect_left(node.keys, key)
            if idx >= len(node.keys) or node.keys[idx] != key:
                return False
            del node.keys[idx]
            del node.values[idx]
            return True

        idx = bisect_right(node.keys, key)
        child = node.children[idx]
        deleted = self._delete(child, key)
        if not deleted:
            return False

        if child is not self.root and len(child.keys) < self._min_keys(child):
            self._fill_child(node, idx)

        # Child index can change if a merge happened; rebuild it from key.
        self._refresh_separators(node)
        return True

    def _fill_child(self, node: BPlusTreeNode, index: int) -> None:
        if index > 0 and len(node.children[index - 1].keys) > self._min_keys(node.children[index - 1]):
            self._borrow_from_prev(node, index)
            return

        if index < len(node.children) - 1 and len(node.children[index + 1].keys) > self._min_keys(node.children[index + 1]):
            self._borrow_from_next(node, index)
            return

        if index < len(node.children) - 1:
            self._merge(node, index)
        else:
            self._merge(node, index - 1)

    def _borrow_from_prev(self, node: BPlusTreeNode, index: int) -> None:
        child = node.children[index]
        left = node.children[index - 1]

        if child.leaf:
            child.keys.insert(0, left.keys.pop())
            child.values.insert(0, left.values.pop())
            node.keys[index - 1] = child.keys[0]
            return

        moved_child = left.children.pop()
        moved_key = left.keys.pop()

        child.children.insert(0, moved_child)
        child.keys.insert(0, node.keys[index - 1])
        node.keys[index - 1] = moved_key

    def _borrow_from_next(self, node: BPlusTreeNode, index: int) -> None:
        child = node.children[index]
        right = node.children[index + 1]

        if child.leaf:
            child.keys.append(right.keys.pop(0))
            child.values.append(right.values.pop(0))
            node.keys[index] = right.keys[0]
            return

        moved_child = right.children.pop(0)
        moved_key = right.keys.pop(0)

        child.children.append(moved_child)
        child.keys.append(node.keys[index])
        node.keys[index] = moved_key

    def _merge(self, node: BPlusTreeNode, index: int) -> None:
        left = node.children[index]
        right = node.children[index + 1]

        if left.leaf:
            left.keys.extend(right.keys)
            left.values.extend(right.values)
            left.next = right.next
        else:
            left.keys.append(node.keys[index])
            left.keys.extend(right.keys)
            left.children.extend(right.children)

        del node.keys[index]
        del node.children[index + 1]

    def update(self, key: int, new_value: Any) -> bool:
        leaf = self._find_leaf(key)
        idx = bisect_left(leaf.keys, key)
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            leaf.values[idx] = new_value
            return True
        return False

    def range_query(self, start_key: int, end_key: int) -> list[tuple[int, Any]]:
        if start_key > end_key:
            return []

        result: list[tuple[int, Any]] = []
        leaf = self._find_leaf(start_key)

        while leaf is not None:
            for key, value in zip(leaf.keys, leaf.values):
                if key < start_key:
                    continue
                if key > end_key:
                    return result
                result.append((key, value))
            leaf = leaf.next

        return result

    def get_all(self) -> list[tuple[int, Any]]:
        result: list[tuple[int, Any]] = []
        leaf = self._leftmost_leaf()

        while leaf is not None:
            result.extend(list(zip(leaf.keys, leaf.values)))
            leaf = leaf.next

        return result

    def visualize_tree(self, output_path: str = "bplustree", view: bool = False):
        try:
            from graphviz import Digraph
        except ImportError as exc:
            raise ImportError("graphviz package is required for visualize_tree") from exc

        dot = Digraph(comment="B+ Tree")
        dot.attr("node", shape="box", style="rounded")

        self._add_nodes(dot, self.root)
        self._add_edges(dot, self.root)
        dot.render(output_path, format="png", cleanup=True, view=view)
        return dot

    def _add_nodes(self, dot, node: BPlusTreeNode) -> None:
        node_id = str(id(node))
        if node.leaf:
            key_text = ", ".join(str(k) for k in node.keys) if node.keys else "empty"
            dot.node(node_id, f"leaf: {key_text}")
            return

        key_text = ", ".join(str(k) for k in node.keys) if node.keys else "empty"
        dot.node(node_id, f"internal: {key_text}")

        for child in node.children:
            self._add_nodes(dot, child)

    def _add_edges(self, dot, node: BPlusTreeNode) -> None:
        if node.leaf:
            if node.next is not None:
                dot.edge(str(id(node)), str(id(node.next)), style="dashed", color="blue", constraint="false")
            return

        for child in node.children:
            dot.edge(str(id(node)), str(id(child)))
            self._add_edges(dot, child)

    def _find_leaf(self, key: int) -> BPlusTreeNode:
        node = self.root
        while not node.leaf:
            idx = bisect_right(node.keys, key)
            node = node.children[idx]
        return node

    def _leftmost_leaf(self) -> BPlusTreeNode:
        node = self.root
        while not node.leaf:
            node = node.children[0]
        return node

    def _min_keys(self, node: BPlusTreeNode) -> int:
        if node is self.root:
            return 1 if not node.leaf else 0
        if node.leaf:
            return self.order // 2
        return (self.order + 1) // 2 - 1

    def _first_key(self, node: BPlusTreeNode) -> int:
        cursor = node
        while not cursor.leaf:
            cursor = cursor.children[0]
        if not cursor.keys:
            raise ValueError("Tree invariant broken: encountered empty leaf")
        return cursor.keys[0]

    def _refresh_separators(self, node: BPlusTreeNode) -> None:
        if node.leaf:
            return

        for child in node.children:
            self._refresh_separators(child)

        node.keys = [self._first_key(node.children[i + 1]) for i in range(len(node.children) - 1)]
