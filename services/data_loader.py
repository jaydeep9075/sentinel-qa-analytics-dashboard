import json
import logging
import pandas as pd
import numpy as np
import lancedb
import duckdb
from . import config, state
from universal_ingester.utils import EmbeddingGenerator

logger = logging.getLogger(__name__)

def init_data():
    """Load data from LanceDB into DuckDB and embedder."""
    if not config.DATA_PATH.exists():
        logger.error(f"Data path {config.DATA_PATH} not found. Run ingester first.")
        return

    state.lance_db = lancedb.connect(str(config.DATA_PATH))
    state.duck_conn = duckdb.connect()
    state.embedder = EmbeddingGenerator()

    # Get table names correctly (handles different LanceDB return types)
    raw_result = state.lance_db.list_tables()
    if hasattr(raw_result, 'tables'):
        raw_tables = raw_result.tables
    else:
        raw_tables = raw_result

    tables = []
    for t in raw_tables:
        if isinstance(t, tuple):
            tables.append(t[0])
        else:
            tables.append(t)
    logger.info(f"Tables found: {tables}")

    # Load test_cases
    if "structured_test_cases" in tables:
        try:
            df_cases = state.lance_db.open_table("structured_test_cases").to_pandas()
            state.duck_conn.register("test_cases", df_cases)
            logger.info(f"Loaded {len(df_cases)} test cases")
        except Exception as e:
            logger.error(f"Error loading test_cases: {e}")

    # Load test_results and flatten
    if "structured_test_results" in tables:
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
                                "build_id": row.get("build_id"),
                                "project_id": row.get("project_id"),
                                "executed_at": row.get("executed_at"),
                                "test_name": t.get("full_title", ""),
                                "status": t.get("status", "").lower(),
                                "duration": dur,
                                "error": err,
                                "spec_file": t.get("spec_file", ""),
                            })
                if rows:
                    flattened = pd.DataFrame(rows)
                    state.duck_conn.register("flattened_tests", flattened)
                    logger.info(f"Flattened {len(flattened)} test executions")
                    # Verify
                    try:
                        result = state.duck_conn.execute("SHOW TABLES").fetchall()
                        logger.info(f"Tables in DuckDB after flattening: {[t[0] for t in result]}")
                    except Exception as e:
                        logger.error(f"Could not verify tables: {e}")
                else:
                    logger.warning("No test records could be flattened")
            else:
                logger.warning("No 'tests' column in test_results")
        except Exception as e:
            logger.error(f"Error loading test_results: {e}")
            import traceback
            traceback.print_exc()

    # IMPORTANT: Do NOT create chat_history or chart_history tables here.
    # They will be created by memory.py with the correct PyArrow schema.
    # Creating them with an empty pandas DataFrame causes null column types,
    # which makes inserts fail with "cannot cast field 'id' from Utf8 to Null".

def get_schema_info():
    """Return dictionary of table schemas in DuckDB."""
    schemas = {}
    if state.duck_conn:
        tables = state.duck_conn.execute("SHOW TABLES").fetchall()
        for (tbl,) in tables:
            info = state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
            schemas[tbl] = [(row[0], row[1]) for row in info]
    return schemas

def execute_sql(query: str):
    """Execute SQL and return (DataFrame, error) tuple."""
    try:
        df = state.duck_conn.execute(query).df()
        return df, None
    except Exception as e:
        logger.error(f"SQL error: {e}")
        return pd.DataFrame(), str(e)

def vector_search(query: str, top_k: int = 5):
    if not state.lance_db or "documents" not in state.lance_db.list_tables():
        return []
    q_emb = state.embedder.embed([query])[0]
    table = state.lance_db.open_table("documents")
    return table.search(q_emb).limit(top_k).to_list()