# connectors/db_connector.py
from sqlalchemy import create_engine, inspect, text
import pandas as pd
from typing import List, Dict, Any, Optional
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

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

    def fetch(self) -> List[Dict[str, Any]]:
        """Fetch each table as a structured dataset."""
        # Determine which tables to fetch
        if self.tables is None:
            table_names = self.inspector.get_table_names()
        else:
            table_names = self.tables

        datasets = []
        for table in table_names:
            try:
                logger.info(f"Reading table {table}...")
                df = pd.read_sql_table(table, self.engine)
                datasets.append({
                    'name': table,
                    'data': df,
                    'type': 'structured',
                    'metadata': {'table': table, 'rows': len(df)}
                })
            except Exception as e:
                logger.error(f"Error reading {table}: {e}")
        return datasets