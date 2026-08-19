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
import threading
import time
from typing import Optional

import duckdb
import lancedb
import numpy as np
import pandas as pd

from . import app_settings, config, state
from universal_ingester.utils import EmbeddingGenerator

logger = logging.getLogger(__name__)

# Guards the cold-load path in ensure_ingestion_loaded (init_data +
# _ingestion_pool insert/eviction). Route handlers now run that path via
# run_in_threadpool, so without this lock, N concurrent requests for the
# same not-yet-warm ingestion would each redundantly re-run the full
# LanceDB -> pandas -> DuckDB rebuild instead of the first one finishing
# and the rest reusing its pool entry.
_ingestion_load_lock = threading.Lock()

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


# ── cross-build access (chat/chart trend & comparison questions) ───────────────

_BUILDS_CACHE_TTL_SECONDS = 10
_builds_cache: tuple[float, list] = (0.0, [])


def list_builds(limit: int | None = None) -> list[dict]:
    """Every ingested build's small pre-aggregated summary.json, newest
    first - the same file the frontend's Build Trends page already reads
    (frontend/app/api/builds/route.ts). Deliberately NOT a DuckDB/LanceDB
    query: each file is a few KB, so listing all of them costs nothing
    regardless of how many builds exist - it's what makes "how are we
    trending" answerable instantly instead of needing to open every build's
    full dataset just to answer a comparison question."""
    global _builds_cache
    now = time.monotonic()
    cached_at, cached = _builds_cache
    if now - cached_at < _BUILDS_CACHE_TTL_SECONDS:
        builds = cached
    else:
        builds = []
        if config.DATA_BASE_PATH.exists():
            for entry in config.DATA_BASE_PATH.iterdir():
                # Two kinds of real build folders: timestamped Allure
                # ingestions (ingestion_YYYYMMDD_HHMMSS) and finalized live
                # runs (run_<hex>, see services/finalize/job.py). Matches
                # BUILD_FOLDER_PATTERN in frontend/app/api/builds/route.ts
                # and frontend/scripts/generate-builds-json.js - keep in
                # sync with those. Matched strictly (not a bare prefix
                # check) so stray/manual debug folders like
                # "ingestion_refactor_test" don't pollute the trend list and
                # cross-build queries with non-build data.
                if not entry.is_dir() or not re.match(r"^(ingestion_\d{8}_\d{6}|run_[0-9a-f]{8,})$", entry.name):
                    continue
                summary_path = entry / "summary.json"
                if not summary_path.exists():
                    continue
                try:
                    raw = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                metrics = raw.get("metrics") or {}
                builds.append({
                    "build_id": raw.get("build_id") or entry.name,
                    "ingested_at": raw.get("ingested_at"),
                    "total_tests": metrics.get("total_tests"),
                    # pass_rate is computed against executed tests (skipped
                    # tests excluded), not total_tests - keep both so
                    # callers can show a passed/executed fraction that
                    # actually agrees with the pass_rate percentage.
                    "executed_tests": metrics.get("executed_tests") or metrics.get("total_tests"),
                    "passed": metrics.get("passed"),
                    "failed": metrics.get("failed"),
                    "pass_rate": metrics.get("pass_rate"),
                    "avg_duration_sec": metrics.get("avg_duration_sec"),
                })
        builds.sort(key=lambda b: b.get("ingested_at") or "", reverse=True)
        _builds_cache = (now, builds)
    return builds[:limit] if limit else builds


def execute_sql_across_builds(sql: str, build_ids: list[str]) -> tuple[pd.DataFrame, str | None]:
    """Run the same validated SQL against several builds and stack the
    results with a build_id column, for questions that genuinely need
    row-level data from more than one build (e.g. "which tests failed in
    both of the last two builds") - list_builds()'s cached summaries can't
    answer that, only full per-build queries can.

    Capped at config.MAX_CROSS_BUILD_QUERY_BUILDS regardless of how many
    build_ids are passed in: unlike list_builds (cheap JSON reads), this
    reopens each build's full DuckDB/LanceDB dataset, so latency scales
    with build count - bounding it keeps worst case predictable no matter
    how much ingestion history has accumulated."""
    build_ids = [b for b in (build_ids or []) if b][: config.MAX_CROSS_BUILD_QUERY_BUILDS]
    if not build_ids:
        return pd.DataFrame(), "No builds specified"

    original_id = state.current_ingestion_id
    frames = []
    last_err = None
    for build_id in build_ids:
        try:
            if not ensure_ingestion_loaded(build_id):
                last_err = f"Ingestion '{build_id}' not found or data unavailable"
                continue
            df, err = execute_sql(sql)
            if err:
                last_err = err
                continue
            if df is not None and not df.empty:
                df = df.copy()
                # flattened_tests already has its own per-row build_id column;
                # overwrite it with the build this query loop iteration is
                # actually tagging rather than inserting a duplicate (which
                # raises ValueError and would otherwise abort the whole
                # cross-build request for one bad query).
                if "build_id" in df.columns:
                    df["build_id"] = build_id
                    df.insert(0, "build_id", df.pop("build_id"))
                else:
                    df.insert(0, "build_id", build_id)
                frames.append(df)
        except Exception as exc:
            last_err = str(exc)
            continue

    # Always restore whichever build the caller had active before this ran -
    # this function must not leave global state pointed at the last build
    # in the loop.
    if original_id:
        ensure_ingestion_loaded(original_id)

    if not frames:
        return pd.DataFrame(), last_err or "No data across the requested builds"
    return pd.concat(frames, ignore_index=True), None


# ── init_data ─────────────────────────────────────────────────────────────────

def init_data(ingestion_id: str) -> Optional[dict]:
    """Cold-build the LanceDB/DuckDB handles for `ingestion_id` and return
    them as {"lance_db", "duck_conn", "embedder"}, or None on failure.

    Deliberately builds into LOCAL variables, not state.* - this runs inside
    get_or_load_ingestion's lock, dispatched via run_in_threadpool from
    request handlers. Writing to state.duck_conn etc. here (as this used to)
    would permanently shadow the ContextVar-backed module attributes for
    every future reader (see state.py) - the very bug this whole change
    exists to remove.
    """
    ingestion_path = config.DATA_BASE_PATH / ingestion_id / "lancedb"
    if not ingestion_path.exists():
        logger.error(f"Ingestion path not found: {ingestion_path}")
        return None

    lance_db = lancedb.connect(str(ingestion_path))
    duck_conn = duckdb.connect()
    embedder = None

    available = lance_db.table_names()
    logger.info(f"LanceDB tables for '{ingestion_id}': {available}")

    if "structured_test_results" not in available:
        # Generalized fallback for arbitrary ingested data.
        structured_candidates = [t for t in available if t.startswith("structured_")]
        if not structured_candidates:
            logger.warning("No structured tables found for ingestion")
            return None
        try:
            primary_table = structured_candidates[0]
            generic_df = lance_db.open_table(primary_table).to_pandas()
            flat = _coerce_generic_to_flattened_tests(generic_df)
            duck_conn.register("flattened_tests", flat)
            logger.info(
                f"Using generalized fallback from {primary_table}: registered flattened_tests with {len(flat)} rows"
            )

            df_mod = _compute_module_metrics(flat)
            duck_conn.register("module_metrics", df_mod)
            df_proj = _compute_project_metrics(df_mod)
            duck_conn.register("project_metrics", df_proj)
            tc = _build_test_cases(flat)
            duck_conn.register("test_cases", tc)

            _log_summary(duck_conn)
            return {"lance_db": lance_db, "duck_conn": duck_conn, "embedder": embedder}
        except Exception as exc:
            logger.error(f"Generalized fallback init failed: {exc}", exc_info=True)
            return None

    try:
        df_raw = lance_db.open_table("structured_test_results").to_pandas()
        logger.info(f"structured_test_results: {len(df_raw)} rows | cols: {list(df_raw.columns)}")

        # ── flatten to per-test rows ──────────────────────────────────────────
        if "tests" in df_raw.columns:
            rows = _flatten_legacy(df_raw)
        else:
            rows = _flatten_normalized(df_raw)

        if not rows:
            logger.warning("No test records after flattening")
            return None

        flat = pd.DataFrame(rows)

        # Ensure platform_type is correct for every row
        # If browser column exists, re-derive platform_type from it (most accurate)
        if "browser" in flat.columns:
            flat["platform_type"] = flat["browser"].apply(_browser_to_platform)
        elif "platform_type" not in flat.columns:
            flat["platform_type"] = "desktop"

        duck_conn.register("flattened_tests", flat)
        logger.info(f"Registered flattened_tests: {len(flat)} rows")

        # ── module_metrics ────────────────────────────────────────────────────
        if "structured_test_module_metrics" in available:
            df_mod = lance_db.open_table("structured_test_module_metrics").to_pandas()
            df_mod = _ensure_module_cols(df_mod)
            # Re-derive platform_type if possible
            duck_conn.register("module_metrics", df_mod)
            logger.info(f"Registered module_metrics from LanceDB: {len(df_mod)} rows")
        else:
            df_mod = _compute_module_metrics(flat)
            duck_conn.register("module_metrics", df_mod)
            logger.info(f"Computed+registered module_metrics: {len(df_mod)} rows")

        # ── project_metrics ───────────────────────────────────────────────────
        if "structured_test_project_metrics" in available:
            df_proj = lance_db.open_table("structured_test_project_metrics").to_pandas()
            df_proj = _ensure_project_cols(df_proj)
            duck_conn.register("project_metrics", df_proj)
            logger.info(f"Registered project_metrics from LanceDB: {len(df_proj)} rows")
        else:
            df_proj = _compute_project_metrics(df_mod)
            duck_conn.register("project_metrics", df_proj)
            logger.info(f"Computed+registered project_metrics: {len(df_proj)} rows")

        # ── test_cases (backward-compat) ──────────────────────────────────────
        tc = _build_test_cases(flat)
        duck_conn.register("test_cases", tc)
        logger.info(f"Registered test_cases: {len(tc)} rows")

        _log_summary(duck_conn)
        return {"lance_db": lance_db, "duck_conn": duck_conn, "embedder": embedder}

    except Exception as exc:
        logger.error(f"init_data failed: {exc}", exc_info=True)
        return None


def get_or_load_ingestion(ingestion_id: str) -> Optional[dict]:
    """Resolve `ingestion_id` to {"lance_db", "duck_conn", "embedder"} using
    a small LRU pool of warm connections (state._ingestion_pool) so repeatedly
    switching between a handful of recently used ingestions is an O(1) pool
    hit instead of a full LanceDB/DuckDB reload.

    Thread-safe, and deliberately does NOT touch which ingestion is
    "active" - it only resolves/builds the pool entry and returns it. Callers
    on the request path (main.py, handlers.py) must call
    state.set_active_ingestion(ingestion_id, **entry) themselves, in their
    own async function, with the dict this returns - see the caveat in
    state.py about why that activation step can't happen in here.
    """
    ingestion_id = str(ingestion_id or "").strip()
    if not ingestion_id:
        return None

    entry = state._ingestion_pool.get(ingestion_id)
    if entry is not None:
        state._ingestion_pool.move_to_end(ingestion_id)
        return entry

    # Cold path: serialize so concurrent requests for the same not-yet-warm
    # ingestion don't each redo the full rebuild (see lock comment above).
    with _ingestion_load_lock:
        # Re-check - another thread may have finished loading this exact
        # ingestion while we were waiting for the lock.
        entry = state._ingestion_pool.get(ingestion_id)
        if entry is not None:
            state._ingestion_pool.move_to_end(ingestion_id)
            return entry

        entry = init_data(ingestion_id)
        if entry is None:
            return None

        state._ingestion_pool[ingestion_id] = entry
        state._ingestion_pool.move_to_end(ingestion_id)
        while len(state._ingestion_pool) > config.INGESTION_POOL_SIZE:
            old_id, old_entry = state._ingestion_pool.popitem(last=False)
            try:
                old_entry["duck_conn"].close()
            except Exception:
                pass
            logger.info(f"Evicted ingestion '{old_id}' from warm pool")
        return entry


def ensure_ingestion_loaded(ingestion_id: str) -> bool:
    """Legacy synchronous API: resolve `ingestion_id` AND make it this
    process's active ingestion in one call, returning success/failure.

    Only safe to use from code that is itself already confined to a single
    thread/context for its whole duration - e.g. execute_sql_across_builds,
    which borrows the active pointer across a loop of builds and restores it
    before returning, all synchronously within whichever single
    run_in_threadpool call dispatched it. Request handlers that need to make
    an ingestion active for the REST of their own execution (including after
    an `await`) must not use this - use
    `await run_in_threadpool(get_or_load_ingestion, id)` followed by
    `state.set_active_ingestion(id, **entry)` in their own async code
    instead, or activation silently won't stick (see state.py).
    """
    entry = get_or_load_ingestion(ingestion_id)
    if entry is None:
        return False
    state.set_active_ingestion(str(ingestion_id or "").strip(), entry["duck_conn"], entry["lance_db"], entry["embedder"])
    return True


# ── flatten helpers ───────────────────────────────────────────────────────────

def _flatten_legacy(df: pd.DataFrame) -> list:
    """Old format: JSON blob in 'tests' column.

    Uses itertuples (namedtuples) instead of iterrows (Series-per-row) since
    the columns here (tests/id/build_id/executed_at) are fixed by the legacy
    connector itself, not arbitrary ingested data — safe to rely on attribute
    access rather than needing dict-like .get() lookups.
    """
    rows = []
    row_id_attr = "id" if "id" in df.columns else None
    build_id_attr = "build_id" if "build_id" in df.columns else None
    executed_at_attr = "executed_at" if "executed_at" in df.columns else None

    for row in df.itertuples(index=False):
        tests = row.tests
        if isinstance(tests, np.ndarray):
            tests = tests.tolist()
        elif isinstance(tests, str):
            try:
                tests = json.loads(tests)
            except Exception:
                continue
        if not isinstance(tests, list):
            continue

        result_id = getattr(row, row_id_attr) if row_id_attr else None
        build_id = getattr(row, build_id_attr) if build_id_attr else None
        executed_at = getattr(row, executed_at_attr) if executed_at_attr else None

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
                "result_id":     result_id,
                "test_name":     t.get("full_title", t.get("name", "")),
                "build_id":      build_id,
                "executed_at":   executed_at,
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
    # "title" covers the live_run connector (universal_ingester/connectors/
    # live_run_connector.py), which names this field "title" to match the
    # Sentinel reporter's own event shape - checked last so it never shadows
    # an Allure-sourced "test_name" column.
    name_col   = next((c for c in ("test_name", "full_name", "name", "title") if c in df.columns), None)
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
        elif "duration_ms" in df.columns and pd.notna(row.get("duration_ms")):
            # live_run connector reports milliseconds under this name.
            dur = float(row["duration_ms"]) / 1000
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


# Fragments that state a duration column's unit. Checked in order, so the
# more specific spelling wins before a shorter one can match inside it.
_DURATION_UNIT_SCALES = (
    ("microsecond", 1e-6),
    ("millisecond", 1e-3),
    ("nanosecond", 1e-9),
    ("micros", 1e-6),
    ("millis", 1e-3),
    ("_usec", 1e-6),
    ("_msec", 1e-3),
    ("_nsec", 1e-9),
    ("_us", 1e-6),
    ("_ms", 1e-3),
    ("_ns", 1e-9),
)

# Per-value suffixes. "ms"/"us"/"ns" must be tried before the bare "s" they
# all end with, or every one of them would be read as seconds.
_DURATION_SUFFIX_SCALES = (
    ("ms", 1e-3),
    ("us", 1e-6),
    ("ns", 1e-9),
    ("sec", 1.0),
    ("min", 60.0),
    ("s", 1.0),
    ("m", 60.0),
    ("h", 3600.0),
)


def _to_seconds(series: pd.Series, column_name: str) -> pd.Series:
    """Normalise an arbitrary duration column to seconds.

    Every downstream number involving time - suite runtime, average test
    duration, slowest-module ranking, the duration axis on charts - assumes
    seconds. A source column named `Duration_ms` used to be copied through
    verbatim, so those readings came out 1000x too large (a 100-test suite
    reporting as 93 hours). The unit is only ever declared in the column
    name, so that is what sets the scale; a row that spells its own unit
    ("240ms") still overrides it.
    """
    name = str(column_name or "").lower()
    scale = 1.0
    for fragment, factor in _DURATION_UNIT_SCALES:
        if fragment in name:
            scale = factor
            break

    numeric = pd.to_numeric(series, errors="coerce")
    result = numeric * scale

    unparsed = numeric.isna() & pd.Series(series).notna()
    if unparsed.any():
        text = pd.Series(series)[unparsed].astype(str).str.strip().str.lower()
        for suffix, factor in _DURATION_SUFFIX_SCALES:
            hit = result.isna() & result.index.isin(text.index)
            candidates = text[text.index.isin(result.index[hit])]
            candidates = candidates[candidates.str.endswith(suffix)]
            if candidates.empty:
                continue
            result.loc[candidates.index] = (
                pd.to_numeric(candidates.str[: -len(suffix)], errors="coerce") * factor
            )

    return result.fillna(0).astype(float)


def _coerce_generic_to_flattened_tests(df: pd.DataFrame) -> pd.DataFrame:
    """Best-effort adapter for arbitrary structured datasets.
    Produces the canonical columns expected by chat/chart logic.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "result_id", "test_name", "build_id", "executed_at", "status", "duration", "error",
            "spec_file", "project_name", "module_name", "platform_type", "browser",
        ])

    out = pd.DataFrame()
    cols = {c.lower(): c for c in df.columns}

    def _empty(default=""):
        return pd.Series([default] * len(df))

    def _pick_named(*names, default=""):
        """Series plus the source column's name. The name matters for
        duration, whose unit is only ever stated in the column name."""
        for n in names:
            key = n.lower()
            if key in cols:
                return df[cols[key]], cols[key]
        return _empty(default), ""

    def _pick(*names, default=""):
        return _pick_named(*names, default=default)[0]

    def _pick_by_aliases_named(aliases: list[str], default=""):
        for alias in aliases:
            for c_lower, c_orig in cols.items():
                if alias in c_lower:
                    return df[c_orig], c_orig
        return _empty(default), ""

    def _pick_by_aliases(aliases: list[str], default=""):
        return _pick_by_aliases_named(aliases, default=default)[0]

    out["result_id"] = _pick("id", "result_id", default="")
    out["test_name"] = _pick("test_name", "name", "title", "full_name", default="record")
    if out["test_name"].astype(str).str.strip().eq("record").all():
        out["test_name"] = _pick_by_aliases(["test", "case", "scenario", "title", "name"], default="record")
    out["build_id"] = _pick("build_id", default="")
    out["executed_at"] = _pick("executed_at", "timestamp", "created_at", "updated_at", default="")

    status_series = _pick("status", "state", "result", "outcome", default="unknown").astype(str)
    if status_series.str.strip().eq("unknown").all():
        status_series = _pick_by_aliases(["status", "state", "result", "outcome"], default="unknown").astype(str)
    out["status"] = status_series.apply(normalize_status)

    duration_raw, duration_col = _pick_named("duration_seconds", "duration", "latency", default=0)
    if pd.to_numeric(duration_raw, errors="coerce").fillna(0).eq(0).all():
        duration_raw, duration_col = _pick_by_aliases_named(
            ["duration", "latency", "elapsed", "time", "runtime"], default=0
        )
    out["duration"] = _to_seconds(duration_raw, duration_col)

    out["error"] = _pick("error", "error_message", "message", default="").astype(str)
    if out["error"].str.strip().eq("").all():
        out["error"] = _pick_by_aliases(["error", "exception", "failure", "message", "stack"], default="").astype(str)

    out["spec_file"] = _pick("spec_file", "file", "path", default="").astype(str)
    out["project_name"] = _pick("project_name", "project", "dataset", default="unknown").astype(str)
    if out["project_name"].str.strip().eq("unknown").all():
        out["project_name"] = _pick_by_aliases(["project", "product", "application", "app", "suite"], default="unknown").astype(str)

    out["module_name"] = _pick("module_name", "module", "suite", "category", "type", default="unknown").astype(str)
    if out["module_name"].str.strip().eq("unknown").all():
        # "suite" belongs here, not only in the project aliases above. A
        # dataset carrying both Project and Suite (a very common export
        # shape) matched Project for project_name and then found nothing for
        # module_name, so every row landed in a single "unknown" module -
        # silently flattening every per-module metric, chart breakdown and
        # blast-radius count into one bucket.
        out["module_name"] = _pick_by_aliases(
            ["module", "component", "feature", "category", "area", "suite", "class"],
            default="unknown",
        ).astype(str)

    out["platform_type"] = _pick("platform_type", default="desktop").astype(str)
    out["browser"] = _pick("browser", "client", default="GoogleChrome").astype(str)
    if out["browser"].str.strip().eq("GoogleChrome").all():
        out["browser"] = _pick_by_aliases(["browser", "device", "client", "user_agent"], default="GoogleChrome").astype(str)

    # If status values are not canonical, infer from free text heuristically.
    bad_status = ~out["status"].isin(["passed", "failed", "skipped", "pending", "unknown"])
    if bad_status.any():
        raw_text = status_series.astype(str).str.lower().fillna("")
        raw_text = raw_text.where(raw_text.str.len() > 0, out["error"].astype(str).str.lower())
        out.loc[raw_text.str.contains("pass|success|ok", regex=True), "status"] = "passed"
        out.loc[raw_text.str.contains("fail|error|exception|broken", regex=True), "status"] = "failed"
        out.loc[raw_text.str.contains("skip|ignored", regex=True), "status"] = "skipped"
        out.loc[raw_text.str.contains("pending|todo", regex=True), "status"] = "pending"
        out["status"] = out["status"].apply(normalize_status)

    out["platform_type"] = out["platform_type"].replace({"": "desktop", None: "desktop"})
    out["project_name"] = out["project_name"].replace({"": "unknown", None: "unknown"})
    out["module_name"] = out["module_name"].replace({"": "unknown", None: "unknown"})
    return out


# ── public API ────────────────────────────────────────────────────────────────

def get_schema_info():
    schemas = {}
    if state.duck_conn:
        with state._duck_query_lock:
            for (tbl,) in state.duck_conn.execute("SHOW TABLES").fetchall():
                info = state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
                schemas[tbl] = [(r[0], r[1]) for r in info]
    return schemas


def get_data_profile(sample_rows: int = 5):
    profile = {"tables": {}}
    if not state.duck_conn:
        return profile

    with state._duck_query_lock:
        try:
            tables = [r[0] for r in state.duck_conn.execute("SHOW TABLES").fetchall()]
        except Exception:
            return profile

        for tbl in tables:
            try:
                info = state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
                count = int(state.duck_conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
                sample_df = state.duck_conn.execute(
                    f"SELECT * FROM {tbl} LIMIT {int(max(1, sample_rows))}"
                ).df()
                profile["tables"][tbl] = {
                    "row_count": count,
                    "columns": [{"name": r[0], "type": r[1]} for r in info],
                    "sample": sample_df.to_dict(orient="records"),
                }
            except Exception as exc:
                profile["tables"][tbl] = {"error": str(exc)}
    return profile


def get_ingestion_quality_report():
    report = {
        "score": 0,
        "quality": "unknown",
        "checks": [],
        "guidance": [],
        "table_counts": {},
        "parser_insights": {},
    }

    if not state.duck_conn:
        report["guidance"].append("Data connection not initialized. Run ingestion first.")
        return report

    with state._duck_query_lock:
        try:
            tables = [r[0] for r in state.duck_conn.execute("SHOW TABLES").fetchall()]
        except Exception as exc:
            report["guidance"].append(f"Could not inspect tables: {exc}")
            return report

        required_tables = ["flattened_tests", "module_metrics", "project_metrics"]
        for tbl in required_tables:
            if tbl in tables:
                count = int(state.duck_conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
                report["table_counts"][tbl] = count
            else:
                report["table_counts"][tbl] = 0

    checks = []
    score_parts = []

    def _add_check(name: str, passed: bool, weight: int, detail: str):
        checks.append({"name": name, "passed": bool(passed), "weight": int(weight), "detail": detail})
        score_parts.append(weight if passed else 0)

    has_flat = report["table_counts"].get("flattened_tests", 0) > 0
    _add_check(
        "flattened_tests availability",
        has_flat,
        30,
        "flattened_tests table exists and has rows" if has_flat else "flattened_tests missing or empty",
    )

    has_module = report["table_counts"].get("module_metrics", 0) > 0
    _add_check(
        "module_metrics availability",
        has_module,
        20,
        "module_metrics table exists and has rows" if has_module else "module_metrics missing or empty",
    )

    has_project = report["table_counts"].get("project_metrics", 0) > 0
    _add_check(
        "project_metrics availability",
        has_project,
        15,
        "project_metrics table exists and has rows" if has_project else "project_metrics missing or empty",
    )

    if has_flat:
        mandatory_cols = [
            "test_name", "status", "duration", "project_name", "module_name", "platform_type"
        ]
        with state._duck_query_lock:
            present = [c[0] for c in state.duck_conn.execute("DESCRIBE flattened_tests").fetchall()]
        missing = [c for c in mandatory_cols if c not in present]
        _add_check(
            "flattened_tests required columns",
            len(missing) == 0,
            20,
            "all required columns present" if not missing else f"missing columns: {missing}",
        )

        try:
            with state._duck_query_lock:
                status_df = state.duck_conn.execute(
                    "SELECT status, COUNT(*) AS cnt FROM flattened_tests GROUP BY status"
                ).df()
            known = {"passed", "failed", "skipped", "pending", "unknown"}
            known_count = int(status_df[status_df["status"].astype(str).str.lower().isin(known)]["cnt"].sum())
            total = int(status_df["cnt"].sum()) if not status_df.empty else 0
            ratio = (known_count / total) if total else 0.0
            _add_check(
                "status normalization",
                ratio >= 0.9,
                15,
                f"known status ratio: {round(ratio * 100, 2)}%",
            )
        except Exception as exc:
            _add_check("status normalization", False, 15, f"status check failed: {exc}")
    else:
        _add_check("flattened_tests required columns", False, 20, "cannot evaluate without flattened_tests")
        _add_check("status normalization", False, 15, "cannot evaluate without flattened_tests")

    report["checks"] = checks
    score = int(sum(score_parts))
    report["score"] = score
    if score >= 85:
        quality = "excellent"
    elif score >= 70:
        quality = "good"
    elif score >= 50:
        quality = "fair"
    else:
        quality = "poor"
    report["quality"] = quality

    guidance = []
    if not has_flat:
        guidance.append("No canonical flattened_tests table found. Ensure source parser emits structured rows or AI parse fallback is enabled.")
    if not has_module:
        guidance.append("module_metrics missing. Verify module_name/project_name are extracted from source data.")
    if not has_project:
        guidance.append("project_metrics missing. Verify project_name/platform_type can be inferred from parsed records.")

    failed_checks = [c for c in checks if not c["passed"]]
    if any(c["name"] == "status normalization" and not c["passed"] for c in failed_checks):
        guidance.append("Status values are noisy. Map source fields to pass/fail/skip/pending before ingestion.")
    if any(c["name"] == "flattened_tests required columns" and not c["passed"] for c in failed_checks):
        guidance.append("Schema mapping incomplete. Provide aliases for missing canonical fields or update connector normalization.")

    # Collect parser strategy insights from schema/source metadata when available.
    if "ingestion_schema_profiles" in tables:
        try:
            with state._duck_query_lock:
                prof_count = int(state.duck_conn.execute("SELECT COUNT(*) FROM ingestion_schema_profiles").fetchone()[0])
            report["parser_insights"]["schema_profiles"] = prof_count
        except Exception:
            pass
    if "sources" in tables:
        try:
            with state._duck_query_lock:
                src_count = int(state.duck_conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0])
            report["parser_insights"]["sources"] = src_count
        except Exception:
            pass

    if not guidance and quality in {"excellent", "good"}:
        guidance.append("Ingestion quality is healthy. No immediate action required.")
    report["guidance"] = guidance
    return report


def execute_sql(query: str):
    try:
        if not state.duck_conn:
            return pd.DataFrame(), "Data connection not initialized"
        ok, clean = validate_sql(query)
        if not ok:
            return pd.DataFrame(), clean
        with state._duck_query_lock:
            return state.duck_conn.execute(clean).df(), None
    except Exception as exc:
        logger.error(f"SQL error: {exc}")
        return pd.DataFrame(), str(exc)


_embedder_singleton: Optional[EmbeddingGenerator] = None
_embedder_singleton_model: Optional[str] = None
_embedder_singleton_lock = threading.Lock()


def _get_shared_embedder() -> EmbeddingGenerator:
    """Process-wide singleton keyed to the currently EFFECTIVE embedding
    model (services/app_settings.py: database > env > default, same
    resolution as the LLM settings). Rebuilds itself if an admin changes the
    model from Settings, so that takes effect on the next call - no restart
    needed. Previously this was accidentally rebuilt (tokenizer + weights
    reloaded) on every single vector_search() call: state.embedder's "cache"
    only lived in a per-request ContextVar that got reset to None on every
    request, so the lazy-create-and-cache in the old vector_search never
    actually persisted anything."""
    global _embedder_singleton, _embedder_singleton_model
    effective_model = app_settings.get_effective_embedding_model()
    if _embedder_singleton is None or _embedder_singleton_model != effective_model:
        with _embedder_singleton_lock:
            if _embedder_singleton is None or _embedder_singleton_model != effective_model:
                _embedder_singleton = EmbeddingGenerator(model_name=effective_model)
                _embedder_singleton_model = effective_model
    return _embedder_singleton


def _stored_embedding_model(table) -> Optional[str]:
    """Which model this build's documents were actually embedded with, from
    the first row's 'embedding_model' tag (see ingester._embed_and_store).
    None for a table predating that tag (legacy build) or any read hiccup -
    treated as "unknown, proceed" by the caller rather than a hard block, so
    pre-upgrade data doesn't become entirely unsearchable."""
    try:
        cols = table.schema.names
        if "embedding_model" not in cols:
            return None
        row = table.head(1).to_pandas()
        if row.empty:
            return None
        value = row["embedding_model"].iloc[0]
        return str(value) if value else None
    except Exception:
        return None


def vector_search(query: str, top_k: int = 5):
    if state.lance_db is None or "documents" not in state.lance_db.table_names():
        return []
    try:
        table = state.lance_db.open_table("documents")
        embedder = _get_shared_embedder()

        stored_model = _stored_embedding_model(table)
        if stored_model and stored_model != embedder.model_name:
            # Two different models can share a vector dimension (e.g. both
            # 384-dim) while their embedding spaces are unrelated - a
            # dimension mismatch would at least raise below, but a
            # same-dimension mismatch would silently return
            # plausible-looking, meaningless nearest-neighbors instead.
            # Refuse rather than risk that; the caller already treats an
            # empty result as "no relevant information found".
            logger.warning(
                "vector_search skipped: this build was embedded with '%s' but "
                "'%s' is currently configured - re-ingest this build to search "
                "it under the new model.", stored_model, embedder.model_name,
            )
            return []

        q_emb = embedder.embed([query])[0]
        return table.search(q_emb).limit(top_k).to_list()
    except Exception as exc:
        # Covers a genuine dimensionality mismatch (different-size vectors)
        # for legacy builds with no embedding_model tag to check above -
        # degrade to "no results" instead of a hard 500, same as any other
        # empty-result case the chat vector path already handles gracefully.
        logger.warning("vector_search failed for query %r: %s", query[:80], exc)
        return []