# data_loader.py (complete replacement)
import json
import logging
import pandas as pd
import numpy as np
import lancedb
import duckdb
import re
from threading import Lock
from pathlib import Path
from . import config, state
from universal_ingester.utils import EmbeddingGenerator

logger = logging.getLogger(__name__)
_init_lock = Lock()

_DISALLOWED_SQL_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bCOPY\b",
]

def normalize_status(raw_status: str) -> str:
    value = str(raw_status or "").strip().lower()
    status_map = {
        "pass": "passed", "passed": "passed", "success": "passed", "ok": "passed",
        "fail": "failed", "failed": "failed", "error": "failed", "broken": "failed",
        "skip": "skipped", "skipped": "skipped", "pending": "pending",
    }
    return status_map.get(value, value or "unknown")

def sanitize_sql(query: str) -> str:
    if not query:
        return ""
    cleaned = query.strip()
    cleaned = re.sub(r"```sql\s*|```", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*duckdb\s*:?", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(";")

def validate_sql(query: str):
    cleaned = sanitize_sql(query)
    if not cleaned:
        return False, "Empty SQL query"
    if not re.search(r"\bSELECT\b", cleaned, flags=re.IGNORECASE):
        return False, "Only SELECT queries are allowed"
    for pattern in _DISALLOWED_SQL_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            return False, "Unsafe SQL pattern detected"
    return True, cleaned

def extract_module_from_spec(spec_file: str) -> str:
    """Extract module name from spec file path."""
    if not spec_file:
        return "unknown"
    # Example: "Platforms/SFRA/Checkout/WDH/..."
    parts = spec_file.replace("\\", "/").split("/")
    if len(parts) >= 3:
        # Return e.g., "SFRA/Checkout" or just the second level
        return f"{parts[1]}/{parts[2]}" if len(parts) > 2 else parts[1]
    return "unknown"

def init_data(ingestion_id: str):
    ingestion_id = str(ingestion_id or "").strip()
    if not ingestion_id:
        logger.error("init_data called with empty ingestion_id")
        return False

    # Fast path: already initialized and healthy.
    if (
        state.current_ingestion_id == ingestion_id
        and state.lance_db is not None
        and state.duck_conn is not None
    ):
        try:
            state.duck_conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            logger.warning("Existing DuckDB handle is unhealthy; reinitializing data connection.")

    with _init_lock:
        # Double-check after acquiring lock to avoid duplicate inits under concurrent requests.
        if (
            state.current_ingestion_id == ingestion_id
            and state.lance_db is not None
            and state.duck_conn is not None
        ):
            try:
                state.duck_conn.execute("SELECT 1").fetchone()
                return True
            except Exception:
                logger.warning("Existing DuckDB handle failed health-check in lock; reinitializing.")

        ingestion_path = config.DATA_BASE_PATH / ingestion_id / "lancedb"
        if not ingestion_path.exists():
            logger.error(f"Ingestion path {ingestion_path} not found.")
            return False

        try:
            if state.duck_conn is not None:
                state.duck_conn.close()
        except Exception:
            logger.warning("Failed closing previous DuckDB connection cleanly.")

        state.lance_db = lancedb.connect(str(ingestion_path))
        state.duck_conn = duckdb.connect()
        if state.embedder is None:
            state.embedder = EmbeddingGenerator()
        state.current_ingestion_id = ingestion_id

        raw_tables = state.lance_db.table_names()
        logger.info(f"Tables found for {ingestion_id}: {raw_tables}")

        if "structured_test_results" not in raw_tables:
            logger.warning("No structured_test_results table found")
            return False

        try:
            df_results = state.lance_db.open_table("structured_test_results").to_pandas()
            logger.info(f"Loaded {len(df_results)} test results rows")

            rows = []
            if "tests" in df_results.columns:
                logger.info("Old format detected")
                for _, row in df_results.iterrows():
                    tests_data = row["tests"]
                    if isinstance(tests_data, np.ndarray):
                        tests_data = tests_data.tolist()
                    elif isinstance(tests_data, str):
                        try:
                            tests_data = json.loads(tests_data)
                        except Exception:
                            continue
                    if not isinstance(tests_data, list):
                        continue
                    for t in tests_data:
                        dur_raw = t.get("duration", "0")
                        if isinstance(dur_raw, str):
                            if dur_raw.endswith("ms"):
                                dur = float(dur_raw[:-2]) / 1000
                            else:
                                dur = float(dur_raw) if dur_raw else 0
                        else:
                            dur = float(dur_raw) if dur_raw else 0
                        err = t.get("error", "")
                        if isinstance(err, dict):
                            err = err.get("message", "")
                        rows.append({
                            "result_id": row.get("id"),
                            "test_name": t.get("full_title", t.get("name", "")),
                            "build_id": row.get("build_id"),
                            "project_id": row.get("project_id"),
                            "executed_at": row.get("executed_at"),
                            "status": normalize_status(t.get("status") or t.get("state") or t.get("outcome") or t.get("result")),
                            "duration": dur,
                            "error": err,
                            "spec_file": t.get("spec_file", ""),
                        })
            else:
                logger.info("New normalized format detected")
                test_name_col = next((c for c in ["test_name", "full_name", "name"] if c in df_results.columns), None)
                status_col = "status" if "status" in df_results.columns else None
                duration_col = "duration_seconds" if "duration_seconds" in df_results.columns else "duration"
                error_col = "error_message" if "error_message" in df_results.columns else "error" if "error" in df_results.columns else None
                spec_col = "spec_file" if "spec_file" in df_results.columns else None

                if not (test_name_col and status_col):
                    logger.error("Missing required columns")
                    return False

                for _, row in df_results.iterrows():
                    test_name = row[test_name_col]
                    status_raw = row[status_col]
                    if duration_col == "duration_seconds":
                        dur = float(row[duration_col]) if pd.notna(row[duration_col]) else 0.0
                    else:
                        dur_raw = row.get(duration_col, "0")
                        if isinstance(dur_raw, str):
                            if dur_raw.endswith("ms"):
                                dur = float(dur_raw[:-2]) / 1000
                            else:
                                dur = float(dur_raw) if dur_raw else 0
                        else:
                            dur = float(dur_raw) if dur_raw else 0
                    err = row[error_col] if error_col and pd.notna(row[error_col]) else ""
                    if isinstance(err, dict):
                        err = err.get("message", "")
                    spec_file = row[spec_col] if spec_col else ""
                    rows.append({
                        "result_id": row.get("id"),
                        "test_name": test_name,
                        "build_id": row.get("build_id"),
                        "project_id": row.get("project_id"),
                        "project_name": row.get("project_name", "unknown"),
                        "module_name": row.get("module_name", "unknown"),
                        "platform_type": row.get("platform_type", "desktop"),
                        "executed_at": row.get("executed_at"),
                        "status": normalize_status(status_raw),
                        "duration": dur,
                        "error": str(err),
                        "spec_file": spec_file,
                    })

            if not rows:
                logger.warning("No test records found")
                return False

            flattened = pd.DataFrame(rows)
            state.duck_conn.register("flattened_tests", flattened)
            logger.info(f"Registered flattened_tests with {len(flattened)} rows")

            if "spec_file" in flattened.columns:
                test_cases_df = flattened[["test_name", "spec_file"]].drop_duplicates(subset=["test_name"]).copy()
                if "module_name" in flattened.columns:
                    module_map = flattened[["test_name", "module_name"]].drop_duplicates(subset=["test_name"])
                    test_cases_df = test_cases_df.merge(module_map, on="test_name", how="left")
                    test_cases_df["module_name"] = test_cases_df["module_name"].fillna(
                        test_cases_df["spec_file"].apply(extract_module_from_spec)
                    )
                else:
                    test_cases_df["module_name"] = test_cases_df["spec_file"].apply(extract_module_from_spec)
                test_cases_df["priority"] = "medium"
                test_cases_df["title"] = test_cases_df["test_name"]
                test_cases_df = test_cases_df[["module_name", "priority", "title"]]
                state.duck_conn.register("test_cases", test_cases_df)
                logger.info(f"Created test_cases table with {len(test_cases_df)} rows")
            else:
                empty_cases = pd.DataFrame(columns=["module_name", "priority", "title"])
                state.duck_conn.register("test_cases", empty_cases)
                logger.warning("No spec_file column, test_cases created empty")

            return True

        except Exception as e:
            logger.error(f"Error in init_data: {e}")
            import traceback
            traceback.print_exc()
            return False

def get_schema_info():
    schemas = {}
    if state.duck_conn:
        tables = state.duck_conn.execute("SHOW TABLES").fetchall()
        for (tbl,) in tables:
            info = state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
            schemas[tbl] = [(row[0], row[1]) for row in info]
    return schemas

def execute_sql(query: str):
    try:
        if not state.duck_conn:
            return pd.DataFrame(), "Data connection is not initialized"
        is_valid, validated_or_error = validate_sql(query)
        if not is_valid:
            return pd.DataFrame(), validated_or_error
        df = state.duck_conn.execute(validated_or_error).df()
        return df, None
    except Exception as e:
        logger.error(f"SQL error: {e}")
        return pd.DataFrame(), str(e)

def vector_search(query: str, top_k: int = 5):
    if not state.lance_db or "documents" not in state.lance_db.table_names():
        return []
    q_emb = state.embedder.embed([query])[0]
    table = state.lance_db.open_table("documents")
    return table.search(q_emb).limit(top_k).to_list()