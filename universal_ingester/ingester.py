import os
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

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
        params = source_config.get('params', {})

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
            connector = AllureConnector(params['directory'])
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
                    'timestamp': datetime.utcnow()
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
        import json
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
                'timestamp': datetime.utcnow()
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
            'ingestion_time': datetime.utcnow(),
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
        """Generate summary.md (human-readable) and summary.json (structured)."""
        import json
        import re
        
        summary_md_path = self.data_base_path / build_id / "summary.md"
        summary_json_path = self.data_base_path / build_id / "summary.json"
        
        # Default metrics structure
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
            f"**Ingested at:** {datetime.utcnow().isoformat()}",
            f"**Total records ingested:** {total_rows}",
            "",
        ]
        
        # Find test results table
        test_table = None
        for table in self.lance_db.table_names():
            if table == "structured_test_results":
                test_table = table
                break
        
        if test_table:
            # Register in DuckDB
            duckdb_tables = [row[0] for row in self.duck_db.execute("SHOW TABLES").fetchall()]
            if test_table not in duckdb_tables:
                df = self.lance_db.open_table(test_table).to_pandas()
                self.duck_db.register(test_table, df)
            
            columns = [col[0] for col in self.duck_db.execute(f"DESCRIBE {test_table}").fetchall()]
            logger.info(f"Table {test_table} columns: {columns}")
            
            if 'tests' in columns:
                try:
                    rows = self.duck_db.execute(f"SELECT tests FROM {test_table} WHERE tests IS NOT NULL").fetchall()
                    all_tests = []
                    for (tests_json,) in rows:
                        if isinstance(tests_json, str):
                            tests_data = json.loads(tests_json)
                        else:
                            tests_data = tests_json
                        if isinstance(tests_data, list):
                            all_tests.extend(tests_data)
                        elif isinstance(tests_data, dict):
                            all_tests.append(tests_data)
                    
                    if all_tests:
                        df_tests = pd.DataFrame(all_tests)
                        logger.info(f"Parsed {len(df_tests)} individual test records")
                        logger.info(f"Columns found: {list(df_tests.columns)}")
                        
                        # Map columns
                        status_col = 'status' if 'status' in df_tests.columns else None
                        test_name_col = 'title' if 'title' in df_tests.columns else None
                        duration_col = 'duration' if 'duration' in df_tests.columns else None
                        error_col = 'error' if 'error' in df_tests.columns else None
                        
                        logger.info(f"Mapped columns - status: {status_col}, test_name: {test_name_col}, duration: {duration_col}, error: {error_col}")
                        
                        if status_col and duration_col and test_name_col:
                            # Parse duration strings (e.g., "43758ms", "88ms", "1.5s")
                            def parse_duration(dur_str):
                                if pd.isna(dur_str) or not isinstance(dur_str, str):
                                    return None
                                # Extract number and unit
                                match = re.match(r'([\d.]+)\s*(ms|s|m|h)?', dur_str.strip())
                                if not match:
                                    return None
                                value = float(match.group(1))
                                unit = match.group(2) or 's'
                                
                                if unit == 'ms':
                                    return value / 1000  # convert to seconds
                                elif unit == 'm':
                                    return value * 60
                                elif unit == 'h':
                                    return value * 3600
                                else:  # seconds or no unit
                                    return value
                            
                            # Apply duration parsing
                            df_tests['duration_seconds'] = df_tests[duration_col].apply(parse_duration)
                            valid_durations = df_tests['duration_seconds'].dropna()
                            logger.info(f"Valid durations found: {len(valid_durations)} out of {len(df_tests)}")
                            
                            if len(valid_durations) > 0:
                                # Calculate metrics
                                total_tests = len(df_tests)
                                passed = df_tests[status_col].astype(str).str.upper().eq('PASSED').sum()
                                failed = df_tests[status_col].astype(str).str.upper().eq('FAILED').sum()
                                pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0.0
                                
                                # Duration stats
                                avg_duration = valid_durations.mean()
                                total_duration = valid_durations.sum()
                                
                                # Top 15 slowest tests - FIXED VERSION
                                df_with_duration = df_tests.copy()
                                df_with_duration['duration_seconds'] = df_tests['duration_seconds']
                                # Filter to only rows with valid durations
                                df_valid = df_with_duration[df_with_duration['duration_seconds'].notna()]
                                # Get top 15
                                df_top_slow = df_valid.nlargest(15, 'duration_seconds')
                                slowest = [
                                    {"name": str(row[test_name_col]), "duration_sec": round(row['duration_seconds'], 2)}
                                    for _, row in df_top_slow.iterrows()
                                ]
                                
                                # Most common error (non-empty)
                                common_error = ""
                                if error_col:
                                    errors = df_tests[error_col].dropna()
                                    # Extract meaningful error messages
                                    error_messages = []
                                    for err in errors:
                                        if isinstance(err, dict):
                                            msg = err.get('message', '') or err.get('stack', '') or str(err)
                                        else:
                                            msg = str(err)
                                        if msg and len(msg) > 5 and msg != '{}':
                                            error_messages.append(msg)
                                    if error_messages:
                                        common_error = pd.Series(error_messages).mode().iloc[0][:200]
                                
                                # Update metrics
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
                                
                                # Build markdown
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
                            else:
                                lines.append("\n## ⚠️ Test Metrics")
                                lines.append("No valid duration values found in the test data.")
                                logger.warning("No valid duration values found")
                        else:
                            lines.append("\n## ⚠️ Test Metrics")
                            lines.append(f"Missing required columns. Status: {status_col}, Duration: {duration_col}, Test Name: {test_name_col}")
                except Exception as e:
                    logger.error(f"Error parsing tests JSON: {e}", exc_info=True)
                    lines.append("\n## ⚠️ Test Metrics")
                    lines.append(f"Could not parse test results. Error: {str(e)}")
            else:
                lines.append("\n## ⚠️ Test Metrics")
                lines.append(f"No 'tests' JSON column found. Available columns: {', '.join(columns)}")
        else:
            lines.append("\n## ⚠️ Test Metrics")
            lines.append("No test results table found.")
        
        lines.append("\n## 📁 Tables in this ingestion")
        for t in self.lance_db.table_names():
            lines.append(f"- `{t}`")
        
        # Write markdown (UTF-8)
        summary_md_path.write_text("\n".join(lines), encoding='utf-8')
        logger.info(f"Markdown summary written to {summary_md_path}")
        
        # Write JSON summary
        json_data = {
            "build_id": build_id,
            "ingested_at": datetime.utcnow().isoformat(),
            "total_records_ingested": total_rows,
            "metrics": metrics,
            "tables": list(self.lance_db.table_names())
        }
        with open(summary_json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON summary written to {summary_json_path}")

    def run_ingestion_from_config(self, config_path: str, build_id: str = None):
        if build_id is None:
            build_id = f"ingestion_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        with open(config_path, 'r') as f:
            config = json.load(f)
        for source in config['sources']:
            self.ingest_source(source, build_id)