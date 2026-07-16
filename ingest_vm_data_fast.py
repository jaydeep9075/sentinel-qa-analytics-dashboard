#!/usr/bin/env python3
"""
Fast ingestion for Allure test data - Python-first, NO embeddings.
Optimized for speed: ~2-3 seconds for 500+ tests.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import duckdb
import lancedb

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from universal_ingester.connectors.allure_connector import AllureConnector


def fast_ingest_allure(allure_path: str) -> bool:
    """Fast ingestion for Allure data - no embeddings, direct LanceDB."""

    print("\n" + "="*70)
    print("⚡ FAST ALLURE INGESTION (Python-only, no AI/embeddings)")
    print("="*70)

    allure_path = Path(allure_path)
    if not allure_path.exists():
        print(f"❌ Path not found: {allure_path}")
        return False

    print(f"\n📁 Source: {allure_path}")

    # Step 1: Extract Allure data
    print("\n⏳ Step 1/3: Extracting Allure data...")
    try:
        connector = AllureConnector(str(allure_path))
        datasets = connector.fetch()
        print(f"✅ Extracted {len(datasets)} datasets")
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return False

    # Step 2: Connect to databases
    print("\n⏳ Step 2/3: Setting up databases...")
    try:
        build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        data_path = Path("./data") / build_id
        data_path.mkdir(parents=True, exist_ok=True)

        lancedb_path = data_path / "lancedb"
        lancedb_path.mkdir(parents=True, exist_ok=True)

        lance_db = lancedb.connect(str(lancedb_path))
        duck_db = duckdb.connect()

        print(f"✅ Databases ready (build_id: {build_id})")
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False

    # Step 3: Ingest data (NO embeddings, NO AI)
    print("\n⏳ Step 3/3: Ingesting data...")
    total_rows = 0

    try:
        for dataset in datasets:
            name = dataset['name']
            data = dataset['data']
            data_type = dataset['type']

            if isinstance(data, pd.DataFrame):
                rows = len(data)
                total_rows += rows

                # Convert build_id if needed
                if 'build_id' not in data.columns:
                    data['build_id'] = build_id

                # Create LanceDB table (NO embeddings)
                table_name = f"structured_{name}"
                if table_name in lance_db.table_names():
                    table = lance_db.open_table(table_name)
                    table.add(data)
                    print(f"  ✅ {name}: +{rows} rows (appended)")
                else:
                    lance_db.create_table(table_name, data)
                    print(f"  ✅ {name}: {rows} rows (created)")

        print(f"\n✅ Total ingested: {total_rows} records")

        # Register with DuckDB for analysis
        print("\n📊 Registering with DuckDB...")
        for dataset in datasets:
            data = dataset['data']
            if isinstance(data, pd.DataFrame):
                name = dataset['name']
                table_name = f"structured_{name}"
                duck_db.register(table_name, data)

        # Show summary
        print("\n📈 Ingestion Summary:")
        print(f"   Build ID: {build_id}")
        print(f"   Total records: {total_rows}")
        print(f"   Database: {lancedb_path}")
        print(f"   ⚡ Speed: Optimized (no embeddings)")

        return True

    except Exception as e:
        print(f"\n❌ Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Try both paths
    paths = [
        Path(__file__).parent / "vm-data.zip",
        Path(__file__).parent / "vm-data",
    ]

    for path in paths:
        if path.exists():
            print(f"Using: {path}")
            success = fast_ingest_allure(str(path))
            sys.exit(0 if success else 1)

    print("❌ No data found. Try:")
    print("  1. Extract vm-data.zip")
    print("  2. Or place vm-data folder in current directory")
    sys.exit(1)
