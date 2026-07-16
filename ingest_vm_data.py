#!/usr/bin/env python3
"""
Direct ingestion script for vm-data.zip (extracted)
Ingest Allure test data from vm-data folder
"""

import sys
import json
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from universal_ingester.ingester import Ingester
from universal_ingester.connectors.allure_connector import AllureConnector


def ingest_vm_data():
    """Ingest VM data directly."""
    print("\n" + "="*70)
    print("INGESTING VM-DATA (from vm-data.zip)")
    print("="*70)

    # Path to extracted vm-data
    vm_data_path = Path(__file__).parent / "vm-data"

    if not vm_data_path.exists():
        print(f"\n❌ Path not found: {vm_data_path}")
        return False

    print(f"\n📁 Data path: {vm_data_path}")

    # Verify Allure files exist
    result_files = list(vm_data_path.glob("**/*-result.json"))
    print(f"✅ Found {len(result_files)} Allure result files")

    if not result_files:
        print("❌ No Allure result files found!")
        return False

    # Create config
    config = {
        "name": "vm-data-ingestion",
        "sources": [
            {
                "type": "allure",
                "path": str(vm_data_path)
            }
        ],
        "include_quality": True
    }

    print(f"\n📋 Ingestion Config:")
    print(json.dumps(config, indent=2))

    # Create ingester
    try:
        ingester = Ingester(config)
        print(f"\n🚀 Starting ingestion...")

        # Run ingestion
        ingester.run_ingestion()

        print(f"\n✅ Ingestion completed successfully!")
        print(f"   Build ID: {ingester.build_id}")

        return True

    except Exception as e:
        print(f"\n❌ Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = ingest_vm_data()
    sys.exit(0 if success else 1)
