from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from table import Table

@dataclass
class ForeignKey:
    col: str
    references: Table
    ref_col: str
    on_delete: str = "RESTRICT"  # "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"
    on_update: str = "RESTRICT"

    def check_insert(self, row: dict[str, Any]) -> None:
        """Verify the referenced primary key exists when inserting/updating child."""
        val = row.get(self.col)
        if val is None:
            return  # NULLs allowed if column allows it

        # Use the BPlusTree index directly for checking existence.
        # This properly sees dirty inserts from the same transaction 
        # (Table.find() locks and searches from heap, bypassing uncommitted txn state).
        slot = self.references._index.search(val)
        if slot is None:
            raise ValueError(f"Foreign key violation: {self.col}={val!r} not found in {self.references.name}.{self.ref_col}")

    def on_parent_delete(self, child_table: Table, pk: Any, txn_id: int | None = None) -> None:
        """Enforce cascade rule when parent row is deleted."""
        # Find all child rows referencing this parent pk
        child_pks = child_table._secondary_indexes[self.col].get_eq(pk)
        if not child_pks:
            return

        if self.on_delete == "RESTRICT":
            raise ValueError(f"Cannot delete {self.references.name} pk={pk!r}: referenced by {child_table.name}.{self.col}")
        
        elif self.on_delete == "CASCADE":
            for child_pk in child_pks:
                if txn_id is not None:
                    child_table._delete_txn(child_pk, txn_id)
                else:
                    child_table.delete(child_pk)
                
        elif self.on_delete == "SET NULL":
            for child_pk in child_pks:
                if txn_id is not None:
                    child_table._update_txn(child_pk, {self.col: None}, txn_id)
                else:
                    child_table.update(child_pk, {self.col: None})
                
        elif self.on_delete == "SET DEFAULT":
            default_val = child_table.schema[self.col].default
            for child_pk in child_pks:
                if txn_id is not None:
                    child_table._update_txn(child_pk, {self.col: default_val}, txn_id)
                else:
                    child_table.update(child_pk, {self.col: default_val})
        else:
            raise ValueError(f"Unknown on_delete action: {self.on_delete}")

    def on_parent_update(self, child_table: Table, old_pk: Any, new_pk: Any, txn_id: int | None = None) -> None:
        """Enforce cascade rule when parent pk is updated."""
        if old_pk == new_pk:
            return

        child_pks = child_table._secondary_indexes[self.col].get_eq(old_pk)
        if not child_pks:
            return

        if self.on_update == "RESTRICT":
            raise ValueError(f"Cannot update {self.references.name} pk={old_pk!r}: referenced by {child_table.name}.{self.col}")
            
        elif self.on_update == "CASCADE":
            for child_pk in child_pks:
                if txn_id is not None:
                    child_table._update_txn(child_pk, {self.col: new_pk}, txn_id)
                else:
                    child_table.update(child_pk, {self.col: new_pk})
                
        elif self.on_update == "SET NULL":
            for child_pk in child_pks:
                if txn_id is not None:
                    child_table._update_txn(child_pk, {self.col: None}, txn_id)
                else:
                    child_table.update(child_pk, {self.col: None})
                
        elif self.on_update == "SET DEFAULT":
            default_val = child_table.schema[self.col].default
            for child_pk in child_pks:
                if txn_id is not None:
                    child_table._update_txn(child_pk, {self.col: default_val}, txn_id)
                else:
                    child_table.update(child_pk, {self.col: default_val})
        else:
            raise ValueError(f"Unknown on_update action: {self.on_update}")
