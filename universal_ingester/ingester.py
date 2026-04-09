# ingester.py
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
        summary_path = self.data_base_path / build_id / "summary.md"
        pass_rate = 0.0
        try:
            result = self.duck_db.execute("""
                SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END)*100.0/COUNT(*), 2)
                FROM flattened_tests
            """).fetchone()
            if result and result[0] is not None:
                pass_rate = result[0]
        except:
            pass

        summary = f"""# Ingestion Summary: {build_id}

**Ingested at:** {datetime.utcnow().isoformat()}
**Total records:** {total_rows}
**Pass rate:** {pass_rate}%

## Tables
{chr(10).join([f"- {t}" for t in self.lance_db.table_names()])}
"""
        summary_path.write_text(summary)
        logger.info(f"Summary written to {summary_path}")

    def run_ingestion_from_config(self, config_path: str, build_id: str = None):
        if build_id is None:
            build_id = f"ingestion_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        with open(config_path, 'r') as f:
            config = json.load(f)
        for source in config['sources']:
            self.ingest_source(source, build_id)