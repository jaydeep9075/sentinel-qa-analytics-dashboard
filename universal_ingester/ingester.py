"""Universal ingestion engine.

Connectors return data (raw payloads, DataFrames, text documents, or batch
iterators); everything after that — parsing, normalization, schema
discovery, chunking, embedding decisions, metadata, storage — happens here
in one generalized pipeline:

    connector → parse/normalize → schema detect → dedup/hash → store → report

Strategy order is Python-first, AI-second: deterministic parsing handles
everything it can (native DataFrames, generic JSON normalization, key:value
heuristics), and the LLM is only consulted when deterministic parsing
cannot confidently make sense of the content.

Dataset contract (what a connector's fetch() yields):
    name:      str
    type:      'structured' | 'unstructured' | 'raw'
    data:      DataFrame | list[{'text': ...}] | any parsed payload (raw)
    data_iter: optional generator of DataFrames for streaming large sources
    metadata:  dict
"""

import os
import json
import uuid
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

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
    from .core.normalizer import normalize_payload
    from .core.chunking import chunk_text
    from .core.report import IngestionReport
    from .core.storage import LanceStorage, compute_text_hash
    from .summary import generate_summary
except ImportError:
    # Fallback for direct script execution inside universal_ingester folder
    from connectors.file_connector import FileConnector
    from connectors.db_connector import DBConnector
    from connectors.api_connector import APIConnector
    from utils import EmbeddingGenerator
    from schema.runtime_detector import RuntimeSchemaDetector
    from core.normalizer import normalize_payload
    from core.chunking import chunk_text
    from core.report import IngestionReport
    from core.storage import LanceStorage, compute_text_hash
    from summary import generate_summary

logger = logging.getLogger(__name__)

# Embedding policy: don't blindly embed everything. Structured records are
# already queryable via DuckDB/SQL; embeddings only add value for semantic
# search, and embedding hundreds of thousands of rows is slow and bloats
# storage. "auto" embeds structured rows only up to a size cap; documents
# (real text) are always embedded.
EMBED_STRUCTURED_MODE = os.getenv("INGEST_EMBED_STRUCTURED", "auto").strip().lower()  # auto|always|never
EMBED_MAX_ROWS = int(os.getenv("INGEST_EMBED_MAX_ROWS", "20000"))


class UniversalIngester:
    def __init__(self, data_base_path: str = "../data"):
        self.data_base_path = Path(data_base_path).absolute()
        self.data_base_path.mkdir(parents=True, exist_ok=True)
        self._embedder = None  # lazy: not every ingestion needs embeddings
        self.schema_detector = RuntimeSchemaDetector()
        self.duck_db = None
        self.lance_db = None
        self.storage: Optional[LanceStorage] = None
        self.report: Optional[IngestionReport] = None
        self.detected_schemas = {}  # cache keyed by (build_id, dataset name)

    @property
    def embedder(self) -> EmbeddingGenerator:
        if self._embedder is None:
            self._embedder = EmbeddingGenerator()
        return self._embedder

    # ------------------------------------------------------------------
    # entry points
    # ------------------------------------------------------------------
    def run_ingestion_from_config(self, config_path: str, build_id: str = None):
        if build_id is None:
            build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        with open(config_path, 'r') as f:
            config = json.load(f)
        for source in config['sources']:
            self.ingest_source(source, build_id)

    def ingest_source(self, source_config: Dict[str, Any], build_id: str):
        ingestion_folder = self.data_base_path / build_id
        ingestion_folder.mkdir(exist_ok=True)
        lancedb_path = ingestion_folder / "lancedb"
        lancedb_path.mkdir(exist_ok=True)

        self.lance_db = lancedb.connect(str(lancedb_path))
        self.duck_db = duckdb.connect()
        self.report = IngestionReport(build_id)
        self.storage = LanceStorage(self.lance_db, self.report)

        connector, source_type = self._build_connector(source_config)

        total_rows = 0
        try:
            datasets = connector.fetch()
        except Exception as exc:
            self.report.dataset_failed(source_type, exc)
            datasets = []

        for dataset in datasets:
            name = dataset.get('name', 'unnamed')
            self.report.dataset_started(name, source_type)
            try:
                rows = self._ingest_dataset(dataset, source_type, build_id)
                total_rows += rows
            except Exception as exc:
                # One bad dataset must not abort the run.
                logger.exception("Dataset %s failed", name)
                self.report.dataset_failed(name, exc)

        self.link_to_duckdb()
        self.report.finish()
        self.report.write(ingestion_folder)
        self._generate_summary(build_id, total_rows)
        logger.info(f"Ingestion {build_id} completed. Summary saved.")
        return total_rows

    def _build_connector(self, source_config: Dict[str, Any]):
        source_type = source_config['type']
        # Support both nested 'params' and flat config
        params = source_config.get('params', source_config)
        path = params.get('path') or params.get('directory', '')

        # Auto-detect Allure data
        if source_type == 'file' and path:
            path_str = str(path).lower()
            if (path_str.endswith('.zip') or
                'allure' in path_str or
                any(f in path_str for f in ['result.json', 'container.json'])):
                logger.info(f"Auto-detected Allure data from path: {path}")
                source_type = 'allure'

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
            allure_path = params.get('path') or params.get('directory')
            if not allure_path:
                raise ValueError("Allure source requires 'path' or 'directory' in config")
            connector = AllureConnector(allure_path)
        elif source_type == 'live_run':
            try:
                from .connectors.live_run_connector import LiveRunConnector
            except ImportError:
                from connectors.live_run_connector import LiveRunConnector
            live_run_path = params.get('path')
            if not live_run_path:
                raise ValueError("live_run source requires 'path' in config")
            connector = LiveRunConnector(live_run_path)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
        return connector, source_type

    # ------------------------------------------------------------------
    # dataset dispatch
    # ------------------------------------------------------------------
    def _ingest_dataset(self, dataset: Dict[str, Any], source_type: str, build_id: str) -> int:
        name = dataset['name']
        data_type = dataset.get('type', 'raw')
        metadata = dict(dataset.get('metadata', {}) or {})
        source_id = f"{name}_{build_id}"
        logger.info(f"Ingesting dataset {name} as {data_type} (build {build_id})")

        if dataset.get('data_iter') is not None:
            return self._ingest_structured_stream(name, dataset['data_iter'], metadata, source_type, source_id, build_id)
        if data_type == 'structured':
            return self._ingest_structured(name, dataset['data'], metadata, source_type, source_id, build_id)
        if data_type == 'unstructured':
            return self._ingest_unstructured(name, dataset['data'], metadata, source_type, source_id, build_id)
        if data_type == 'raw':
            return self._ingest_raw(name, dataset['data'], metadata, source_type, source_id, build_id)

        # Unknown type: try to make sense of it as a raw payload rather than
        # failing the whole dataset outright.
        self.report.warn(name, f"Unknown data type '{data_type}', attempting generic normalization")
        return self._ingest_raw(name, dataset['data'], metadata, source_type, source_id, build_id)

    # ------------------------------------------------------------------
    # raw payloads → generic structure normalization (deterministic)
    # ------------------------------------------------------------------
    def _ingest_raw(self, name: str, payload: Any, metadata: dict,
                    source_type: str, source_id: str, build_id: str) -> int:
        normalized = normalize_payload(payload, name)
        if not normalized.tables:
            self.report.warn(name, "Raw payload produced no records")
            self._record_source(source_id, source_type, name, 0, {
                **metadata,
                "ingested_data_type": "raw",
                "parser_strategy": "structure-normalizer",
                "parser_confidence": 0.95,
                "parsed_rows": 0,
            }, build_id)
            return 0

        total = 0
        tables_written = []
        for table_key, df in normalized.tables.items():
            rows = self._store_structured_frame(
                dataset_name=name,
                table_key=table_key,
                df=df,
                metadata=metadata,
                source_type=source_type,
                source_id=source_id,
                build_id=build_id,
            )
            total += rows
            tables_written.append(f"structured_{table_key}")

        source_meta = {
            **metadata,
            "ingested_data_type": "raw",
            "parser_strategy": "structure-normalizer",
            "parser_confidence": 0.95,
            "parsed_rows": total,
            "normalized_tables": tables_written,
            "normalizer_stats": normalized.stats,
        }
        self._record_source(source_id, source_type, name, total, source_meta, build_id)
        self.report.dataset_completed(
            name, rows_stored=total, tables=tables_written,
            parser_strategy="structure-normalizer", parser_confidence=0.95,
        )
        return total

    # ------------------------------------------------------------------
    # structured DataFrames
    # ------------------------------------------------------------------
    def _ingest_structured(self, name: str, df: pd.DataFrame, metadata: dict,
                           source_type: str, source_id: str, build_id: str) -> int:
        if df is None:
            df = pd.DataFrame()
        df = self._flatten_json_column(df)
        # Preserve any original build_id column from the source data.
        if 'build_id' in df.columns:
            if 'original_build_id' not in df.columns:
                df = df.rename(columns={'build_id': 'original_build_id'})
            else:
                df = df.drop(columns=['build_id'])

        rows = self._store_structured_frame(
            dataset_name=name, table_key=name, df=df, metadata=metadata,
            source_type=source_type, source_id=source_id, build_id=build_id,
        )

        source_meta = {
            **metadata,
            "ingested_data_type": "structured",
            "parser_strategy": "native-structured",
            "parser_confidence": 1.0,
            "parsed_rows": rows,
        }
        schema_info = self.detected_schemas.get((build_id, name))
        if schema_info:
            source_meta.update({"detected_schema": schema_info, "runtime_detection": True})

        self._record_source(source_id, source_type, name, rows, source_meta, build_id)
        self.report.dataset_completed(
            name, rows_stored=rows, tables=[f"structured_{name}"],
            parser_strategy="native-structured", parser_confidence=1.0,
        )
        return rows

    def _ingest_structured_stream(self, name: str, batches: Iterable[pd.DataFrame], metadata: dict,
                                  source_type: str, source_id: str, build_id: str) -> int:
        """Streaming ingestion: batches are written as they arrive, so a
        multi-GB CSV/JSONL/DB table never has to fit in memory at once."""
        total = 0
        batch_no = 0
        for batch in batches:
            if batch is None or batch.empty:
                continue
            batch_no += 1
            try:
                batch = self._flatten_json_column(batch)
                if 'build_id' in batch.columns and 'original_build_id' not in batch.columns:
                    batch = batch.rename(columns={'build_id': 'original_build_id'})
                total += self._store_structured_frame(
                    dataset_name=name, table_key=name, df=batch, metadata=metadata,
                    source_type=source_type, source_id=source_id, build_id=build_id,
                    embed_row_total=total,
                )
            except Exception as exc:
                self.report.record_failures(name, len(batch), f"batch {batch_no} failed: {exc}")
                logger.exception("Batch %d of %s failed", batch_no, name)

        source_meta = {
            **metadata,
            "ingested_data_type": "structured",
            "parser_strategy": "native-structured-stream",
            "parser_confidence": 1.0,
            "parsed_rows": total,
            "batches": batch_no,
        }
        self._record_source(source_id, source_type, name, total, source_meta, build_id)
        self.report.dataset_completed(
            name, rows_stored=total, tables=[f"structured_{name}"],
            parser_strategy="native-structured-stream", parser_confidence=1.0,
        )
        return total

    def _store_structured_frame(self, dataset_name: str, table_key: str, df: pd.DataFrame,
                                metadata: dict, source_type: str, source_id: str, build_id: str,
                                embed_row_total: int = 0) -> int:
        """Shared structured path: schema detection, storage, profiling,
        conditional embedding."""
        if df is None or df.empty:
            return 0

        # Runtime schema discovery (deterministic heuristics, AI only for
        # low-confidence fields — handled inside the detector).
        cache_key = (build_id, dataset_name)
        if cache_key not in self.detected_schemas:
            try:
                records = df.head(20).to_dict('records')
                schema_info = self.schema_detector.detect(
                    records=records, data_context=f"{source_type} {dataset_name}"
                )
                self.detected_schemas[cache_key] = schema_info
                logger.info(
                    f"Detected schema for {dataset_name}: "
                    f"{len(schema_info.get('fields', {}))} fields, confidence={schema_info.get('confidence', 0)}"
                )
            except Exception as exc:
                self.report.warn(dataset_name, f"Schema detection failed: {exc}")
                self.detected_schemas[cache_key] = None

        table_name = f"structured_{table_key}"
        stored = self.storage.write_structured(
            table_name, df, build_id=build_id, source_id=source_id, dataset_name=dataset_name
        )
        if stored:
            self._add_schema_profile(dataset_name, table_name, df, source_type, build_id)

        if stored and self._should_embed_structured(embed_row_total + stored):
            docs = self._df_to_documents(df, dataset_name, source_id, metadata, build_id)
            embedded = self._embed_and_store(docs, build_id)
            self.report.dataset_completed(dataset_name, documents_stored=embedded)
        elif stored:
            self.report.warn(
                dataset_name,
                f"Skipped embeddings ({embed_row_total + stored} rows > {EMBED_MAX_ROWS} cap or mode={EMBED_STRUCTURED_MODE}); "
                "structured data remains fully SQL-queryable",
            )
        return stored

    def _should_embed_structured(self, row_count: int) -> bool:
        if EMBED_STRUCTURED_MODE == "never":
            return False
        if EMBED_STRUCTURED_MODE == "always":
            return True
        return row_count <= EMBED_MAX_ROWS

    # ------------------------------------------------------------------
    # unstructured documents
    # ------------------------------------------------------------------
    def _ingest_unstructured(self, name: str, data: List[Dict[str, Any]], metadata: dict,
                             source_type: str, source_id: str, build_id: str) -> int:
        docs = []
        for i, item in enumerate(data):
            text = str(item.get('text', '') or '')
            if not text.strip():
                continue
            parent_id = f"{name}_{i}_{uuid.uuid4().hex[:8]}"
            item_meta = {k: v for k, v in item.items() if k != 'text'}
            for chunk in chunk_text(text):
                docs.append({
                    'id': f"{parent_id}_c{chunk['chunk_index']}",
                    'text': chunk['text'],
                    'metadata': json.dumps({**metadata, **item_meta, 'index': i}),
                    'source_id': source_id,
                    'build_id': build_id,
                    'timestamp': datetime.now(timezone.utc),
                    'parent_id': parent_id,
                    'chunk_index': chunk['chunk_index'],
                    'chunk_count': chunk['chunk_count'],
                    'doc_type': str(metadata.get('doc_type', source_type or 'document')),
                    'content_hash': compute_text_hash(chunk['text']),
                })

        embedded = self._embed_and_store(docs, build_id)

        # Python-first structured extraction; AI only if heuristics fail.
        heuristic_df = self._infer_structured_rows_from_unstructured(data)
        parse_strategy = "none"
        parser_confidence = 0.15
        parsed_rows = 0
        if heuristic_df.empty:
            heuristic_df = self._ai_structured_parse(name, data, source_type=source_type, metadata=metadata)
            if not heuristic_df.empty:
                parse_strategy = "ai-structured-fallback"
                parser_confidence = 0.86
        else:
            parse_strategy = "heuristic-kv"
            parser_confidence = 0.72

        ai_tables = []
        if not heuristic_df.empty:
            table_key = f"{name}_ai_parsed"
            parsed_rows = self.storage.write_structured(
                f"structured_{table_key}", heuristic_df,
                build_id=build_id, source_id=source_id, dataset_name=name,
            )
            if parsed_rows:
                ai_tables.append(f"structured_{table_key}")
                self._add_schema_profile(name, f"structured_{table_key}", heuristic_df, source_type, build_id)
                logger.info(f"{parse_strategy} parsed {parsed_rows} structured rows for {name}")
            if parse_strategy == "ai-structured-fallback" and len(data) > parsed_rows:
                self.report.warn(
                    name,
                    f"AI fallback parsed a sample of {parsed_rows}/{len(data)} items into structured rows; "
                    "full text remains searchable via documents",
                )

        source_meta = {
            **metadata,
            "ingested_data_type": "unstructured",
            "parser_strategy": parse_strategy,
            "parser_confidence": parser_confidence,
            "parsed_rows": parsed_rows,
            "chunk_count": len(docs),
        }
        self._record_source(source_id, source_type, name, len(docs), source_meta, build_id)
        self.report.dataset_completed(
            name, documents_stored=embedded, rows_stored=parsed_rows,
            tables=["documents"] + ai_tables,
            parser_strategy=parse_strategy, parser_confidence=parser_confidence,
        )
        return len(docs)

    def _embed_and_store(self, docs: List[Dict], build_id: str) -> int:
        if not docs:
            return 0
        texts = [doc['text'] for doc in docs]
        embeddings = self.embedder.embed(texts)
        for doc, emb in zip(docs, embeddings):
            doc['embedding'] = emb
        return self.storage.write_documents(docs, build_id)

    # ------------------------------------------------------------------
    # parsing helpers (deterministic first, AI fallback)
    # ------------------------------------------------------------------
    def _flatten_json_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Expand dict-like columns when values are JSON strings/dicts.
        Keeps original columns unless overwritten by flattened fields."""
        if df is None or df.empty:
            return df

        out = df.copy()
        object_cols = out.select_dtypes(include=["object"]).columns.tolist()

        for col in object_cols:
            sample = out[col].dropna().head(25)
            if sample.empty:
                continue

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
            flat.index = out.index
            out = pd.concat([out, flat], axis=1)

        return out

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

            # Try line-based key:value extraction. Require at least two
            # extracted pairs so prose with an incidental colon doesn't
            # produce garbage single-column rows.
            kv = {}
            for ln in text.splitlines():
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                key = re.sub(r"\s+", "_", k.strip().lower())
                val = v.strip()
                if key and val and len(key) <= 64:
                    kv[key] = val
            if len(kv) >= 2:
                rows.append(kv)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

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
        rather than asking it to guess blind from a bare JSON dump.
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
                norm = [row for row in parsed if isinstance(row, dict)]
                return pd.DataFrame(norm)
        except Exception as exc:
            logger.warning(f"AI structured parsing failed for {dataset_name}: {exc}")

        return pd.DataFrame()

    # ------------------------------------------------------------------
    # documents from structured rows (for semantic search)
    # ------------------------------------------------------------------
    def _df_to_documents(self, df: pd.DataFrame, dataset_name: str, source_id: str,
                         metadata: dict, build_id: str) -> List[Dict]:
        docs = []
        columns = [c for c in df.columns if not c.startswith('_')]
        meta_json = json.dumps({**metadata, 'columns': columns})
        now = datetime.now(timezone.utc)
        # to_dict is dramatically faster than DataFrame.iterrows for wide frames.
        for idx, row in enumerate(df[columns].to_dict(orient="records")):
            parts = []
            for col, val in row.items():
                if isinstance(val, (list, dict, tuple)):
                    val_str = json.dumps(val, default=str)
                else:
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        continue
                    val_str = str(val)
                parts.append(f"{col}: {val_str}")
            text = " | ".join(parts)
            if not text:
                continue
            docs.append({
                'id': f"{dataset_name}_{idx}_{uuid.uuid4().hex[:8]}",
                'text': text,
                'metadata': meta_json,
                'source_id': source_id,
                'build_id': build_id,
                'timestamp': now,
                'parent_id': source_id,
                'chunk_index': 0,
                'chunk_count': 1,
                'doc_type': 'structured_row',
                'content_hash': compute_text_hash(text),
            })
        return docs

    # ------------------------------------------------------------------
    # bookkeeping
    # ------------------------------------------------------------------
    def _record_source(self, source_id: str, source_type: str, source_name: str,
                       row_count: int, metadata: dict, build_id: str):
        self.storage.append_records("sources", [{
            'source_id': source_id,
            'source_type': source_type,
            'source_name': source_name,
            'build_id': build_id,
            'ingestion_time': datetime.now(timezone.utc),
            'row_count': row_count,
            'status': 'success',
            'metadata': json.dumps(metadata, ensure_ascii=False, default=str)
        }])
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

    def _add_schema_profile(self, dataset_name: str, table_name: str, df: pd.DataFrame,
                            source_type: str, build_id: str):
        try:
            profile = self._build_dataframe_profile(df)
            self.storage.append_records("ingestion_schema_profiles", [{
                "id": f"schema_{dataset_name}_{uuid.uuid4().hex[:10]}",
                "build_id": build_id,
                "dataset_name": dataset_name,
                "table_name": table_name,
                "source_type": source_type,
                "created_at": datetime.now(timezone.utc),
                "row_count": int(profile.get("row_count", 0)),
                "column_count": int(profile.get("column_count", 0)),
                "profile_json": json.dumps(profile, ensure_ascii=False, default=str),
            }])
        except Exception as exc:
            self.report.warn(dataset_name, f"Schema profile failed: {exc}")

    # ------------------------------------------------------------------
    # downstream integration
    # ------------------------------------------------------------------
    def link_to_duckdb(self):
        tables = self.lance_db.table_names()
        for t in tables:
            if t.startswith('structured_'):
                df = self.lance_db.open_table(t).to_pandas()
                self.duck_db.register(t, df)
                logger.info(f"Registered {t} in DuckDB")
        for t in ('documents', 'sources', 'ingestion_schema_profiles'):
            if t in tables:
                self.duck_db.register(t, self.lance_db.open_table(t).to_pandas())
        return self.duck_db

    def _generate_summary(self, build_id: str, total_rows: int):
        report_dict = self.report.to_dict() if self.report else None
        generate_summary(self.lance_db, self.data_base_path, build_id, total_rows, report_dict)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Env first so the container can point at the mounted state directory
    # (/app/state/config2.json); the repo-relative path stays the default for
    # a plain `python ingester.py` from a checkout.
    config_file = Path(
        os.getenv("SENTINEL_CONFIG2_PATH") or (Path(__file__).parent.parent / "config2.json")
    )
    if config_file.exists():
        with open(config_file, 'r') as f:
            cfg = json.load(f)
        base_path = cfg.get("output", {}).get("base_path", "../data")
        UniversalIngester(data_base_path=base_path).run_ingestion_from_config(str(config_file))
    else:
        print(f"No config found at {config_file}")
