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
    def __init__(self, lancedb_path: str = "./lancedb_data"):
        self.lancedb_path = Path(lancedb_path).absolute()
        self.lancedb_path.mkdir(parents=True, exist_ok=True)
        self.lance_db = lancedb.connect(str(self.lancedb_path))
        self.embedder = EmbeddingGenerator()
        self.duck_db = duckdb.connect()
        # No empty tables; they will be created on first insert

    def ingest_source(self, source_config: Dict[str, Any], build_id: str = None):
        """
        Ingest a source and assign a build_id.
        If no build_id given, generate one from current timestamp.
        """
        if build_id is None:
            build_id = datetime.utcnow().isoformat()
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
            # Allure connector not implemented yet
            raise NotImplementedError("Allure connector not implemented yet")
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

        datasets = connector.fetch()
        for dataset in datasets:
            self._ingest_dataset(dataset, source_type, build_id)

    def _ingest_dataset(self, dataset: Dict[str, Any], source_type: str, build_id: str):
        name = dataset['name']
        data = dataset['data']
        data_type = dataset['type']
        metadata = dataset.get('metadata', {})

        source_id = f"{name}_{build_id}"
        logger.info(f"Ingesting dataset {name} as {data_type} (build {build_id})")

        if data_type == 'structured':
            df = data.copy()
            # Add build_id column if not present
            if 'build_id' not in df.columns:
                df['build_id'] = build_id
            else:
                # If the source already has a build_id, rename it to avoid conflict
                if 'original_build_id' not in df.columns:
                    df = df.rename(columns={'build_id': 'original_build_id'})
                df['build_id'] = build_id

            table_name = f"structured_{name}"

            # If table exists, append; else create
            if table_name in self.lance_db.table_names():
                table = self.lance_db.open_table(table_name)
                # Assume schema is compatible (build_id already present)
                table.add(df)
                logger.info(f"Appended {len(df)} rows to {table_name} (build {build_id})")
            else:
                self.lance_db.create_table(table_name, df)
                logger.info(f"Created new table {table_name} with {len(df)} rows")

            # Create documents from each row
            docs = self._df_to_documents(df, name, source_id, metadata, build_id)
            if docs:
                texts = [doc['text'] for doc in docs]
                embeddings = self.embedder.embed(texts)
                for doc, emb in zip(docs, embeddings):
                    doc['embedding'] = emb
                self._add_documents(docs)

            # Record source (build) metadata
            self._add_source(source_id, source_type, name, len(df), metadata, build_id)

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

        else:
            raise ValueError(f"Unknown data type: {data_type}")

    def _df_to_documents(self, df: pd.DataFrame, dataset_name: str, source_id: str, metadata: dict, build_id: str) -> List[Dict]:
        """Convert each row of a DataFrame into a text document."""
        import json
        docs = []
        for idx, row in df.iterrows():
            parts = []
            for col in df.columns:
                val = row[col]
                # Skip NaN/None for scalar values; handle non-scalar gracefully
                if isinstance(val, (list, dict, tuple)):
                    # Convert to JSON string
                    val_str = json.dumps(val)
                else:
                    # For scalars, check if it's NaN or None
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
            # If table is empty, drop and recreate to avoid schema mismatch
            if table.count_rows() == 0:
                logger.info(f"Dropping empty {table_name} table to recreate with correct schema.")
                self.lance_db.drop_table(table_name)
                self.lance_db.create_table(table_name, docs)
            else:
                # Append to existing table
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
        # Also register documents and sources if needed
        if 'documents' in self.lance_db.table_names():
            df_docs = self.lance_db.open_table('documents').to_pandas()
            self.duck_db.register('documents', df_docs)
        if 'sources' in self.lance_db.table_names():
            df_sources = self.lance_db.open_table('sources').to_pandas()
            self.duck_db.register('sources', df_sources)
        return self.duck_db

    def run_ingestion_from_config(self, config_path: str, build_id: str = None):
        with open(config_path, 'r') as f:
            config = json.load(f)
        for source in config['sources']:
            self.ingest_source(source, build_id)
        self.link_to_duckdb()