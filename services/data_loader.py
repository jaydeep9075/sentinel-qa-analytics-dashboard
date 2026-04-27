"""
data_loader.py

Loads LanceDB ingestion into DuckDB and registers these queryable tables:

  flattened_tests     – one row per logical test (after retry-merge)
    Columns: result_id, test_name, build_id, executed_at,
             status (passed|failed|skipped|pending|unknown),
             duration FLOAT (seconds),
             error VARCHAR,
             spec_file VARCHAR,
             project_name VARCHAR  (FSA | HSA | WDH | unknown),
             module_name  VARCHAR  (e.g. "Eligibility Tests"),
             platform_type VARCHAR (desktop | mobile),
             browser VARCHAR       (e.g. "GoogleChrome", "GoogleChromeiPhoneX")

  module_metrics      – (project_name, module_name, platform_type) aggregates
  project_metrics     – (project_name, platform_type) aggregates
  test_cases          – (module_name, priority, title=test_name, project_name, platform_type)
                        backward-compat join table

IMPORTANT: platform_type comes from the Allure "Project" parameter value,
NOT from text-matching on test names.
  "GoogleChrome"        → desktop
  "GoogleChromeiPhoneX" → mobile
  "GoogleChromeiPad"    → mobile
"""

import json
import logging
import re

import duckdb
import lancedb
import numpy as np
import pandas as pd

from . import config, state
from universal_ingester.utils import EmbeddingGenerator

logger = logging.getLogger(__name__)

_DISALLOWED_SQL = [
    r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
    r"\bALTER\b", r"\bTRUNCATE\b", r"\bATTACH\b", r"\bDETACH\b", r"\bCOPY\b",
]

# Allure "Project" param values that mean mobile
_MOBILE_BROWSER_KEYWORDS = ("iphone", "ipad", "android", "mobile", "pixel", "samsung", "galaxy", "appium")


# ── status normaliser ─────────────────────────────────────────────────────────

def normalize_status(raw: str) -> str:
    v = str(raw or "").strip().lower()
    return {
        "pass": "passed", "passed": "passed", "success": "passed", "ok": "passed",
        "fail": "failed", "failed": "failed", "error": "failed", "broken": "failed",
        "skip": "skipped", "skipped": "skipped",
        "pending": "pending",
    }.get(v, v or "unknown")


def _browser_to_platform(browser: str) -> str:
    b = (browser or "").lower()
    return "mobile" if any(k in b for k in _MOBILE_BROWSER_KEYWORDS) else "desktop"


# ── SQL helpers ───────────────────────────────────────────────────────────────

def sanitize_sql(q: str) -> str:
    q = re.sub(r"```sql\s*|```", "", (q or ""), flags=re.IGNORECASE).strip()
    q = re.sub(r"^\s*duckdb\s*:?", "", q, flags=re.IGNORECASE).strip()
    return q.rstrip(";").strip()


def validate_sql(q: str):
    clean = sanitize_sql(q)
    if not clean:
        return False, "Empty SQL query"
    if not re.search(r"\bSELECT\b", clean, re.IGNORECASE):
        return False, "Only SELECT queries are allowed"
    for pat in _DISALLOWED_SQL:
        if re.search(pat, clean, re.IGNORECASE):
            return False, "Unsafe SQL pattern detected"
    return True, clean


# ── init_data ─────────────────────────────────────────────────────────────────

def init_data(ingestion_id: str) -> bool:
    ingestion_path = config.DATA_BASE_PATH / ingestion_id / "lancedb"
    if not ingestion_path.exists():
        logger.error(f"Ingestion path not found: {ingestion_path}")
        return False

    state.lance_db = lancedb.connect(str(ingestion_path))
    state.duck_conn = duckdb.connect()
    state.embedder = EmbeddingGenerator()
    state.current_ingestion_id = ingestion_id

    available = state.lance_db.table_names()
    logger.info(f"LanceDB tables for '{ingestion_id}': {available}")

    if "structured_test_results" not in available:
        logger.warning("No structured_test_results table found")
        return False

    try:
        df_raw = state.lance_db.open_table("structured_test_results").to_pandas()
        logger.info(f"structured_test_results: {len(df_raw)} rows | cols: {list(df_raw.columns)}")

        # ── flatten to per-test rows ──────────────────────────────────────────
        if "tests" in df_raw.columns:
            rows = _flatten_legacy(df_raw)
        else:
            rows = _flatten_normalized(df_raw)

        if not rows:
            logger.warning("No test records after flattening")
            return False

        flat = pd.DataFrame(rows)

        # Ensure platform_type is correct for every row
        # If browser column exists, re-derive platform_type from it (most accurate)
        if "browser" in flat.columns:
            flat["platform_type"] = flat["browser"].apply(_browser_to_platform)
        elif "platform_type" not in flat.columns:
            flat["platform_type"] = "desktop"

        state.duck_conn.register("flattened_tests", flat)
        logger.info(f"Registered flattened_tests: {len(flat)} rows")

        # ── module_metrics ────────────────────────────────────────────────────
        if "structured_test_module_metrics" in available:
            df_mod = state.lance_db.open_table("structured_test_module_metrics").to_pandas()
            df_mod = _ensure_module_cols(df_mod)
            # Re-derive platform_type if possible
            state.duck_conn.register("module_metrics", df_mod)
            logger.info(f"Registered module_metrics from LanceDB: {len(df_mod)} rows")
        else:
            df_mod = _compute_module_metrics(flat)
            state.duck_conn.register("module_metrics", df_mod)
            logger.info(f"Computed+registered module_metrics: {len(df_mod)} rows")

        # ── project_metrics ───────────────────────────────────────────────────
        if "structured_test_project_metrics" in available:
            df_proj = state.lance_db.open_table("structured_test_project_metrics").to_pandas()
            df_proj = _ensure_project_cols(df_proj)
            state.duck_conn.register("project_metrics", df_proj)
            logger.info(f"Registered project_metrics from LanceDB: {len(df_proj)} rows")
        else:
            df_proj = _compute_project_metrics(df_mod)
            state.duck_conn.register("project_metrics", df_proj)
            logger.info(f"Computed+registered project_metrics: {len(df_proj)} rows")

        # ── test_cases (backward-compat) ──────────────────────────────────────
        tc = _build_test_cases(flat)
        state.duck_conn.register("test_cases", tc)
        logger.info(f"Registered test_cases: {len(tc)} rows")

        _log_summary(state.duck_conn)
        return True

    except Exception as exc:
        logger.error(f"init_data failed: {exc}", exc_info=True)
        return False


# ── flatten helpers ───────────────────────────────────────────────────────────

def _flatten_legacy(df: pd.DataFrame) -> list:
    """Old format: JSON blob in 'tests' column."""
    rows = []
    for _, row in df.iterrows():
        tests = row["tests"]
        if isinstance(tests, np.ndarray):
            tests = tests.tolist()
        elif isinstance(tests, str):
            try:
                tests = json.loads(tests)
            except Exception:
                continue
        if not isinstance(tests, list):
            continue
        for t in tests:
            dur_raw = t.get("duration", "0")
            if isinstance(dur_raw, str):
                dur = float(dur_raw[:-2]) / 1000 if dur_raw.endswith("ms") else float(dur_raw or 0)
            else:
                dur = float(dur_raw or 0)
            err = t.get("error", "")
            if isinstance(err, dict):
                err = err.get("message", "")
            browser = t.get("browser", "")
            rows.append({
                "result_id":     row.get("id"),
                "test_name":     t.get("full_title", t.get("name", "")),
                "build_id":      row.get("build_id"),
                "executed_at":   row.get("executed_at"),
                "status":        normalize_status(
                    t.get("status") or t.get("state") or t.get("outcome") or t.get("result")
                ),
                "duration":      dur,
                "error":         str(err) if err else "",
                "spec_file":     t.get("spec_file", ""),
                "project_name":  t.get("project_name", "unknown"),
                "module_name":   t.get("module_name", "unknown"),
                "platform_type": _browser_to_platform(browser) if browser else t.get("platform_type", "desktop"),
                "browser":       browser or "GoogleChrome",
            })
    return rows


def _flatten_normalized(df: pd.DataFrame) -> list:
    """New format: one column per field, one row per test."""
    rows = []
    name_col   = next((c for c in ("test_name", "full_name", "name") if c in df.columns), None)
    status_col = "status" if "status" in df.columns else None
    err_col    = next((c for c in ("error_message", "error") if c in df.columns), None)
    spec_col   = "spec_file" if "spec_file" in df.columns else None

    if not (name_col and status_col):
        logger.error("Missing test_name or status column in normalized format")
        return rows

    for _, row in df.iterrows():
        # duration
        if "duration_seconds" in df.columns and pd.notna(row.get("duration_seconds")):
            dur = float(row["duration_seconds"])
        elif "duration" in df.columns:
            d = row.get("duration", "0")
            if isinstance(d, str):
                dur = float(d[:-2]) / 1000 if d.endswith("ms") else float(d or 0)
            else:
                dur = float(d or 0)
        else:
            dur = 0.0

        err = row[err_col] if err_col and pd.notna(row.get(err_col)) else ""
        if isinstance(err, dict):
            err = err.get("message", "")

        browser       = str(row.get("browser", "") or "GoogleChrome")
        platform_type = _browser_to_platform(browser) if browser else str(row.get("platform_type", "desktop") or "desktop")

        rows.append({
            "result_id":     row.get("id"),
            "test_name":     row[name_col],
            "build_id":      row.get("build_id"),
            "executed_at":   row.get("executed_at"),
            "status":        normalize_status(row[status_col]),
            "duration":      dur,
            "error":         str(err) if err else "",
            "spec_file":     row[spec_col] if spec_col else "",
            "project_name":  str(row.get("project_name", "unknown") or "unknown"),
            "module_name":   str(row.get("module_name",  "unknown") or "unknown"),
            "platform_type": platform_type,
            "browser":       browser,
        })
    return rows


# ── aggregation helpers ───────────────────────────────────────────────────────

def _compute_module_metrics(flat: pd.DataFrame) -> pd.DataFrame:
    if flat.empty:
        return pd.DataFrame(columns=[
            "project_name", "module_name", "platform_type",
            "total_tests", "passed", "failed", "skipped", "pending", "unknown",
            "pass_rate", "total_duration_seconds", "avg_duration_seconds",
        ])
    for col in ("project_name", "module_name", "platform_type"):
        if col not in flat.columns:
            flat[col] = "unknown"

    records = []
    for (proj, mod, plat), grp in flat.groupby(
        ["project_name", "module_name", "platform_type"], dropna=False
    ):
        s         = grp["status"].astype(str).str.lower()
        passed    = int(s.eq("passed").sum())
        failed    = int(s.isin(["failed", "broken", "error"]).sum())
        skipped   = int(s.eq("skipped").sum())
        pending   = int(s.eq("pending").sum())
        unknown   = int(s.isin(["unknown", ""]).sum())
        total     = int(len(grp))
        executed  = passed + failed
        dur       = grp["duration"].fillna(0).astype(float)
        records.append({
            "project_name":           str(proj),
            "module_name":            str(mod),
            "platform_type":          str(plat),
            "total_tests":            total,
            "passed":                 passed,
            "failed":                 failed,
            "skipped":                skipped,
            "pending":                pending,
            "unknown":                unknown,
            "pass_rate":              round(passed / executed * 100, 2) if executed else 0.0,
            "total_duration_seconds": round(float(dur.sum()), 2),
            "avg_duration_seconds":   round(float(dur.mean()), 2) if total else 0.0,
        })
    return pd.DataFrame(records)


def _compute_project_metrics(df_mod: pd.DataFrame) -> pd.DataFrame:
    if df_mod.empty:
        return pd.DataFrame(columns=[
            "project_name", "platform_type", "module_count",
            "total_tests", "passed", "failed", "skipped", "pending", "unknown",
            "pass_rate", "total_duration_seconds", "avg_duration_seconds",
        ])
    records = []
    for (proj, plat), grp in df_mod.groupby(["project_name", "platform_type"], dropna=False):
        passed   = int(grp["passed"].sum())
        failed   = int(grp["failed"].sum())
        skipped  = int(grp["skipped"].sum())
        pending  = int(grp["pending"].sum())
        unknown  = int(grp["unknown"].sum())
        total    = int(grp["total_tests"].sum())
        executed = passed + failed
        records.append({
            "project_name":           str(proj),
            "platform_type":          str(plat),
            "module_count":           int(grp["module_name"].nunique()) if "module_name" in grp.columns else len(grp),
            "total_tests":            total,
            "passed":                 passed,
            "failed":                 failed,
            "skipped":                skipped,
            "pending":                pending,
            "unknown":                unknown,
            "pass_rate":              round(passed / executed * 100, 2) if executed else 0.0,
            "total_duration_seconds": round(float(grp["total_duration_seconds"].sum()), 2),
            "avg_duration_seconds":   round(float(grp["total_duration_seconds"].sum()) / total, 2) if total else 0.0,
        })
    return pd.DataFrame(records)


def _ensure_module_cols(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("project_name", "module_name", "platform_type"):
        if col not in df.columns:
            df[col] = "unknown"
    for col in ("passed", "failed", "skipped", "pending", "unknown", "total_tests"):
        if col not in df.columns:
            df[col] = 0
    for col in ("pass_rate", "total_duration_seconds", "avg_duration_seconds"):
        if col not in df.columns:
            df[col] = 0.0
    # Re-derive platform_type from any browser column present
    if "browser" in df.columns:
        df["platform_type"] = df["browser"].apply(_browser_to_platform)
    return df


def _ensure_project_cols(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("project_name", "platform_type"):
        if col not in df.columns:
            df[col] = "unknown"
    for col in ("passed", "failed", "skipped", "pending", "unknown", "total_tests", "module_count"):
        if col not in df.columns:
            df[col] = 0
    for col in ("pass_rate", "total_duration_seconds", "avg_duration_seconds"):
        if col not in df.columns:
            df[col] = 0.0
    return df


def _build_test_cases(flat: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible view; handler.py uses: test_cases.title = flattened_tests.test_name"""
    if flat.empty:
        return pd.DataFrame(columns=["module_name", "priority", "title", "project_name", "platform_type"])
    for col in ("test_name", "module_name", "project_name", "platform_type"):
        if col not in flat.columns:
            flat[col] = "unknown"
    tc = flat[["test_name", "module_name", "project_name", "platform_type"]].drop_duplicates("test_name").copy()
    tc["priority"] = "medium"
    tc["title"]    = tc["test_name"]
    return tc[["module_name", "priority", "title", "project_name", "platform_type"]]


def _log_summary(conn: duckdb.DuckDBPyConnection):
    try:
        rows = conn.execute(
            "SELECT project_name, module_name, platform_type, "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed "
            "FROM flattened_tests "
            "GROUP BY project_name, module_name, platform_type "
            "ORDER BY project_name, module_name, platform_type"
        ).fetchall()
        logger.info("Hierarchy summary (project → module → platform : total / failed):")
        for proj, mod, plat, total, failed in rows:
            logger.info(f"  {proj} → {mod} [{plat}]: {total} tests, {failed} failed")
    except Exception as e:
        logger.warning(f"Could not log hierarchy: {e}")


# ── public API ────────────────────────────────────────────────────────────────

def get_schema_info():
    schemas = {}
    if state.duck_conn:
        for (tbl,) in state.duck_conn.execute("SHOW TABLES").fetchall():
            info = state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
            schemas[tbl] = [(r[0], r[1]) for r in info]
    return schemas


def execute_sql(query: str):
    try:
        if not state.duck_conn:
            return pd.DataFrame(), "Data connection not initialized"
        ok, clean = validate_sql(query)
        if not ok:
            return pd.DataFrame(), clean
        return state.duck_conn.execute(clean).df(), None
    except Exception as exc:
        logger.error(f"SQL error: {exc}")
        return pd.DataFrame(), str(exc)


def vector_search(query: str, top_k: int = 5):
    if not state.lance_db or "documents" not in state.lance_db.table_names():
        return []
    q_emb = state.embedder.embed([query])[0]
    return state.lance_db.open_table("documents").search(q_emb).limit(top_k).to_list()