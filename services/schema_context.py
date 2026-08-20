"""
schema_context.py — Runtime schema introspection for dynamic, data-driven
prompts, fallback SQL, and entity-scope verification.

Replaces hardcoded assumptions about specific project/module names (e.g.
FSA/HSA/WDH) with live introspection of whatever data was actually ingested,
so the same chat/chart logic works correctly for the current QA/Allure
dataset AND for arbitrary ingested datasets.

Cached per ingestion_id (state.current_ingestion_id) — switching to a
different ingestion naturally uses a different cache entry, no explicit
invalidation wiring needed.
"""

import logging
import re
from typing import Dict, List, Optional

from . import data_loader, state

logger = logging.getLogger(__name__)

_CATEGORICAL_COLUMN_HINTS = ("project", "module", "platform", "status", "browser", "priority")
_MAX_DISTINCT_VALUES = 12

# Columns hidden from every prompt that describes the data to the LLM.
#
# These carry runner identity - values like
# "9ed19d4b-...-vt9km-61-playwright-worker-0" - which is a per-run scheduling
# accident, not a property of the test. Advertised in the schema block, the
# model treats them as just another categorical and will happily answer "which
# area is failing" with a chart of forty unreadable worker IDs. The columns
# still exist and still execute if SQL names them; they are simply not
# suggested. The runtime insight band reads them directly
# (main._wall_clock_runtime) to work out how parallel the suite was, which is
# the one question they can actually answer.
#
# Matched on the exact lowercased name, not as substrings - "host" must not
# swallow a legitimate "hosted_page" column.
_RUNNER_IDENTITY_COLUMNS = frozenset({
    "worker",
    "worker_id",
    "worker_index",
    "workerindex",
    "host",
    "hostname",
    "thread",
    "labels_host",
    "labels_thread",
})


def _is_runner_identity_column(col_name: str) -> bool:
    return (col_name or "").strip().lower() in _RUNNER_IDENTITY_COLUMNS

_cache: Dict[str, dict] = {}
# Each ingestion is an immutable snapshot (see module docstring), so a cache
# entry is valid for the process lifetime and invalidate_cache() is only for
# explicit cache-busting - there's no TTL here on purpose (a TTL would just
# re-trigger the DISTINCT queries in _fetch_distinct_values on a timer for no
# correctness benefit). What's uncapped is entry *count*: a long-running
# backend that's been pointed at many different ingestions over its life
# accumulates one entry per ingestion_id forever. Cap that instead.
_MAX_CACHED_INGESTIONS = 50


_NUMERIC_TYPE_HINTS = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC", "HUGEINT")


def _is_categorical_column(col_name: str, col_type: str = "") -> bool:
    name = (col_name or "").lower()
    dtype = (col_type or "").upper()
    if any(h in dtype for h in _NUMERIC_TYPE_HINTS):
        return False
    return any(h in name for h in _CATEGORICAL_COLUMN_HINTS)


def _fetch_distinct_values(table: str, column: str, limit: int = _MAX_DISTINCT_VALUES) -> List[str]:
    if not state.duck_conn:
        return []
    try:
        with state._duck_query_lock:
            rows = state.duck_conn.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {int(limit)}'
            ).fetchall()
        return [str(r[0]) for r in rows if r and r[0] is not None]
    except Exception:
        return []


def build_schema_summary(sample_rows: int = 3, force_refresh: bool = False) -> dict:
    """Live profile of every DuckDB table currently registered: columns, row
    counts, and top distinct values for low-cardinality categorical columns."""
    ingestion_id = state.current_ingestion_id or ""
    if not force_refresh and ingestion_id in _cache:
        return _cache[ingestion_id]

    profile = data_loader.get_data_profile(sample_rows=sample_rows)
    tables = profile.get("tables", {}) if isinstance(profile, dict) else {}

    summary: dict = {"tables": {}}
    for tbl, info in tables.items():
        if not isinstance(info, dict) or "columns" not in info:
            continue
        # Filtered here rather than at each prompt site: this summary is the
        # single source every LLM-facing schema block is rendered from
        # (handlers._build_schema_context, render_prompt_examples), so one
        # exclusion covers both the chat and chart paths.
        columns = [
            col
            for col in info.get("columns", [])
            if not (isinstance(col, dict) and _is_runner_identity_column(col.get("name", "")))
        ]
        distinct_values = {}
        for col in columns:
            if not isinstance(col, dict):
                continue
            name = col.get("name", "")
            col_type = col.get("type", "")
            if _is_categorical_column(name, col_type):
                values = _fetch_distinct_values(tbl, name)
                if values:
                    distinct_values[name] = values
        summary["tables"][tbl] = {
            "row_count": info.get("row_count", 0),
            "columns": columns,
            "distinct_values": distinct_values,
        }

    _cache[ingestion_id] = summary
    if len(_cache) > _MAX_CACHED_INGESTIONS:
        for key in list(_cache.keys())[: len(_cache) - _MAX_CACHED_INGESTIONS]:
            _cache.pop(key, None)
    return summary


def invalidate_cache(ingestion_id: Optional[str] = None) -> None:
    if ingestion_id is None:
        _cache.clear()
    else:
        _cache.pop(ingestion_id, None)


def find_entity_mentions(user_message: str, schema_summary: Optional[dict] = None) -> Dict[str, str]:
    """Scan the prompt for tokens that match a known distinct value of a
    categorical column (case-insensitive, word-boundary matched). Returns
    {column_name: matched_value} — at most one match per column."""
    summary = schema_summary or build_schema_summary()
    p = (user_message or "").lower()
    mentions: Dict[str, str] = {}
    for info in summary.get("tables", {}).values():
        for col, values in info.get("distinct_values", {}).items():
            if col in mentions:
                continue
            for value in values:
                v = str(value).strip()
                if not v:
                    continue
                if re.search(rf"(?<![a-z0-9]){re.escape(v.lower())}(?![a-z0-9])", p):
                    mentions[col] = value
                    break
    return mentions


def all_known_values(schema_summary: Optional[dict] = None, column_hint: Optional[str] = None) -> List[str]:
    """Flatten distinct values across tables for a given column-name hint
    (e.g. 'project'), used to tell the user what values ARE available when
    they reference something that doesn't exist in the ingested data."""
    summary = schema_summary or build_schema_summary()
    hint = (column_hint or "").lower()
    values: List[str] = []
    seen = set()
    for info in summary.get("tables", {}).values():
        for col, vals in info.get("distinct_values", {}).items():
            if hint and hint not in col.lower():
                continue
            for v in vals:
                if v not in seen:
                    seen.add(v)
                    values.append(v)
    return values


def render_prompt_examples(schema_summary: Optional[dict] = None) -> str:
    """Render a short block of REAL values actually present in the ingested
    data (project/module/platform/status names, etc.), for injection into
    LLM prompts in place of hardcoded literal examples (e.g. 'FSA | HSA |
    WDH'). Grounds the LLM in whatever dataset is actually loaded, whether
    that's this QA/Allure dataset or something else entirely."""
    summary = schema_summary or build_schema_summary()
    seen_cols: Dict[str, List[str]] = {}
    for info in summary.get("tables", {}).values():
        for col, vals in info.get("distinct_values", {}).items():
            if col not in seen_cols:
                seen_cols[col] = list(vals)

    if not seen_cols:
        return "(No ingested data profile available yet.)"

    lines = ["=== ACTUAL VALUES IN THIS INGESTED DATASET ==="]
    for col, vals in seen_cols.items():
        shown = ", ".join(str(v) for v in vals[:8])
        more = f", … (+{len(vals) - 8} more)" if len(vals) > 8 else ""
        lines.append(f"{col} values: {shown}{more}")
    return "\n".join(lines)


_GENERIC_VALUE_WORDS = {"test", "tests", "the", "and", "of", "for", "app", "page"}


def find_partial_module_mention(user_message: str, schema_summary: Optional[dict] = None) -> Optional[str]:
    """Module names are usually multi-word ('Eligibility Tests'), so a user
    saying just 'eligibility' won't exact-match via find_entity_mentions.
    Check if a significant keyword from any known module_name appears in
    the prompt and return the full matched value if so."""
    summary = schema_summary or build_schema_summary()
    p = (user_message or "").lower()
    for info in summary.get("tables", {}).values():
        for col, values in info.get("distinct_values", {}).items():
            if "module" not in col.lower():
                continue
            for value in values:
                words = [
                    w for w in re.findall(r"[a-z0-9]+", str(value).lower())
                    if w not in _GENERIC_VALUE_WORDS and len(w) >= 4
                ]
                for w in words:
                    if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", p):
                        return value
    return None


def build_entity_filter_sql(
    user_message: str,
    schema_summary: Optional[dict] = None,
    base_table: str = "module_metrics",
    select_columns: str = "project_name, module_name, platform_type, total_tests, passed, failed, pass_rate",
) -> Optional[str]:
    """Schema-aware replacement for hardcoded per-project/per-module fallback
    SQL entries (e.g. static regexes for '\\bfsa\\b' / 'eligibility'). Finds
    any known entity value mentioned in the prompt and builds a filtered
    query against it dynamically, so the same logic works for whatever
    project/module names actually exist in the ingested data — not just a
    fixed hardcoded set. Returns None if no known entity is mentioned."""
    summary = schema_summary or build_schema_summary()
    mentions = find_entity_mentions(user_message, summary)

    # Prefer project_name, then module_name, then platform_type as the filter column.
    for col in ("project_name", "module_name", "platform_type"):
        if col in mentions:
            value = str(mentions[col]).replace("'", "''")
            return (
                f"SELECT {select_columns} FROM {base_table}"
                f" WHERE {col} = '{value}' ORDER BY module_name, platform_type"
            )

    # Fuzzy fallback: a keyword from a known module name (e.g. "eligibility"
    # matching "Eligibility Tests") — give test-level detail since a user
    # naming a specific module by keyword is usually after failure detail.
    partial = find_partial_module_mention(user_message, summary)
    if partial:
        first_word = re.findall(r"[A-Za-z0-9]+", str(partial))
        like_fragment = (first_word[0] if first_word else str(partial)).replace("'", "''")
        return (
            "SELECT test_name, project_name, module_name, platform_type, status, error"
            f" FROM flattened_tests WHERE module_name ILIKE '%{like_fragment}%'"
            " ORDER BY status, platform_type, test_name"
        )

    return None
