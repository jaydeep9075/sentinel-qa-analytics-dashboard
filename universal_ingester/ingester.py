import os
import json
import uuid
import logging
import re
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np
import lancedb
import duckdb

try:
    import litellm
except Exception:
    litellm = None

try:
    # Package-style imports (works when app runs as modules, e.g. python -m services.main)
    from .connectors.file_connector import FileConnector
    from .connectors.db_connector import DBConnector
    from .connectors.api_connector import APIConnector
    from .utils import EmbeddingGenerator
    from .schema.runtime_detector import RuntimeSchemaDetector
except ImportError:
    # Fallback for direct script execution inside universal_ingester folder
    from connectors.file_connector import FileConnector
    from connectors.db_connector import DBConnector
    from connectors.api_connector import APIConnector
    from utils import EmbeddingGenerator
    from schema.runtime_detector import RuntimeSchemaDetector

logger = logging.getLogger(__name__)

class UniversalIngester:
    def __init__(self, data_base_path: str = "../data"):
        self.data_base_path = Path(data_base_path).absolute()
        self.data_base_path.mkdir(parents=True, exist_ok=True)
        self.embedder = EmbeddingGenerator()
        self.schema_detector = RuntimeSchemaDetector()
        self.duck_db = None
        self.lance_db = None
        self.detected_schemas = {}  # Cache schemas per ingestion

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
            try:
                from .connectors.allure_connector import AllureConnector
            except ImportError:
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

    def _flatten_json_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Expand dict-like columns when values are JSON strings/dicts.
        Keeps original columns unless overwritten by flattened fields.
        """
        if df is None or df.empty:
            return df

        out = df.copy()
        object_cols = out.select_dtypes(include=["object"]).columns.tolist()

        for col in object_cols:
            sample = out[col].dropna().head(25)
            if sample.empty:
                continue

            parsed_values = []
            parsed_count = 0
            for val in sample:
                parsed = None
                if isinstance(val, dict):
                    parsed = val
                elif isinstance(val, str):
                    text = val.strip()
                    if text.startswith("{") and text.endswith("}"):
                        try:
                            parsed = json.loads(text)
                        except Exception:
                            parsed = None
                if isinstance(parsed, dict):
                    parsed_count += 1
                    parsed_values.append(parsed)

            if parsed_count < max(3, int(len(sample) * 0.5)):
                continue

            normalized_rows = []
            for v in out[col].tolist():
                if isinstance(v, dict):
                    normalized_rows.append(v)
                elif isinstance(v, str):
                    text = v.strip()
                    if text.startswith("{") and text.endswith("}"):
                        try:
                            normalized_rows.append(json.loads(text))
                        except Exception:
                            normalized_rows.append({})
                    else:
                        normalized_rows.append({})
                else:
                    normalized_rows.append({})

            flat = pd.json_normalize(normalized_rows)
            if flat.empty:
                continue
            flat.columns = [f"{col}.{c}" for c in flat.columns]
            out = pd.concat([out, flat], axis=1)

        return out

    def _normalize_structured_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        out = df.copy()
        if out.empty:
            return out

        # Flatten nested JSON-like columns to improve queryability for arbitrary schemas.
        out = self._flatten_json_column(out)

        # Replace NaN/Inf with None-safe values for storage and downstream parsing.
        out = out.replace({np.nan: None})
        out = out.replace({np.inf: None, -np.inf: None})
        return out

    def _ai_structured_parse(
        self,
        dataset_name: str,
        items: List[Dict[str, Any]],
        source_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """AI parser used when heuristic key-value extraction can't make sense
        of unstructured content. Grounds the LLM in what's actually known
        about the data's origin (source connector type, original file
        extension, a raw text excerpt showing real structure/formatting)
        rather than asking it to guess blind from a bare JSON dump — this
        materially improves parsing accuracy for varied inputs (PDF text
        extracts, log files, freeform notes, CSV-like text, etc.).
        Returns empty DataFrame if AI parsing is unavailable or fails.
        """
        if not items or litellm is None:
            return pd.DataFrame()

        provider = os.getenv("LLM_PROVIDER", "")
        model = os.getenv("LLM_MODEL", "")
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or ""
        )
        api_base = os.getenv("LLM_API_BASE") or os.getenv("OPENAI_API_BASE") or ""

        if not model:
            return pd.DataFrame()
        model_name = model if "/" in model else (f"{provider}/{model}" if provider else model)

        meta = metadata or {}
        file_path = str(meta.get("file_path", "") or "")
        file_ext = Path(file_path).suffix.lower().lstrip(".") if file_path else ""

        sample = items[:25]
        # Show the LLM the actual raw text of a few items (not just a JSON
        # dump) so it can see real structure — delimiters, headers,
        # indentation, key:value lines, etc. — rather than guessing blind.
        raw_text_excerpt = "\n---\n".join(
            str(item.get("text", ""))[:800] for item in sample[:5] if isinstance(item, dict) and item.get("text")
        )

        context_lines = [
            f"Dataset name: {dataset_name}",
            f"Source connector type: {source_type or 'unknown'}",
        ]
        if file_ext:
            context_lines.append(f"Original file extension: .{file_ext}")
        if file_path:
            context_lines.append(f"Original file path: {file_path}")

        prompt = (
            "You are a robust data normalizer. The heuristic key:value parser could not make sense of this "
            "content, so use the context below (data source, file type, raw excerpt) to infer its real structure "
            "and convert the sample input list into a JSON array of flat objects.\n"
            "Preserve information, infer stable column names from the actual content shape, and avoid nested "
            "structures. If the raw excerpt looks like tabular/delimited data, split it into columns accordingly. "
            "If it looks like a report or log, extract the meaningful fields (e.g. names, dates, statuses, "
            "amounts) rather than dumping the whole text into one field.\n"
            "Return ONLY valid JSON array.\n\n"
            + "\n".join(context_lines)
            + f"\n\nRaw content excerpt (for structural context only):\n{raw_text_excerpt[:4000]}\n\n"
            f"Sample input (full items to convert):\n{json.dumps(sample, ensure_ascii=False)[:18000]}"
        )

        try:
            kwargs = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 2000,
            }
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base
            resp = litellm.completion(**kwargs)
            content = resp.choices[0].message.content if resp and resp.choices else ""
            cleaned = re.sub(r"```json\s*|```", "", str(content or ""), flags=re.IGNORECASE).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, list) and parsed:
                norm = []
                for row in parsed:
                    if isinstance(row, dict):
                        norm.append(row)
                return pd.DataFrame(norm)
        except Exception as exc:
            logger.warning(f"AI structured parsing failed for {dataset_name}: {exc}")

        return pd.DataFrame()

    def _infer_structured_rows_from_unstructured(self, data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Heuristic parser that extracts JSON objects embedded in text payloads."""
        if not data:
            return pd.DataFrame()

        rows = []
        for item in data:
            text = str(item.get("text", "") or "").strip()
            if not text:
                continue
            # Try full-text JSON object.
            if text.startswith("{") and text.endswith("}"):
                try:
                    obj = json.loads(text)
                    if isinstance(obj, dict):
                        rows.append(obj)
                        continue
                except Exception:
                    pass

            # Try line-based key:value extraction.
            kv = {}
            for ln in text.splitlines():
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                key = re.sub(r"\s+", "_", k.strip().lower())
                val = v.strip()
                if key and val:
                    kv[key] = val
            if kv:
                rows.append(kv)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _ingest_dataset(self, dataset: Dict[str, Any], source_type: str, build_id: str) -> int:
        name = dataset['name']
        data = dataset['data']
        data_type = dataset['type']
        metadata = dataset.get('metadata', {})
        source_metadata = dict(metadata or {})

        source_id = f"{name}_{build_id}"
        logger.info(f"Ingesting dataset {name} as {data_type} (build {build_id})")

        # Runtime schema detection (NEW)
        schema_info = None
        if data_type == 'structured' and isinstance(data, pd.DataFrame):
            if name not in self.detected_schemas:
                records = data.to_dict('records')[:20]  # Sample for detection
                schema_info = self.schema_detector.detect(
                    records=records,
                    data_context=f"{source_type} {name}"
                )
                self.detected_schemas[name] = schema_info
                logger.info(f"Detected schema for {name}: {len(schema_info.get('fields', {}))} fields, confidence={schema_info.get('confidence', 0)}")
            else:
                schema_info = self.detected_schemas[name]

            if schema_info:
                source_metadata.update({
                    "detected_schema": schema_info,
                    "runtime_detection": True
                })

        if data_type == 'structured':
            df = data.copy()
            df = self._normalize_structured_df(df)
            source_metadata.update({
                "ingested_data_type": "structured",
                "parser_strategy": "native-structured",
                "parser_confidence": 1.0,
                "parsed_rows": int(len(df)),
            })
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

            self._add_schema_profile(name, table_name, df, source_type, build_id)

            docs = self._df_to_documents(df, name, source_id, source_metadata, build_id)
            if docs:
                texts = [doc['text'] for doc in docs]
                embeddings = self.embedder.embed(texts)
                for doc, emb in zip(docs, embeddings):
                    doc['embedding'] = emb
                self._add_documents(docs)

            self._add_source(source_id, source_type, name, len(df), source_metadata, build_id)
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
                    'metadata': json.dumps({**source_metadata, 'index': i}),
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

            # Attempt general-purpose structured parsing from unstructured content.
            heuristic_df = self._infer_structured_rows_from_unstructured(data)
            parse_strategy = "none"
            parser_confidence = 0.15
            if heuristic_df.empty:
                heuristic_df = self._ai_structured_parse(
                    name, data, source_type=source_type, metadata=source_metadata
                )
                if not heuristic_df.empty:
                    parse_strategy = "ai-structured-fallback"
                    parser_confidence = 0.86
            else:
                parse_strategy = "heuristic-kv"
                parser_confidence = 0.72

            if not heuristic_df.empty:
                heuristic_df = self._normalize_structured_df(heuristic_df)
                if 'build_id' not in heuristic_df.columns:
                    heuristic_df['build_id'] = build_id
                ai_table_name = f"structured_{name}_ai_parsed"
                if ai_table_name in self.lance_db.table_names():
                    self.lance_db.open_table(ai_table_name).add(heuristic_df)
                else:
                    self.lance_db.create_table(ai_table_name, heuristic_df)
                logger.info(f"AI/heuristic parsed {len(heuristic_df)} structured rows for {name}")
                self._add_schema_profile(name, ai_table_name, heuristic_df, source_type, build_id)

            source_metadata.update({
                "ingested_data_type": "unstructured",
                "parser_strategy": parse_strategy,
                "parser_confidence": parser_confidence,
                "parsed_rows": int(len(heuristic_df)) if not heuristic_df.empty else 0,
            })

            self._add_source(source_id, source_type, name, len(docs), source_metadata, build_id)
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

    def _build_dataframe_profile(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df is None:
            return {"row_count": 0, "columns": []}

        profile_cols = []
        sample_df = df.head(3).copy()
        for c in sample_df.columns:
            sample_df[c] = sample_df[c].astype(str)
        samples = sample_df.to_dict(orient="records") if not sample_df.empty else []

        row_count = int(len(df))
        for col in df.columns:
            series = df[col]
            nulls = int(series.isna().sum()) if hasattr(series, "isna") else 0
            non_null = max(row_count - nulls, 0)
            non_null_ratio = round((non_null / row_count), 3) if row_count else 0.0
            profile_cols.append({
                "name": str(col),
                "dtype": str(series.dtype),
                "null_count": nulls,
                "non_null_ratio": non_null_ratio,
                "distinct_count": int(series.nunique(dropna=True)) if row_count else 0,
            })

        return {
            "row_count": row_count,
            "column_count": int(len(df.columns)),
            "columns": profile_cols,
            "sample_rows": samples,
        }

    def _add_schema_profile(self, dataset_name: str, table_name: str, df: pd.DataFrame, source_type: str, build_id: str):
        profile = self._build_dataframe_profile(df)
        record = {
            "id": f"schema_{dataset_name}_{uuid.uuid4().hex[:10]}",
            "build_id": build_id,
            "dataset_name": dataset_name,
            "table_name": table_name,
            "source_type": source_type,
            "created_at": datetime.now(timezone.utc),
            "row_count": int(profile.get("row_count", 0)),
            "column_count": int(profile.get("column_count", 0)),
            "profile_json": json.dumps(profile, ensure_ascii=False),
        }
        table = "ingestion_schema_profiles"
        if table in self.lance_db.table_names():
            self.lance_db.open_table(table).add([record])
        else:
            self.lance_db.create_table(table, [record])

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
        if 'ingestion_schema_profiles' in self.lance_db.table_names():
            df_profiles = self.lance_db.open_table('ingestion_schema_profiles').to_pandas()
            self.duck_db.register('ingestion_schema_profiles', df_profiles)
        return self.duck_db

    def _collect_parser_insights(self) -> Dict[str, Any]:
        insights: Dict[str, Any] = {
            "total_sources": 0,
            "strategies": {},
            "avg_confidence": 0.0,
            "ai_fallback_used": 0,
        }
        if not self.lance_db or "sources" not in self.lance_db.table_names():
            return insights

        try:
            df_sources = self.lance_db.open_table("sources").to_pandas()
            if df_sources.empty:
                return insights

            df_sources = df_sources.copy()
            strategies: Dict[str, int] = {}
            confidences: List[float] = []
            ai_count = 0

            for _, row in df_sources.iterrows():
                raw_meta = row.get("metadata", "{}")
                try:
                    meta = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
                except Exception:
                    meta = {}

                strategy = str(meta.get("parser_strategy", "unknown"))
                strategies[strategy] = strategies.get(strategy, 0) + 1

                conf = meta.get("parser_confidence")
                if isinstance(conf, (int, float)):
                    confidences.append(float(conf))
                if strategy == "ai-structured-fallback":
                    ai_count += 1

            insights["total_sources"] = int(len(df_sources))
            insights["strategies"] = strategies
            insights["avg_confidence"] = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
            insights["ai_fallback_used"] = ai_count
            return insights
        except Exception as exc:
            logger.warning(f"Failed to collect parser insights: {exc}")
            return insights

    def _generate_summary(self, build_id: str, total_rows: int):
        """Generate summary.md and summary.json from structured_test_results.
        Handles both old format (JSON 'tests' column) and new normalized format.
        Pass rate calculated as passed/(passed+failed) to match Allure behavior."""
        import json
        import re
        from datetime import datetime, timezone
        import pandas as pd
        import numpy as np

        summary_md_path = self.data_base_path / build_id / "summary.md"
        summary_json_path = self.data_base_path / build_id / "summary.json"

        metrics = {
            "total_tests": 0,
            "executed_tests": 0,
            "skipped_tests": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "module_count": 0,
            "avg_duration_sec": 0.0,
            "total_duration_sec": 0.0,
            "most_common_error": "",
            "slowest_tests": [],
            "modules": {},
            "projects": {}
        }

        lines = [
            f"# Ingestion Summary: {build_id}",
            "",
            f"**Ingested at:** {datetime.now(timezone.utc).isoformat()}",
            f"**Total records ingested:** {total_rows}",
            "",
        ]

        parser_insights = self._collect_parser_insights()

        tables_in_db = self.lance_db.table_names()
        logger.info(f"Tables in DB: {tables_in_db}")

        if "structured_test_results" not in tables_in_db:
            lines.append("## ⚠️ Test Metrics")
            lines.append("No `structured_test_results` table found.")
            lines.append("")
            lines.append("## 🧠 Parser Insights")
            lines.append(f"- Total sources: {parser_insights.get('total_sources', 0)}")
            lines.append(f"- Avg parser confidence: {parser_insights.get('avg_confidence', 0.0)}")
            lines.append(f"- AI fallback used: {parser_insights.get('ai_fallback_used', 0)}")
            summary_md_path.write_text("\n".join(lines), encoding='utf-8')
            with open(summary_json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "build_id": build_id,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "total_records_ingested": total_rows,
                    "metrics": metrics,
                    "tables": tables_in_db,
                    "parser_insights": parser_insights,
                }, f, indent=2, ensure_ascii=False)
            return

        try:
            # Read the entire table into a pandas DataFrame
            df_results = self.lance_db.open_table("structured_test_results").to_pandas()
            logger.info(f"structured_test_results rows: {len(df_results)}")
            logger.info(f"Columns: {list(df_results.columns)}")

            all_tests = []
            
            # Check which format we have
            if 'tests' in df_results.columns:
                # OLD FORMAT: JSON blob in 'tests' column
                logger.info("Using old format: extracting tests from 'tests' JSON column")
                for tests_raw in df_results['tests'].dropna():
                    if isinstance(tests_raw, str):
                        try:
                            tests_data = json.loads(tests_raw)
                        except Exception as e:
                            logger.warning(f"Failed to parse tests JSON: {e}")
                            continue
                    elif isinstance(tests_raw, np.ndarray):
                        tests_data = tests_raw.tolist()
                    else:
                        tests_data = tests_raw

                    if isinstance(tests_data, list):
                        all_tests.extend(tests_data)
                    elif isinstance(tests_data, dict):
                        found = False
                        for key in ['test_cases', 'tests', 'cases', 'results', 'items', 'data']:
                            if key in tests_data and isinstance(tests_data[key], list):
                                all_tests.extend(tests_data[key])
                                found = True
                                break
                        if not found:
                            all_tests.append(tests_data)
            else:
                # NEW FORMAT: normalized columns (one row per test)
                logger.info("Using new normalized format: converting rows to test objects")
                for _, row in df_results.iterrows():
                    test_obj = {}
                    
                    # Map common fields
                    test_obj['full_title'] = row.get('test_name') or row.get('full_name') or row.get('name') or ''
                    test_obj['name'] = row.get('test_name') or row.get('name') or ''
                    test_obj['status'] = row.get('status', '')
                    test_obj['duration'] = row.get('duration', '0ms')
                    test_obj['error'] = row.get('error_message', '')
                    test_obj['spec_file'] = row.get('spec_file', '')
                    test_obj['description'] = row.get('description', '')
                    test_obj['project_name'] = row.get('project_name', 'unknown')
                    test_obj['module_name'] = row.get('module_name', 'unknown')
                    test_obj['platform_type'] = row.get('platform_type', 'desktop')
                    
                    # Handle labels (might be JSON string or dict)
                    labels_val = row.get('labels', {})
                    if isinstance(labels_val, str):
                        try:
                            test_obj['labels'] = json.loads(labels_val)
                        except:
                            test_obj['labels'] = {}
                    else:
                        test_obj['labels'] = labels_val
                    
                    # Handle tags
                    tags_val = row.get('tags', [])
                    if isinstance(tags_val, str):
                        try:
                            test_obj['tags'] = json.loads(tags_val)
                        except:
                            test_obj['tags'] = []
                    else:
                        test_obj['tags'] = tags_val
                    
                    test_obj['uuid'] = row.get('id', '')
                    test_obj['history_id'] = row.get('history_id', '')
                    test_obj['duration_seconds'] = row.get('duration_seconds', 0)
                    
                    all_tests.append(test_obj)

            logger.info(f"Extracted {len(all_tests)} individual test records")

            if not all_tests:
                lines.append("## ⚠️ Test Metrics")
                lines.append("No test records found in table.")
                summary_md_path.write_text("\n".join(lines), encoding='utf-8')
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

            # --- Flexible column detection ---
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
                # If it's already numeric (seconds)
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    val = val.strip().lower()
                    # If it ends with 'ms'
                    if val.endswith('ms'):
                        try:
                            return float(val[:-2]) / 1000.0
                        except:
                            pass
                    # General number with optional unit
                    match = re.match(r'^([\d.]+)\s*(ms|s|m|h)?$', val)
                    if match:
                        num = float(match.group(1))
                        unit = match.group(2) or 's'
                        if unit == 'ms':
                            return num / 1000.0
                        elif unit == 'm':
                            return num * 60.0
                        elif unit == 'h':
                            return num * 3600.0
                        else:
                            return num
                return None

            # Check if duration_seconds already exists (normalized format)
            if 'duration_seconds' in df_tests.columns:
                df_tests['duration_seconds'] = pd.to_numeric(df_tests['duration_seconds'], errors='coerce')
                valid_durations = df_tests['duration_seconds'].dropna()
            else:
                df_tests['duration_seconds'] = df_tests[duration_col].apply(parse_duration)
                valid_durations = df_tests['duration_seconds'].dropna()
            
            logger.info(f"Valid durations: {len(valid_durations)} / {len(df_tests)}")

            # --- Calculate metrics (Allure-style pass rate) ---
            total_tests = len(df_tests)
            status_series = df_tests[status_col].astype(str).str.lower()
            passed = status_series.eq('passed').sum()
            failed = status_series.isin(['failed', 'broken', 'error']).sum()
            skipped = status_series.isin(['skipped', 'pending', 'unknown']).sum()
            executed_tests = passed + failed
            
            # Pass rate based on executed tests only (ignores skipped/pending)
            pass_rate = (passed / executed_tests * 100) if executed_tests > 0 else 0.0

            avg_duration = valid_durations.mean() if len(valid_durations) > 0 else 0.0
            total_duration = valid_durations.sum() if len(valid_durations) > 0 else 0.0

            # Top 15 slowest tests
            slowest = []
            if not df_tests.empty and len(valid_durations) > 0:
                df_valid = df_tests[df_tests['duration_seconds'].notna()].copy()
                if not df_valid.empty:
                    df_top = df_valid.nlargest(15, 'duration_seconds')
                    slowest = [
                        {"name": str(row[test_name_col]), "duration_sec": round(row['duration_seconds'], 2)}
                        for _, row in df_top.iterrows()
                    ]

            # Most common error message (only from failed tests)
            common_error = ""
            if error_col and error_col in df_tests.columns:
                failed_mask = status_series.isin(['failed', 'broken', 'error'])
                errors = df_tests.loc[failed_mask, error_col].dropna()
                error_strings = []
                for err in errors:
                    if isinstance(err, dict):
                        msg = err.get('message', '') or str(err)
                    else:
                        msg = str(err)
                    if msg and msg.strip() and msg != '{}' and msg != 'nan':
                        error_strings.append(msg.strip())
                if error_strings:
                    # Get most common error (truncate for display)
                    common_error = pd.Series(error_strings).mode().iloc[0][:200]

            metrics = {
                "total_tests": int(total_tests),
                "executed_tests": int(executed_tests),
                "skipped_tests": int(skipped),
                "passed": int(passed),
                "failed": int(failed),
                "pass_rate": round(pass_rate, 2),
                "module_count": 0,
                "avg_duration_sec": round(avg_duration, 2),
                "total_duration_sec": round(total_duration, 2),
                "most_common_error": common_error,
                "slowest_tests": slowest,
                "modules": {},
                "projects": {}
            }

            module_metrics = {}
            if "structured_test_module_metrics" in tables_in_db:
                df_module = self.lance_db.open_table("structured_test_module_metrics").to_pandas()
                for _, row in df_module.iterrows():
                    module_name = str(row.get("module_name", "unknown"))
                    if not module_name:
                        module_name = "unknown"
                    module_metrics[module_name] = {
                        "project_name": str(row.get("project_name", "unknown")),
                        "platform_type": str(row.get("platform_type", "desktop")),
                        "tests_per_module": int(row.get("total_tests", 0) or 0),
                        "passed": int(row.get("passed", 0) or 0),
                        "failed": int(row.get("failed", 0) or 0),
                        "skipped": int(row.get("skipped", 0) or 0),
                        "pending": int(row.get("pending", 0) or 0),
                        "unknown": int(row.get("unknown", 0) or 0),
                        "pass_rate": float(row.get("pass_rate", 0.0) or 0.0),
                        "total_execution_time_sec": float(row.get("total_duration_seconds", 0.0) or 0.0),
                        "avg_execution_time_sec": float(row.get("avg_duration_seconds", 0.0) or 0.0),
                    }
            else:
                # Fallback: compute from test-level table if module table is unavailable.
                if "module_name" in df_tests.columns:
                    if "project_name" not in df_tests.columns:
                        df_tests["project_name"] = "unknown"
                    if "platform_type" not in df_tests.columns:
                        df_tests["platform_type"] = "desktop"
                    df_module = df_tests.copy()
                    df_module["normalized_status"] = status_series
                    grouped_module = df_module.groupby(["module_name", "project_name", "platform_type"], dropna=False)
                    for (module_name, project_name, platform_type), grp in grouped_module:
                        statuses = grp["normalized_status"].astype(str).str.lower()
                        passed_m = int(statuses.eq("passed").sum())
                        failed_m = int(statuses.isin(["failed", "broken", "error"]).sum())
                        skipped_m = int(statuses.isin(["skipped"]).sum())
                        pending_m = int(statuses.isin(["pending"]).sum())
                        unknown_m = int(statuses.isin(["unknown"]).sum())
                        executed_m = passed_m + failed_m
                        total_m = int(len(grp))
                        module_metrics[str(module_name)] = {
                            "project_name": str(project_name),
                            "platform_type": str(platform_type),
                            "tests_per_module": total_m,
                            "passed": passed_m,
                            "failed": failed_m,
                            "skipped": skipped_m,
                            "pending": pending_m,
                            "unknown": unknown_m,
                            "pass_rate": round((passed_m / executed_m * 100), 2) if executed_m else 0.0,
                            "total_execution_time_sec": round(float(grp["duration_seconds"].sum()), 2),
                            "avg_execution_time_sec": round(float(grp["duration_seconds"].mean()), 2) if total_m else 0.0,
                        }

            project_metrics = {}
            if "structured_test_project_metrics" in tables_in_db:
                df_project = self.lance_db.open_table("structured_test_project_metrics").to_pandas()
                for _, row in df_project.iterrows():
                    project_name = str(row.get("project_name", "unknown"))
                    key = f"{project_name}:{str(row.get('platform_type', 'desktop'))}"
                    project_metrics[key] = {
                        "project_name": project_name,
                        "platform_type": str(row.get("platform_type", "desktop")),
                        "module_count": int(row.get("module_count", 0) or 0),
                        "total_tests": int(row.get("total_tests", 0) or 0),
                        "passed": int(row.get("passed", 0) or 0),
                        "failed": int(row.get("failed", 0) or 0),
                        "skipped": int(row.get("skipped", 0) or 0),
                        "pass_rate": float(row.get("pass_rate", 0.0) or 0.0),
                        "total_execution_time_sec": float(row.get("total_duration_seconds", 0.0) or 0.0),
                    }

            metrics["modules"] = module_metrics
            metrics["projects"] = project_metrics
            metrics["module_count"] = len(module_metrics)

            # Build markdown summary
            lines.append("## 📊 Test Metrics")
            lines.append(f"- **Total number of tests:** {total_tests}")
            lines.append(f"- **Executed tests:** {executed_tests} (passed + failed)")
            lines.append(f"- **Skipped/Pending tests:** {skipped}")
            lines.append(f"- **Passed tests:** {passed}")
            lines.append(f"- **Failed tests:** {failed}")
            lines.append(f"- **Pass rate (executed only):** {pass_rate:.2f}%")
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
            "tables": tables_in_db,
            "parser_insights": parser_insights,
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