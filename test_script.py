"""
Read the full ingested test data from a specific build's LanceDB table.
Data folder is expected to be in the current directory.
Usage: python read_build_data.py [build_id]
"""

import sys
from pathlib import Path
import lancedb
import pandas as pd

def list_builds(data_path: Path):
    """Return sorted list of ingestion build folders."""
    builds = []
    for item in data_path.iterdir():
        if item.is_dir() and item.name.startswith("ingestion_"):
            lancedb_path = item / "lancedb"
            if lancedb_path.exists():
                builds.append(item.name)
    return sorted(builds, reverse=True)

def load_build_data(data_path: Path, build_id: str):
    """Load structured_test_results DataFrame for a build."""
    lancedb_path = data_path / build_id / "lancedb"
    if not lancedb_path.exists():
        raise FileNotFoundError(f"Build {build_id} not found at {lancedb_path}")
    db = lancedb.connect(str(lancedb_path))
    if "structured_test_results" not in db.table_names():
        raise ValueError(f"Table 'structured_test_results' missing in build {build_id}")
    table = db.open_table("structured_test_results")
    return table.to_pandas()

def main():
    # Data folder is in the current working directory (dashboard root)
    data_path = Path.cwd() / "data"
    if not data_path.exists():
        print(f"❌ Data folder not found at {data_path}")
        print("Make sure you are running this script from the dashboard root directory.")
        return

    print(f"📁 Data folder: {data_path}")

    builds = list_builds(data_path)
    if not builds:
        print("No ingestion builds found.")
        return

    if len(sys.argv) > 1:
        build_id = sys.argv[1]
        if build_id not in builds:
            print(f"Build '{build_id}' not found. Available builds: {', '.join(builds[:5])}")
            return
    else:
        print("Available builds (most recent first):")
        for i, b in enumerate(builds[:10]):
            print(f"  {i+1}. {b}")
        if len(builds) > 10:
            print(f"  ... and {len(builds)-10} more")
        choice = input("Enter build number or full build_id: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(builds):
                build_id = builds[idx]
            else:
                print("Invalid number")
                return
        else:
            build_id = choice
            if build_id not in builds:
                print(f"Build '{build_id}' not found")
                return

    print(f"\n🔍 Loading build: {build_id}")
    df = load_build_data(data_path, build_id)
    print(f"✅ Loaded {len(df)} test records")
    print(f"📋 Columns: {list(df.columns)}")

    # Show first few rows
    pd.set_option('display.max_colwidth', 60)
    print("\n📊 First 5 test records:\n")
    print(df.head(5).to_string())

    # Quick stats
    print("\n📈 Quick stats:")
    print(f"  - Passed: {(df['status'] == 'passed').sum()}")
    print(f"  - Failed: {(df['status'] == 'failed').sum()}")
    if 'skipped' in df['status'].values:
        print(f"  - Skipped: {(df['status'] == 'skipped').sum()}")
    print(f"  - Average duration: {df['duration_seconds'].mean():.2f}s")

    # Export to CSV for further analysis
    export_csv = data_path / build_id / "exported_tests.csv"
    df.to_csv(export_csv, index=False)
    print(f"\n💾 Full data exported to: {export_csv}")

if __name__ == "__main__":
    main()