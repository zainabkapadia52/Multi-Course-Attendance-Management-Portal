from __future__ import annotations
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BPlusTreeNode:
    leaf: bool
    keys: list[Any] = field(default_factory=list)
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

    def search(self, key: Any) -> Any | None:
        leaf = self._find_leaf(key)
        idx = bisect_left(leaf.keys, key)
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            return leaf.values[idx]
        return None

    def insert(self, key: Any, value: Any) -> None:
        promoted_key = self._insert_recursive(self.root, key, value)
        
        # If a key was promoted from the root, create a new root
        if promoted_key is not None:
            new_root = BPlusTreeNode(leaf=False)
            new_root.keys = [promoted_key[0]]
            new_root.children = [self.root, promoted_key[1]]
            self.root = new_root

    def _insert_recursive(self, node: BPlusTreeNode, key: Any, value: Any) -> tuple[int, BPlusTreeNode] | None:
        """
        Insert into node. Returns (promoted_key, new_sibling) if node splits, None otherwise.
        """
        if node.leaf:
            idx = bisect_left(node.keys, key)
            if idx < len(node.keys) and node.keys[idx] == key:
                node.values[idx] = value
                return None
            
            node.keys.insert(idx, key)
            node.values.insert(idx, value)
            
            # Split only if we exceeded max_keys
            if len(node.keys) > self.max_keys:
                return self._split_leaf(node)
            return None

        # Internal node
        idx = bisect_right(node.keys, key)
        promoted = self._insert_recursive(node.children[idx], key, value)
        
        if promoted is None:
            return None
        
        # A child split, insert the promoted key
        promoted_key, new_child = promoted
        node.keys.insert(idx, promoted_key)
        node.children.insert(idx + 1, new_child)
        
        # Split this internal node if it now exceeds max_keys
        if len(node.keys) > self.max_keys:
            return self._split_internal(node)
        return None
    
    def _split_leaf(self, node: BPlusTreeNode) -> tuple[int, BPlusTreeNode]:
        """Split a leaf node and return (promoted_key, new_sibling)."""
        mid = len(node.keys) // 2
        new_sibling = BPlusTreeNode(leaf=True)
        
        new_sibling.keys = node.keys[mid:]
        new_sibling.values = node.values[mid:]
        node.keys = node.keys[:mid]
        node.values = node.values[:mid]
        
        new_sibling.next = node.next
        node.next = new_sibling
        
        return (new_sibling.keys[0], new_sibling)
    
    def _split_internal(self, node: BPlusTreeNode) -> tuple[int, BPlusTreeNode]:
        """Split an internal node and return (promoted_key, new_sibling)."""
        mid = len(node.keys) // 2
        promoted_key = node.keys[mid]
        
        new_sibling = BPlusTreeNode(leaf=False)
        new_sibling.keys = node.keys[mid + 1:]
        new_sibling.children = node.children[mid + 1:]
        
        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]
        
        return (promoted_key, new_sibling)


    def delete(self, key: int) -> bool:
        deleted, _ = self._delete(self.root, key)
        while not self.root.leaf and len(self.root.keys) == 0:
            self.root = self.root.children[0]
        return deleted

    def _delete(self, node: BPlusTreeNode, key: int) -> tuple[bool, int | None]:
        if node.leaf:
            idx = bisect_left(node.keys, key)
            if idx >= len(node.keys) or node.keys[idx] != key:
                return False, None
            del node.keys[idx]
            del node.values[idx]
            new_min = node.keys[0] if node.keys else None
            return True, new_min

        idx = bisect_right(node.keys, key)
        deleted, _ = self._delete(node.children[idx], key)
        if not deleted:
            return False, None

        idx = min(idx, len(node.children) - 1)

        child_node = node.children[idx]
        # A child that is not the root must satisfy minimum-occupancy invariants.
        if child_node.leaf:
            underflows = len(child_node.keys) < self._min_keys(child_node)
        else:
            underflows = len(child_node.children) < math.ceil(self.order / 2)
        if underflows:
            num_children_before = len(node.children)
            self._fill_child(node, idx)
            merge_happened = len(node.children) < num_children_before

            # After a merge the merged node sits at the lower of the two indices.
            if merge_happened:
                affected_idx = idx - 1 if idx >= len(node.children) else idx
            else:
                affected_idx = idx

            # If the affected child is an internal node, refresh its own separators
            # so that subsequent traversals route correctly through it.
            affected = node.children[affected_idx]
            if not affected.leaf:
                affected.keys = [
                    self._first_key(affected.children[i + 1])
                    for i in range(len(affected.children) - 1)
                ]

        # Rebuild this node's separator keys from the actual first keys of subtrees.
        node.keys = [
            self._first_key(node.children[i + 1])
            for i in range(len(node.children) - 1)
        ]

        new_min = self._first_key(node.children[0]) if node.children else None
        return True, new_min

    def _fill_child(self, node: BPlusTreeNode, index: int) -> int | None:
        if len(node.children) <= 1:
            return None

        child = node.children[index]

        # Try to borrow from left sibling
        if index > 0 and len(node.children[index - 1].keys) > self._min_keys(node.children[index - 1]):
            self._borrow_from_prev(node, index)
            return node.keys[index - 1]

        # Try to borrow from right sibling
        if index < len(node.children) - 1 and len(node.children[index + 1].keys) > self._min_keys(node.children[index + 1]):
            self._borrow_from_next(node, index)
            if index > 0:
                return node.keys[index - 1]
            return child.keys[0] if child.leaf and child.keys else None

        # Merge with a sibling
        if index < len(node.children) - 1:
            self._merge(node, index)
            merged = node.children[index]
            if index > 0:
                return node.keys[index - 1]
            return merged.keys[0] if merged.leaf and merged.keys else None
        else:
            self._merge(node, index - 1)
            merged = node.children[index - 1]
            if index >= 2:
                return node.keys[index - 2]
            return merged.keys[0] if merged.leaf and merged.keys else None

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
            left.keys.append(node.keys[index])   # push down parent separator
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
            return (self.order - 1) // 2
        return math.ceil(self.order / 2) - 1

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