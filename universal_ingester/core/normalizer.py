"""Generic, schema-free normalization of arbitrary parsed payloads (JSON,
API responses, DB rows) into relational tables.

Design rules — all deterministic, no AI involved:

- A list of objects becomes a records table.
- A dict is scanned for *every* array-of-objects (not just the first one);
  each becomes its own table. Remaining scalar fields become a one-row
  context table that children link back to.
- Inside a record, nested dicts are flattened with dot paths (later
  sanitized to underscores for LanceDB).
- Arrays of objects inside a record become a child table carrying
  `_parent_id` / `_parent_table` so hierarchy is preserved instead of
  being truncated to the first element.
- Arrays of scalars are kept as JSON strings (queryable, lossless).
- Mixed/missing/changing field types are tolerated: pandas unions columns
  across records and the storage layer handles type coercion.

The result preserves the full structure of the input as linked tables,
which is what "preserve structure instead of flattening everything" means
in a columnar store.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

MAX_DEPTH = 6
MAX_CHILD_TABLES = 40
# Below this many elements a nested object array is inlined as JSON rather
# than exploded into a table — tiny arrays (e.g. Allure "parameters" with 2
# entries) aren't worth a join.
MIN_ROWS_FOR_CHILD_TABLE = 1


def _new_record_id() -> str:
    return uuid.uuid4().hex[:16]


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", str(name)).strip("_").lower()
    return cleaned or "field"


def _is_record_array(value: Any) -> bool:
    """An array where dict elements dominate (tolerates a few stray scalars)."""
    if not isinstance(value, list) or not value:
        return False
    dict_count = sum(1 for v in value[:50] if isinstance(v, dict))
    return dict_count >= max(1, int(min(len(value), 50) * 0.6))


@dataclass
class NormalizedPayload:
    tables: Dict[str, pd.DataFrame] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)


class StructureNormalizer:
    def __init__(self, max_depth: int = MAX_DEPTH, max_child_tables: int = MAX_CHILD_TABLES):
        self.max_depth = max_depth
        self.max_child_tables = max_child_tables

    def normalize(self, payload: Any, root_name: str) -> NormalizedPayload:
        root_name = _safe_name(root_name)
        self._tables: Dict[str, List[Dict[str, Any]]] = {}
        self._truncated = False

        if _is_record_array(payload):
            self._add_records(root_name, payload, parent_table=None, parent_id=None, depth=0)
        elif isinstance(payload, list):
            # Array of scalars / mixed non-dict values.
            rows = [{"value": v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False, default=str)} for v in payload]
            self._tables.setdefault(root_name, []).extend(rows)
        elif isinstance(payload, dict):
            self._add_root_dict(root_name, payload)
        else:
            self._tables.setdefault(root_name, []).append({"value": payload})

        result = NormalizedPayload()
        for name, rows in self._tables.items():
            if not rows:
                continue
            df = pd.DataFrame(rows)
            result.tables[name] = df
        result.stats = {
            "table_count": len(result.tables),
            "total_rows": int(sum(len(df) for df in result.tables.values())),
            "truncated": self._truncated,
        }
        return result

    def _add_root_dict(self, root_name: str, payload: Dict[str, Any]) -> None:
        """Split a root object into: one context row (scalars) + one table
        per top-level record array. All record arrays are captured — the old
        pipeline silently kept only the first list it found."""
        root_id = _new_record_id()
        scalars: Dict[str, Any] = {"_record_id": root_id}
        found_array = False

        for key, value in payload.items():
            if _is_record_array(value):
                found_array = True
                self._add_records(
                    f"{root_name}_{_safe_name(key)}",
                    value,
                    parent_table=root_name,
                    parent_id=root_id,
                    depth=1,
                )
            else:
                self._flatten_into(scalars, key, value, depth=1, parent_ctx=(root_name, root_id))

        # A context row is only meaningful when there are scalar fields or no
        # arrays were found at all (single-object payload).
        if len(scalars) > 1 or not found_array:
            self._tables.setdefault(root_name, []).append(scalars)

    def _add_records(
        self,
        table_name: str,
        records: List[Any],
        parent_table: Optional[str],
        parent_id: Optional[str],
        depth: int,
    ) -> None:
        rows = self._tables.setdefault(table_name, [])
        for item in records:
            if isinstance(item, dict):
                row: Dict[str, Any] = {"_record_id": _new_record_id()}
                if parent_table:
                    row["_parent_table"] = parent_table
                    row["_parent_id"] = parent_id
                for key, value in item.items():
                    self._flatten_into(row, key, value, depth + 1, parent_ctx=(table_name, row["_record_id"]))
                rows.append(row)
            elif item is not None:
                row = {"value": item if not isinstance(item, list) else json.dumps(item, ensure_ascii=False, default=str)}
                if parent_table:
                    row["_parent_table"] = parent_table
                    row["_parent_id"] = parent_id
                rows.append(row)

    def _flatten_into(
        self,
        row: Dict[str, Any],
        key: str,
        value: Any,
        depth: int,
        parent_ctx: tuple[str, str],
    ) -> None:
        """Flatten one field of a record into the row, spawning child tables
        for nested record arrays."""
        col = _safe_name(key)
        parent_table, parent_id = parent_ctx

        if isinstance(value, dict):
            if depth >= self.max_depth:
                row[col] = json.dumps(value, ensure_ascii=False, default=str)
                self._truncated = True
                return
            for sub_key, sub_val in value.items():
                self._flatten_into(row, f"{col}.{sub_key}", sub_val, depth + 1, parent_ctx)
        elif _is_record_array(value):
            if (
                depth >= self.max_depth
                or len(self._tables) >= self.max_child_tables
                or len(value) < MIN_ROWS_FOR_CHILD_TABLE
            ):
                row[col] = json.dumps(value, ensure_ascii=False, default=str)
                self._truncated = depth >= self.max_depth or len(self._tables) >= self.max_child_tables
                return
            child_table = f"{parent_table}_{col.replace('.', '_')}"
            self._add_records(child_table, value, parent_table=parent_table, parent_id=parent_id, depth=depth)
            row[f"{col}_count"] = len(value)
        elif isinstance(value, list):
            row[col] = json.dumps(value, ensure_ascii=False, default=str) if value else None
        else:
            row[col] = value


def normalize_payload(payload: Any, root_name: str) -> NormalizedPayload:
    return StructureNormalizer().normalize(payload, root_name)
