import os
import json
import pandas as pd
import lancedb
from sqlalchemy import create_engine, inspect

class UniversalIngestor:
    def __init__(self, db_uri: str = "./sentinel_data"):
        self.db_uri = db_uri
        # Initialize local storage
        if not os.path.exists(db_uri):
            os.makedirs(db_uri)
        self.db = lancedb.connect(db_uri)

    def _clean_df(self, df: pd.DataFrame):
        """Standardizes columns and converts objects to strings for RAG/LanceDB."""
        df.columns = [c.replace(' ', '_').replace('.', '_').replace('-', '_').lower() for c in df.columns]
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (dict, list)) else str(x))
        
        # Create a RAG context column: Merges all row data into one searchable string
        df['rag_context'] = df.astype(str).apply(lambda x: ' | '.join(x), axis=1)
        return df

    def sync_entire_database(self, connection_url: str):
        """
        ONE-SHOT: Discovers all tables in the DB and pulls all data into LanceDB.
        """
        print(f"📡 Connecting to Source Database...")
        engine = create_engine(connection_url)
        inspector = inspect(engine)
        
        # 1. Automatically find all table names
        tables = inspector.get_table_names()
        print(f"📂 Found {len(tables)} tables: {tables}")

        # 2. Loop through every table and pull 'Whole Data'
        for table_name in tables:
            print(f"📥 Syncing Table: {table_name}...")
            try:
                df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
                self.save_to_lance(df, f"local_{table_name}")
            except Exception as e:
                print(f"⚠️ Could not sync {table_name}: {e}")

    def ingest_from_file(self, file_path: str, table_name: str):
        """Handles local files (CSV, JSON, XML) and prepares them for RAG."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.json':
            df = pd.read_json(file_path)
            if isinstance(df.iloc[0], dict) or isinstance(df.iloc[0], list):
                 df = pd.json_normalize(json.load(open(file_path)))
        elif ext == '.csv':
            df = pd.read_csv(file_path)
        else:
            raise ValueError("Unsupported format")
            
        return self.save_to_lance(df, table_name)

    def save_to_lance(self, df: pd.DataFrame, table_name: str):
        """Saves cleaned, RAG-ready data to the local file system."""
        df = self._clean_df(df)
        tbl = self.db.create_table(table_name, data=df, mode="overwrite")
        print(f"✅ Stored {len(df)} rows in local table: {table_name}")
        return tbl