import json
import logging
import pandas as pd
import numpy as np
import lancedb
import duckdb
import re
from pathlib import Path
from . import config, state
from universal_ingester.utils import EmbeddingGenerator

logger = logging.getLogger(__name__)

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
        "pass": "passed",
        "passed": "passed",
        "success": "passed",
        "ok": "passed",
        "fail": "failed",
        "failed": "failed",
        "error": "failed",
        "broken": "failed",
        "skip": "skipped",
        "skipped": "skipped",
        "pending": "pending",
    }
    return status_map.get(value, value or "unknown")


def sanitize_sql(query: str) -> str:
    if not query:
        return ""
    cleaned = query.strip()
    cleaned = re.sub(r"```sql\s*|```", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*duckdb\s*:?", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().rstrip(";")
    return cleaned


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

def init_data(ingestion_id: str):
    """Load data for a specific ingestion into state.lance_db and state.duck_conn."""
    ingestion_path = config.DATA_BASE_PATH / ingestion_id / "lancedb"
    if not ingestion_path.exists():
        logger.error(f"Ingestion path {ingestion_path} not found.")
        return False

    state.lance_db = lancedb.connect(str(ingestion_path))
    state.duck_conn = duckdb.connect()
    state.embedder = EmbeddingGenerator()
    state.current_ingestion_id = ingestion_id

    raw_tables = state.lance_db.table_names()
    logger.info(f"Tables found for {ingestion_id}: {raw_tables}")

    # Load test_cases
    if "structured_test_cases" in raw_tables:
        try:
            df_cases = state.lance_db.open_table("structured_test_cases").to_pandas()
            state.duck_conn.register("test_cases", df_cases)
            logger.info(f"Loaded {len(df_cases)} test cases")
        except Exception as e:
            logger.error(f"Error loading test_cases: {e}")

    # Load test_results and flatten
    if "structured_test_results" in raw_tables:
        try:
            df_results = state.lance_db.open_table("structured_test_results").to_pandas()
            logger.info(f"Loaded {len(df_results)} test results")
            if "tests" in df_results.columns:
                rows = []
                for _, row in df_results.iterrows():
                    tests = row["tests"]
                    if isinstance(tests, np.ndarray):
                        tests = tests.tolist()
                    elif isinstance(tests, str):
                        try:
                            tests = json.loads(tests)
                        except:
                            continue
                    if isinstance(tests, list):
                        for t in tests:
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
                                "test_name": t.get("full_title", ""),
                                "build_id": row.get("build_id"),
                                "project_id": row.get("project_id"),
                                "executed_at": row.get("executed_at"),
                                "status": normalize_status(
                                    t.get("status") or t.get("state") or t.get("outcome") or t.get("result")
                                ),
                                "duration": dur,
                                "error": err,
                                "spec_file": t.get("spec_file", ""),
                            })
                if rows:
                    flattened = pd.DataFrame(rows)
                    state.duck_conn.register("flattened_tests", flattened)
                    logger.info(f"Flattened {len(flattened)} test executions")
        except Exception as e:
            logger.error(f"Error loading test_results: {e}")
            import traceback
            traceback.print_exc()
    return True

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