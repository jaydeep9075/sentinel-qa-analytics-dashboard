import os
import json
import uuid
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

import pandas as pd
import numpy as np
import lancedb
import duckdb

from connectors.file_connector import FileConnector
from connectors.db_connector import DBConnector
from connectors.api_connector import APIConnector
from utils import EmbeddingGenerator

logger = logging.getLogger(__name__)

class UniversalIngester:
    def __init__(self, data_base_path: str = "../data"):
        self.data_base_path = Path(data_base_path).absolute()
        self.data_base_path.mkdir(parents=True, exist_ok=True)
        self.embedder = EmbeddingGenerator()
        self.duck_db = None
        self.lance_db = None

    def ingest_source(self, source_config: Dict[str, Any], build_id: str):
        ingestion_folder = self.data_base_path / build_id
        ingestion_folder.mkdir(exist_ok=True)
        lancedb_path = ingestion_folder / "lancedb"
        lancedb_path.mkdir(exist_ok=True)

        self.lance_db = lancedb.connect(str(lancedb_path))
        self.duck_db = duckdb.connect()

        source_type = source_config['type']
        # Support both nested 'params' and flat config
        params = source_config.get('params', source_config)

        if source_type == 'file':
            connector = FileConnector(params['path'])
        elif source_type == 'db':
            connector = DBConnector(
                connection_string=params['connection_string'],
                tables=params.get('tables'),
                connect_args=params.get('connect_args')
            )
        elif source_type == 'api':
            connector = APIConnector(
                url=params['url'],
                method=params.get('method', 'GET'),
                headers=params.get('headers'),
                params=params.get('params')
            )
        elif source_type == 'allure':
            from connectors.allure_connector import AllureConnector
            path = params.get('path') or params.get('directory')
            if not path:
                raise ValueError("Allure source requires 'path' or 'directory' in config")
            connector = AllureConnector(path)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

        datasets = connector.fetch()
        total_rows = 0
        for dataset in datasets:
            rows = self._ingest_dataset(dataset, source_type, build_id)
            total_rows += rows

        self.link_to_duckdb()
        self._generate_summary(build_id, total_rows)
        logger.info(f"Ingestion {build_id} completed. Summary saved.")

    def _ingest_dataset(self, dataset: Dict[str, Any], source_type: str, build_id: str) -> int:
        name = dataset['name']
        data = dataset['data']
        data_type = dataset['type']
        metadata = dataset.get('metadata', {})

        source_id = f"{name}_{build_id}"
        logger.info(f"Ingesting dataset {name} as {data_type} (build {build_id})")

        if data_type == 'structured':
            df = data.copy()
            if 'build_id' not in df.columns:
                df['build_id'] = build_id
            else:
                if 'original_build_id' not in df.columns:
                    df = df.rename(columns={'build_id': 'original_build_id'})
                df['build_id'] = build_id

            table_name = f"structured_{name}"
            if table_name in self.lance_db.table_names():
                table = self.lance_db.open_table(table_name)
                table.add(df)
                logger.info(f"Appended {len(df)} rows to {table_name} (build {build_id})")
            else:
                self.lance_db.create_table(table_name, df)
                logger.info(f"Created new table {table_name} with {len(df)} rows")

            docs = self._df_to_documents(df, name, source_id, metadata, build_id)
            if docs:
                texts = [doc['text'] for doc in docs]
                embeddings = self.embedder.embed(texts)
                for doc, emb in zip(docs, embeddings):
                    doc['embedding'] = emb
                self._add_documents(docs)

            self._add_source(source_id, source_type, name, len(df), metadata, build_id)
            return len(df)

        elif data_type == 'unstructured':
            docs = []
            for i, item in enumerate(data):
                text = item.get('text', '')
                if not text:
                    continue
                doc = {
                    'id': f"{name}_{i}_{uuid.uuid4().hex[:8]}",
                    'text': text,
                    'metadata': json.dumps({**metadata, 'index': i}),
                    'source_id': source_id,
                    'build_id': build_id,
                    'timestamp': datetime.now(timezone.utc)
                }
                docs.append(doc)

            if docs:
                texts = [doc['text'] for doc in docs]
                embeddings = self.embedder.embed(texts)
                for doc, emb in zip(docs, embeddings):
                    doc['embedding'] = emb
                self._add_documents(docs)

            self._add_source(source_id, source_type, name, len(docs), metadata, build_id)
            return len(docs)

        else:
            raise ValueError(f"Unknown data type: {data_type}")

    def _df_to_documents(self, df: pd.DataFrame, dataset_name: str, source_id: str, metadata: dict, build_id: str) -> List[Dict]:
        docs = []
        for idx, row in df.iterrows():
            parts = []
            for col in df.columns:
                val = row[col]
                if isinstance(val, (list, dict, tuple)):
                    val_str = json.dumps(val)
                else:
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        continue
                    val_str = str(val)
                parts.append(f"{col}: {val_str}")
            text = " | ".join(parts)
            if not text:
                continue
            doc = {
                'id': f"{dataset_name}_{idx}_{uuid.uuid4().hex[:8]}",
                'text': text,
                'metadata': json.dumps({**metadata, 'row_index': idx, 'columns': list(df.columns)}),
                'source_id': source_id,
                'build_id': build_id,
                'timestamp': datetime.now(timezone.utc)
            }
            docs.append(doc)
        return docs

    def _add_documents(self, docs: List[Dict]):
        if not docs:
            return
        table_name = "documents"
        if table_name in self.lance_db.table_names():
            table = self.lance_db.open_table(table_name)
            if table.count_rows() == 0:
                logger.info(f"Dropping empty {table_name} table to recreate with correct schema.")
                self.lance_db.drop_table(table_name)
                self.lance_db.create_table(table_name, docs)
            else:
                table.add(docs)
        else:
            self.lance_db.create_table(table_name, docs)
        logger.info(f"Added {len(docs)} documents to {table_name}")

    def _add_source(self, source_id: str, source_type: str, source_name: str,
                    row_count: int, metadata: dict, build_id: str):
        source_record = {
            'source_id': source_id,
            'source_type': source_type,
            'source_name': source_name,
            'build_id': build_id,
            'ingestion_time': datetime.now(timezone.utc),
            'row_count': row_count,
            'status': 'success',
            'metadata': json.dumps(metadata)
        }
        table_name = "sources"
        if table_name in self.lance_db.table_names():
            table = self.lance_db.open_table(table_name)
            if table.count_rows() == 0:
                logger.info(f"Dropping empty {table_name} table to recreate with correct schema.")
                self.lance_db.drop_table(table_name)
                self.lance_db.create_table(table_name, [source_record])
            else:
                table.add([source_record])
        else:
            self.lance_db.create_table(table_name, [source_record])
        logger.info(f"Recorded source {source_id} (build {build_id})")

    def link_to_duckdb(self):
        tables = self.lance_db.table_names()
        for t in tables:
            if t.startswith('structured_'):
                df = self.lance_db.open_table(t).to_pandas()
                self.duck_db.register(t, df)
                logger.info(f"Registered {t} in DuckDB")
        if 'documents' in self.lance_db.table_names():
            df_docs = self.lance_db.open_table('documents').to_pandas()
            self.duck_db.register('documents', df_docs)
        if 'sources' in self.lance_db.table_names():
            df_sources = self.lance_db.open_table('sources').to_pandas()
            self.duck_db.register('sources', df_sources)
        return self.duck_db

    def _generate_summary(self, build_id: str, total_rows: int):
        """Generate summary.md and summary.json from structured_test_results.
        Works for both TiDB and Allure data formats."""
        import json
        import re
        from datetime import datetime, timezone
        import pandas as pd
        import numpy as np

        summary_md_path = self.data_base_path / build_id / "summary.md"
        summary_json_path = self.data_base_path / build_id / "summary.json"

        metrics = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "avg_duration_sec": 0.0,
            "total_duration_sec": 0.0,
            "most_common_error": "",
            "slowest_tests": []
        }

        lines = [
            f"# Ingestion Summary: {build_id}",
            "",
            f"**Ingested at:** {datetime.now(timezone.utc).isoformat()}",
            f"**Total records ingested:** {total_rows}",
            "",
        ]

        tables_in_db = self.lance_db.table_names()
        logger.info(f"Tables in DB: {tables_in_db}")

        if "structured_test_results" not in tables_in_db:
            lines.append("## ⚠️ Test Metrics")
            lines.append("No `structured_test_results` table found.")
            summary_md_path.write_text("\n".join(lines), encoding='utf-8')
            return

        try:
            # Read the entire table into a pandas DataFrame
            df_results = self.lance_db.open_table("structured_test_results").to_pandas()
            logger.info(f"structured_test_results rows: {len(df_results)}")
            logger.info(f"Columns: {list(df_results.columns)}")

            if 'tests' not in df_results.columns:
                lines.append("## ⚠️ Test Metrics")
                lines.append("No 'tests' column found in table.")
                summary_md_path.write_text("\n".join(lines), encoding='utf-8')
                return

            # Extract all individual test records from the 'tests' column
            all_tests = []
            for tests_raw in df_results['tests'].dropna():
                # Parse if it's a JSON string
                if isinstance(tests_raw, str):
                    try:
                        tests_data = json.loads(tests_raw)
                    except Exception as e:
                        logger.warning(f"Failed to parse tests JSON: {e}")
                        continue
                # Handle NumPy array (convert to list)
                elif isinstance(tests_raw, np.ndarray):
                    tests_data = tests_raw.tolist()
                else:
                    tests_data = tests_raw

                # Handle both list and dict structures
                if isinstance(tests_data, list):
                    all_tests.extend(tests_data)
                elif isinstance(tests_data, dict):
                    # Some formats store tests under a key like 'test_cases' or 'tests'
                    found = False
                    for key in ['test_cases', 'tests', 'cases', 'results', 'items', 'data']:
                        if key in tests_data and isinstance(tests_data[key], list):
                            all_tests.extend(tests_data[key])
                            found = True
                            break
                    if not found:
                        all_tests.append(tests_data)

            logger.info(f"Extracted {len(all_tests)} individual test records")

            if not all_tests:
                lines.append("## ⚠️ Test Metrics")
                lines.append("No test records found in 'tests' column.")
                summary_md_path.write_text("\n".join(lines), encoding='utf-8')
                # Still write JSON with empty metrics
                json_data = {
                    "build_id": build_id,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "total_records_ingested": total_rows,
                    "metrics": metrics,
                    "tables": tables_in_db
                }
                with open(summary_json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                logger.info(f"JSON summary written to {summary_json_path}")
                return

            df_tests = pd.DataFrame(all_tests)
            logger.info(f"Test DataFrame columns: {list(df_tests.columns)}")

            # --- Flexible column detection (supports TiDB and Allure) ---
            test_name_col = None
            for col in ['full_title', 'title', 'test_name', 'name']:
                if col in df_tests.columns:
                    test_name_col = col
                    break

            status_col = None
            for col in ['status', 'state', 'outcome', 'result']:
                if col in df_tests.columns:
                    status_col = col
                    break

            duration_col = None
            for col in ['duration', 'duration_ms', 'time']:
                if col in df_tests.columns:
                    duration_col = col
                    break

            error_col = None
            for col in ['error', 'error_message', 'message']:
                if col in df_tests.columns:
                    error_col = col
                    break

            logger.info(f"Detected columns: name={test_name_col}, status={status_col}, duration={duration_col}, error={error_col}")

            if not (status_col and test_name_col and duration_col):
                lines.append("## ⚠️ Test Metrics")
                lines.append(f"Missing required columns. Found: name={test_name_col}, status={status_col}, duration={duration_col}")
                summary_md_path.write_text("\n".join(lines), encoding='utf-8')
                return

            # --- Robust duration parser (handles '43758ms', '88ms', '1.5s', numeric ms/seconds) ---
            def parse_duration(val):
                if pd.isna(val):
                    return None
                # Numeric (int/float) – assume milliseconds
                if isinstance(val, (int, float)):
                    return float(val) / 1000.0
                if isinstance(val, str):
                    val = val.strip().lower()
                    # Extract number and optional unit
                    match = re.match(r'^([\d.]+)\s*(ms|s|m|h)?$', val)
                    if not match:
                        return None
                    num = float(match.group(1))
                    unit = match.group(2) or 's'
                    if unit == 'ms':
                        return num / 1000.0
                    elif unit == 'm':
                        return num * 60.0
                    elif unit == 'h':
                        return num * 3600.0
                    else:  # seconds or no unit
                        return num
                return None

            df_tests['duration_seconds'] = df_tests[duration_col].apply(parse_duration)
            valid_durations = df_tests['duration_seconds'].dropna()
            logger.info(f"Valid durations: {len(valid_durations)} / {len(df_tests)}")

            # --- Calculate metrics ---
            total_tests = len(df_tests)
            # Normalize status strings (case‑insensitive)
            status_series = df_tests[status_col].astype(str).str.lower()
            passed = status_series.eq('passed').sum()
            failed = status_series.isin(['failed', 'broken', 'error']).sum()
            pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0.0

            avg_duration = valid_durations.mean() if len(valid_durations) > 0 else 0.0
            total_duration = valid_durations.sum() if len(valid_durations) > 0 else 0.0

            # Top 15 slowest tests
            slowest = []
            if not df_tests.empty:
                df_valid = df_tests[df_tests['duration_seconds'].notna()].copy()
                if not df_valid.empty:
                    df_top = df_valid.nlargest(15, 'duration_seconds')
                    slowest = [
                        {"name": str(row[test_name_col]), "duration_sec": round(row['duration_seconds'], 2)}
                        for _, row in df_top.iterrows()
                    ]

            # Most common error message (only from failed tests)
            common_error = ""
            if error_col:
                failed_mask = status_series.isin(['failed', 'broken', 'error'])
                errors = df_tests.loc[failed_mask, error_col].dropna()
                error_strings = []
                for err in errors:
                    if isinstance(err, dict):
                        msg = err.get('message', '') or str(err)
                    else:
                        msg = str(err)
                    if msg and msg.strip() and msg != '{}':
                        error_strings.append(msg.strip())
                if error_strings:
                    common_error = pd.Series(error_strings).mode().iloc[0][:200]

            metrics = {
                "total_tests": int(total_tests),
                "passed": int(passed),
                "failed": int(failed),
                "pass_rate": round(pass_rate, 2),
                "avg_duration_sec": round(avg_duration, 2),
                "total_duration_sec": round(total_duration, 2),
                "most_common_error": common_error,
                "slowest_tests": slowest
            }

            # Build markdown summary
            lines.append("## 📊 Test Metrics")
            lines.append(f"- **Total number of tests:** {total_tests}")
            lines.append(f"- **Passed tests:** {passed}")
            lines.append(f"- **Failed tests:** {failed}")
            lines.append(f"- **Pass rate:** {pass_rate:.2f}%")
            lines.append(f"- **Average duration:** {avg_duration:.2f} seconds")
            lines.append(f"- **Total duration:** {total_duration:.2f} seconds")
            lines.append(f"- **Most common failure reason:** {common_error if common_error else '(no error messages captured)'}")

            if slowest:
                lines.append("\n### 🐢 Top 15 Slowest Tests")
                lines.append("| Test Name | Duration (seconds) |")
                lines.append("|-----------|--------------------|")
                for item in slowest:
                    name = item["name"]
                    dur = item["duration_sec"]
                    display_name = name[:80] + "..." if len(name) > 80 else name
                    lines.append(f"| {display_name} | {dur:.2f} |")
            else:
                lines.append("\n### 🐢 Top 15 Slowest Tests\nNo duration data available.")

        except Exception as e:
            logger.error(f"Error generating summary: {e}", exc_info=True)
            lines.append("\n## ⚠️ Test Metrics")
            lines.append(f"Error computing metrics: {str(e)}")

        lines.append("\n## 📁 Tables in this ingestion")
        for t in tables_in_db:
            lines.append(f"- `{t}`")

        # Write markdown
        summary_md_path.write_text("\n".join(lines), encoding='utf-8')
        logger.info(f"Markdown summary written to {summary_md_path}")

        # Write JSON summary
        json_data = {
            "build_id": build_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "total_records_ingested": total_rows,
            "metrics": metrics,
            "tables": tables_in_db
        }
        with open(summary_json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON summary written to {summary_json_path}")

    def run_ingestion_from_config(self, config_path: str, build_id: str = None):
        if build_id is None:
            build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        with open(config_path, 'r') as f:
            config = json.load(f)
        for source in config['sources']:
            self.ingest_source(source, build_id)