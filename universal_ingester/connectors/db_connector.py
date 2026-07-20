# connectors/db_connector.py
from sqlalchemy import create_engine, inspect
import os
import pandas as pd
from typing import List, Dict, Any, Optional
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

# Tables stream in chunks so a huge table never loads fully in memory.
DB_CHUNK_ROWS = int(os.getenv("INGEST_DB_CHUNK_ROWS", "50000"))


class DBConnector(BaseConnector):
    def __init__(self, connection_string: str, tables: List[str] = None, connect_args: Optional[Dict] = None):
        """
        connection_string: SQLAlchemy connection string
        tables: optional list of tables to fetch; if None, fetch all tables.
        connect_args: additional arguments to pass to create_engine (e.g., for SSL)
        """
        self.engine = create_engine(connection_string, connect_args=connect_args or {})
        self.tables = tables
        self.inspector = inspect(self.engine)

    def _stream_table(self, table: str):
        for chunk in pd.read_sql_table(table, self.engine, chunksize=DB_CHUNK_ROWS):
            yield chunk

    def fetch(self) -> List[Dict[str, Any]]:
        """Expose each table as a streamed structured dataset; the engine
        writes batches as they arrive."""
        if self.tables is None:
            table_names = self.inspector.get_table_names()
        else:
            table_names = self.tables

        datasets = []
        for table in table_names:
            datasets.append({
                'name': table,
                'data': None,
                'data_iter': self._stream_table(table),
                'type': 'structured',
                'metadata': {'table': table, 'streamed': True},
            })
        return datasets
