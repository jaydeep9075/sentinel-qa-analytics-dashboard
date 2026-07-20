"""LanceDB storage manager for the universal ingestion pipeline.

Centralizes everything that used to be scattered across ingester methods:

- standard metadata columns on every structured table
  (`build_id`, `_source_id`, `_ingested_at`, `_content_hash`,
  `_schema_version`, `_extra_json`) — flat and filterable, not buried in a
  JSON blob
- content hashing + deduplication (within a build; re-ingesting the same
  data into the same build is a no-op instead of doubling rows)
- schema evolution: appending a DataFrame whose columns differ from the
  existing table no longer crashes — new columns are preserved in
  `_extra_json`, missing columns are null-filled, conflicting types are
  coerced to the table's type
- batched writes so huge DataFrames don't hit LanceDB in one giant call
"""

import json
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2  # v1 = pre-refactor tables without standard metadata columns
BATCH_ROWS = int(os.getenv("INGEST_BATCH_ROWS", "2000"))
DEDUP_ENABLED = os.getenv("INGEST_DEDUP", "true").strip().lower() in {"1", "true", "yes", "on"}

# Volatile per-run columns that must not participate in content hashing,
# otherwise identical data re-ingested would never deduplicate.
_HASH_EXCLUDED = {"id", "_record_id", "_content_hash", "_ingested_at", "build_id", "_schema_version"}


def sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """LanceDB rejects dots and several special chars in field names."""
    if df is None or df.empty:
        return df
    rename_map = {}
    seen = set()
    for col in df.columns:
        new_col = str(col)
        for ch in (".", "-", " ", "(", ")", "[", "]", "{", "}", "/", "\\", ":"):
            new_col = new_col.replace(ch, "_")
        while "__" in new_col:
            new_col = new_col.replace("__", "_")
        new_col = new_col.strip("_") or "field"
        # Guarantee uniqueness after sanitization collapses names.
        base = new_col
        i = 2
        while new_col in seen:
            new_col = f"{base}_{i}"
            i += 1
        seen.add(new_col)
        if new_col != col:
            rename_map[col] = new_col
    return df.rename(columns=rename_map) if rename_map else df


def compute_row_hashes(df: pd.DataFrame) -> pd.Series:
    """Stable sha256 per row over canonical JSON of non-volatile columns."""
    cols = [c for c in df.columns if c not in _HASH_EXCLUDED]
    if not cols:
        return pd.Series([""] * len(df), index=df.index)
    records = df[cols].to_dict(orient="records")
    hashes = []
    for rec in records:
        canonical = json.dumps(rec, sort_keys=True, ensure_ascii=False, default=str)
        hashes.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32])
    return pd.Series(hashes, index=df.index)


def compute_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


class LanceStorage:
    def __init__(self, lance_db, report=None):
        self.db = lance_db
        self.report = report
        # In-run hash registry: (table_name, build_id) -> set of hashes.
        self._seen_hashes: Dict[tuple, set] = {}

    # ------------------------------------------------------------------
    # structured tables
    # ------------------------------------------------------------------
    def write_structured(
        self,
        table_name: str,
        df: pd.DataFrame,
        build_id: str,
        source_id: str,
        dataset_name: str = "",
    ) -> int:
        """Write a structured DataFrame with metadata, dedup and schema
        alignment. Returns the number of rows actually stored."""
        if df is None or df.empty:
            return 0
        dataset_name = dataset_name or table_name

        df = sanitize_columns(df.copy())
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

        # Standard metadata columns.
        if "build_id" not in df.columns:
            df["build_id"] = build_id
        df["_source_id"] = source_id
        df["_ingested_at"] = datetime.now(timezone.utc)
        df["_schema_version"] = SCHEMA_VERSION
        if "_extra_json" not in df.columns:
            df["_extra_json"] = None
        # An all-None column would be inferred as arrow Null type at table
        # creation, permanently rejecting future string values — pin it.
        df["_extra_json"] = df["_extra_json"].astype("string")
        df["_content_hash"] = compute_row_hashes(df)

        if DEDUP_ENABLED:
            df, dropped = self._dedup(table_name, build_id, df)
            if dropped and self.report is not None:
                self.report.record_duplicates(dataset_name, dropped)
        if df.empty:
            return 0

        stored = 0
        if table_name in self.db.table_names():
            table = self.db.open_table(table_name)
            if table.count_rows() == 0:
                # Empty placeholder table: recreate so the schema matches the
                # incoming data instead of a stale empty schema.
                self.db.drop_table(table_name)
                stored = self._create_batched(table_name, df)
            else:
                df = self._align_to_table_schema(table, table_name, df, dataset_name)
                if df.empty:
                    return 0
                stored = self._add_batched(table, df)
        else:
            stored = self._create_batched(table_name, df)

        logger.info("Stored %d rows into %s (build %s)", stored, table_name, build_id)
        return stored

    def _dedup(self, table_name: str, build_id: str, df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        key = (table_name, build_id)
        seen = self._seen_hashes.setdefault(key, self._load_existing_hashes(table_name, build_id))
        before = len(df)
        mask = ~df["_content_hash"].isin(seen)
        df = df[mask]
        # Also drop duplicates inside the incoming frame itself.
        df = df.drop_duplicates(subset=["_content_hash"], keep="first")
        seen.update(df["_content_hash"].tolist())
        return df, before - len(df)

    def _load_existing_hashes(self, table_name: str, build_id: str) -> set:
        """Best-effort load of hashes already stored for this build so
        re-running the same ingestion doesn't duplicate rows. Falls back to
        empty (in-run dedup only) on any error or legacy table."""
        if table_name not in self.db.table_names():
            return set()
        try:
            dataset = self.db.open_table(table_name).to_lance()
            tbl = dataset.to_table(columns=["_content_hash"], filter=f"build_id = '{build_id}'")
            return set(tbl.column("_content_hash").to_pylist())
        except Exception:
            return set()

    def _align_to_table_schema(self, table, table_name: str, df: pd.DataFrame, dataset_name: str) -> pd.DataFrame:
        """Make df conform to the existing table schema without dropping data."""
        try:
            schema: pa.Schema = table.schema
        except Exception:
            return df

        table_cols = list(schema.names)
        extra_cols = [c for c in df.columns if c not in table_cols]
        missing_cols = [c for c in table_cols if c not in df.columns]

        if extra_cols:
            if "_extra_json" in table_cols:
                # Preserve new fields instead of failing the append: pack them
                # into the _extra_json overflow column.
                extras = df[extra_cols].to_dict(orient="records")
                packed = []
                for base, rec in zip(df.get("_extra_json", [None] * len(df)), extras):
                    merged = {k: v for k, v in rec.items() if v is not None}
                    if isinstance(base, str) and base:
                        try:
                            merged = {**json.loads(base), **merged}
                        except Exception:
                            pass
                    packed.append(json.dumps(merged, ensure_ascii=False, default=str) if merged else None)
                df = df.drop(columns=extra_cols)
                df["_extra_json"] = packed
                note = f"{table_name}: new columns {extra_cols} stored in _extra_json"
            else:
                df = df.drop(columns=extra_cols)
                note = f"{table_name}: legacy table, dropped new columns {extra_cols}"
            if self.report is not None:
                self.report.record_schema_change(dataset_name, note)
            logger.info("Schema evolution: %s", note)

        for col in missing_cols:
            df[col] = None

        df = df[table_cols]
        return self._coerce_types(schema, df)

    def _coerce_types(self, schema: pa.Schema, df: pd.DataFrame) -> pd.DataFrame:
        for fld in schema:
            col = fld.name
            if col not in df.columns:
                continue
            try:
                if pa.types.is_integer(fld.type) or pa.types.is_floating(fld.type):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif pa.types.is_timestamp(fld.type):
                    df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
                elif pa.types.is_boolean(fld.type):
                    df[col] = df[col].map(
                        lambda v: None if v is None else bool(v) if not isinstance(v, str)
                        else v.strip().lower() in {"1", "true", "yes", "on"}
                    )
                elif pa.types.is_string(fld.type) or pa.types.is_large_string(fld.type):
                    df[col] = df[col].map(
                        lambda v: None if v is None
                        else v if isinstance(v, str)
                        else json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list))
                        else str(v)
                    )
            except Exception as exc:
                logger.warning("Type coercion failed for column %s: %s", col, exc)
        return df

    def _create_batched(self, table_name: str, df: pd.DataFrame) -> int:
        first = df.iloc[:BATCH_ROWS]
        self.db.create_table(table_name, first)
        stored = len(first)
        if len(df) > BATCH_ROWS:
            table = self.db.open_table(table_name)
            stored += self._add_batched(table, df.iloc[BATCH_ROWS:])
        return stored

    def _add_batched(self, table, df: pd.DataFrame) -> int:
        stored = 0
        for start in range(0, len(df), BATCH_ROWS):
            batch = df.iloc[start : start + BATCH_ROWS]
            table.add(batch)
            stored += len(batch)
        return stored

    # ------------------------------------------------------------------
    # documents (embedded chunks)
    # ------------------------------------------------------------------
    def write_documents(self, docs: List[Dict[str, Any]], build_id: str = "") -> int:
        if not docs:
            return 0
        if DEDUP_ENABLED:
            key = ("documents", build_id)
            seen = self._seen_hashes.setdefault(key, set())
            unique = []
            for doc in docs:
                h = doc.get("content_hash") or compute_text_hash(doc.get("text", ""))
                doc["content_hash"] = h
                if h in seen:
                    continue
                seen.add(h)
                unique.append(doc)
            docs = unique
            if not docs:
                return 0

        table_name = "documents"
        stored = 0
        if table_name in self.db.table_names():
            table = self.db.open_table(table_name)
            if table.count_rows() == 0:
                self.db.drop_table(table_name)
                self.db.create_table(table_name, docs)
                stored = len(docs)
            else:
                for start in range(0, len(docs), BATCH_ROWS):
                    batch = docs[start : start + BATCH_ROWS]
                    table.add(batch)
                    stored += len(batch)
        else:
            self.db.create_table(table_name, docs)
            stored = len(docs)
        logger.info("Added %d documents", stored)
        return stored

    # ------------------------------------------------------------------
    # small bookkeeping tables (sources, schema profiles)
    # ------------------------------------------------------------------
    def append_records(self, table_name: str, records: List[Dict[str, Any]]) -> None:
        if not records:
            return
        if table_name in self.db.table_names():
            table = self.db.open_table(table_name)
            if table.count_rows() == 0:
                self.db.drop_table(table_name)
                self.db.create_table(table_name, records)
            else:
                table.add(records)
        else:
            self.db.create_table(table_name, records)
