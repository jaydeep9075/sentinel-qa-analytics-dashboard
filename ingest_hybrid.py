#!/usr/bin/env python3
"""
Hybrid Ingestion - Smart about embeddings:
- Structured data (JSON, CSV, Allure) → NO embeddings (fast)
- Unstructured data (text, logs) → WITH embeddings + AI (smart RAG)

Works for ANY data type automatically!
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import pandas as pd
import duckdb
import lancedb

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from universal_ingester.connectors.allure_connector import AllureConnector
from universal_ingester.utils import EmbeddingGenerator


class HybridIngester:
    """Smart ingester that auto-detects data type and uses embeddings only when needed."""

    def __init__(self):
        self.embedder = EmbeddingGenerator()
        self.lance_db = None
        self.duck_db = None
        self.build_id = None

    def is_structured_data(self, df: pd.DataFrame) -> bool:
        """Detect if data is structured (has clear columns/fields)."""
        if df.empty:
            return False

        # Structured if:
        # 1. Has many columns (implies schema)
        # 2. Consistent column types across rows
        # 3. Not mostly text columns

        num_cols = len(df.columns)
        text_cols = df.select_dtypes(include=['object']).shape[1]
        numeric_cols = df.select_dtypes(include=['number']).shape[1]

        # If mostly numeric/structured columns
        is_structured = (
            num_cols > 3 and  # Has schema
            text_cols < num_cols * 0.8 and  # Not all text
            numeric_cols > 0  # Has some structure
        )

        logger.info(
            f"Data analysis: {num_cols} cols, {text_cols} text, {numeric_cols} numeric "
            f"→ {'STRUCTURED' if is_structured else 'UNSTRUCTURED'}"
        )

        return is_structured

    def ingest_structured(self, name: str, df: pd.DataFrame) -> int:
        """Ingest structured data - NO embeddings, direct to DB."""
        print(f"\n✅ STRUCTURED DATA: {name}")
        print(f"   Strategy: Python-only (no embeddings)")
        print(f"   Speed: ⚡ Fast")

        # Add build_id if needed
        if 'build_id' not in df.columns:
            df['build_id'] = self.build_id

        # Store in LanceDB (no embeddings)
        table_name = f"structured_{name}"
        if table_name in self.lance_db.table_names():
            table = self.lance_db.open_table(table_name)
            table.add(df)
            logger.info(f"Appended {len(df)} rows to {table_name}")
        else:
            self.lance_db.create_table(table_name, df)
            logger.info(f"Created {table_name} with {len(df)} rows")

        # Also register with DuckDB for SQL queries
        self.duck_db.register(table_name, df)
        logger.info(f"Registered {table_name} in DuckDB for SQL queries")

        return len(df)

    def ingest_unstructured(self, name: str, texts: list) -> int:
        """Ingest unstructured data - WITH embeddings for RAG."""
        print(f"\n✅ UNSTRUCTURED DATA: {name}")
        print(f"   Strategy: AI + embeddings (smart RAG)")
        print(f"   Speed: ⚡ Medium (embedding overhead)")

        if not texts:
            logger.warning(f"No text data for {name}")
            return 0

        print(f"   Embedding {len(texts)} documents...")

        # Create documents
        docs = []
        for i, text in enumerate(texts):
            doc = {
                'id': f"{name}_{i}",
                'text': text,
                'build_id': self.build_id,
                'timestamp': datetime.now(timezone.utc),
                'source': name,
            }
            docs.append(doc)

        # Generate embeddings
        try:
            texts_list = [doc['text'] for doc in docs]
            embeddings = self.embedder.embed(texts_list)

            for doc, emb in zip(docs, embeddings):
                doc['embedding'] = emb

            print(f"   ✅ Generated {len(embeddings)} embeddings")
        except Exception as e:
            logger.warning(f"Embedding failed: {e} - storing without embeddings")
            # Continue without embeddings

        # Store in LanceDB
        table_name = f"documents_{name}"
        self.lance_db.create_table(table_name, docs)
        logger.info(f"Created {table_name} with {len(docs)} documents + embeddings")

        return len(docs)

    def ingest_allure(self, path: str) -> int:
        """Ingest Allure test data - structured, so NO embeddings."""
        print(f"\n📊 Allure Test Data (structured)")

        try:
            connector = AllureConnector(path)
            datasets = connector.fetch()

            total_rows = 0
            for dataset in datasets:
                name = dataset['name']
                data = dataset['data']

                if isinstance(data, pd.DataFrame):
                    rows = self.ingest_structured(name, data)
                    total_rows += rows

            return total_rows

        except Exception as e:
            logger.error(f"Allure ingestion failed: {e}")
            raise

    def ingest_any_data(self, path: str, data_type: Optional[str] = None) -> bool:
        """Smart ingestion for ANY data type."""

        print("\n" + "="*70)
        print("🚀 HYBRID INGESTION (Smart embeddings)")
        print("="*70)

        path = Path(path)
        if not path.exists():
            print(f"❌ Path not found: {path}")
            return False

        print(f"\n📁 Source: {path}")
        print(f"📋 Type: {data_type or 'auto-detect'}")

        # Setup databases
        try:
            self.build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            data_path = Path("./data") / self.build_id
            data_path.mkdir(parents=True, exist_ok=True)

            lancedb_path = data_path / "lancedb"
            lancedb_path.mkdir(parents=True, exist_ok=True)

            self.lance_db = lancedb.connect(str(lancedb_path))
            self.duck_db = duckdb.connect()

            print(f"✅ Build ID: {self.build_id}")
        except Exception as e:
            print(f"❌ Setup failed: {e}")
            return False

        # Ingest based on type
        try:
            total_rows = 0

            # Allure test data
            if str(path).endswith(('.zip', 'allure-results')) or data_type == 'allure':
                total_rows = self.ingest_allure(str(path))

            # JSON/CSV files
            elif path.is_file() and path.suffix in ('.json', '.csv'):
                if path.suffix == '.json':
                    with open(path) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        df = pd.DataFrame(data)
                    else:
                        df = pd.DataFrame([data])
                else:  # CSV
                    df = pd.read_csv(path)

                # Auto-detect structure
                if self.is_structured_data(df):
                    total_rows = self.ingest_structured(path.stem, df)
                else:
                    texts = df.iloc[:, 0].astype(str).tolist()  # First column as text
                    total_rows = self.ingest_unstructured(path.stem, texts)

            # Directory with multiple files
            elif path.is_dir():
                for file in path.glob('*.json'):
                    with open(file) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        df = pd.DataFrame(data)
                    else:
                        df = pd.DataFrame([data])

                    if self.is_structured_data(df):
                        total_rows += self.ingest_structured(file.stem, df)
                    else:
                        texts = df.iloc[:, 0].astype(str).tolist()
                        total_rows += self.ingest_unstructured(file.stem, texts)

            # Summary
            print("\n" + "="*70)
            print("✅ INGESTION COMPLETE")
            print("="*70)
            print(f"Build ID: {self.build_id}")
            print(f"Total records: {total_rows}")
            print(f"Database: {lancedb_path}")

            print("\n📊 Query modes enabled:")
            print("   ✅ SQL queries (for structured data)")
            print("   ✅ Vector search + RAG (for unstructured data)")

            return True

        except Exception as e:
            print(f"\n❌ Ingestion failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point."""
    ingester = HybridIngester()

    # Try common paths
    paths = [
        Path(__file__).parent / "vm-data.zip",
        Path(__file__).parent / "vm-data",
        Path(__file__).parent / "data",
    ]

    for path in paths:
        if path.exists():
            logger.info(f"Found data: {path}")
            success = ingester.ingest_any_data(str(path))
            return 0 if success else 1

    print("❌ No data found. Provide path as argument:")
    print(f"   python {Path(__file__).name} /path/to/data")
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ingester = HybridIngester()
        success = ingester.ingest_any_data(sys.argv[1])
        sys.exit(0 if success else 1)
    else:
        sys.exit(main())
