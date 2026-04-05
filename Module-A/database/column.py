from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


SUPPORTED_TYPES = ["INT", "FLOAT", "CHAR", "VARCHAR", "TEXT", "BOOLEAN"]

PYTHON_TYPE_MAP = {
    "INT":     int,
    "FLOAT":   float,
    "CHAR":    str,
    "VARCHAR": str,
    "TEXT":    str, #check diff with varchar (remcheck)
    "BOOLEAN": bool,
}


def parse_type(type_str: str) -> tuple[str, int | None]:
    """
    Parse a SQL type string into (base_type, limit).

    Examples:
        "INT"         -> ("INT", None)
        "VARCHAR(50)" -> ("VARCHAR", 50)
        "CHAR(3)"     -> ("CHAR", 3)
        "TEXT"        -> ("TEXT", None)
    """
    type_str = type_str.strip().upper()

    if "(" in type_str:
        paren_idx = type_str.index("(")
        base = type_str[:paren_idx].strip()
        limit_str = type_str[paren_idx + 1:].replace(")", "").strip()

        if not limit_str.isdigit():
            raise ValueError(
                f"Invalid type length in '{type_str}'. Expected an integer, got '{limit_str}'."
            )
        limit = int(limit_str)
        if limit <= 0:
            raise ValueError(
                f"Type length must be positive, got {limit} in '{type_str}'."
            )
    else:
        base = type_str
        limit = None

    if base not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported type '{base}'. "
            f"Supported types are: {', '.join(SUPPORTED_TYPES)}."
        )

    if base in ("CHAR", "VARCHAR") and limit is None:
        raise ValueError(
            f"Type '{base}' requires a length, e.g. {base}(50)."
        )

    if base not in ("CHAR", "VARCHAR") and limit is not None:
        raise ValueError(
            f"Type '{base}' does not accept a length parameter."
        )

    return base, limit


@dataclass
class Column:
    """
    Represents a single column in a table schema.

    Attributes:
        name     : column name, e.g. "age"
        type_str : SQL type string, e.g. "INT", "VARCHAR(50)"
        nullable : whether None is a valid value (default True)
        default  : value used when the column is omitted in an insert (default None)

    Internal (set in __post_init__, not passed by the user):
        _base_type : normalised type name, e.g. "VARCHAR"
        _limit     : length constraint for CHAR / VARCHAR, else None
    """

    name:     str
    type_str: str
    nullable: bool = True
    default:  Any  = None

    _base_type: str      = field(init=False, repr=False)
    _limit:     int|None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Normalise the stored type string
        self.type_str = self.type_str.strip().upper()

        # Parse and cache base type + limit
        self._base_type, self._limit = parse_type(self.type_str)

        # Validate the default value itself at definition time
        if self.default is not None:
            try:
                self.validate(self.default)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid default value for column '{self.name}': {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, value: Any) -> None:
        """
        Validate a single value against this column's type, nullability,
        and length constraints.  Raises ValueError on any violation.
        """

        # Step 1 — handle None
        if value is None:
            if not self.nullable:
                raise ValueError(
                    f"Column '{self.name}' cannot be null."
                )
            return  # None is acceptable, no further checks needed

        # Step 2 — type check
        self._check_type(value)

        # Step 3 — length check (CHAR and VARCHAR only)
        if self._base_type == "VARCHAR":
            if len(value) > self._limit:
                raise ValueError(
                    f"Column '{self.name}': value {value!r} exceeds VARCHAR({self._limit}) "
                    f"(length {len(value)})."
                )

        elif self._base_type == "CHAR":
            if len(value) != self._limit:
                raise ValueError(
                    f"Column '{self.name}': value {value!r} must be exactly "
                    f"CHAR({self._limit}) characters (got {len(value)})."
                )

    def _check_type(self, value: Any) -> None:
        """Raise ValueError if value is the wrong Python type for this column."""

        base = self._base_type

        if base == "INT":
            # bool is a subclass of int in Python — reject it explicitly
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"Column '{self.name}' expects INT, "
                    f"got {type(value).__name__} ({value!r})."
                )

        elif base == "FLOAT":
            # allow int values to be stored in FLOAT columns (implicit cast)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"Column '{self.name}' expects FLOAT, "
                    f"got {type(value).__name__} ({value!r})."
                )

        elif base == "BOOLEAN":
            if not isinstance(value, bool):
                raise ValueError(
                    f"Column '{self.name}' expects BOOLEAN, "
                    f"got {type(value).__name__} ({value!r})."
                )

        elif base in ("VARCHAR", "CHAR", "TEXT"):
            if not isinstance(value, str):
                raise ValueError(
                    f"Column '{self.name}' expects {base}, "
                    f"got {type(value).__name__} ({value!r})."
                )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serialisable dict for persistence."""
        return {
            "name":     self.name,
            "type_str": self.type_str,
            "nullable": self.nullable,
            "default":  self.default,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Column":
        """Reconstruct a Column from a dict loaded from JSON."""
        return cls(
            name     = data["name"],
            type_str = data["type_str"],
            nullable = data.get("nullable", True),
            default  = data.get("default", None),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        nullable_str = "NOT NULL" if not self.nullable else "NULL"
        default_str  = f" DEFAULT {self.default!r}" if self.default is not None else ""
        return f"Column({self.name} {self.type_str} {nullable_str}{default_str})"