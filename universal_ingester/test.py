# inspect_tidb_tests.py
import sys
from pathlib import Path
import json
import lancedb  # Add this import

# Adjust path if needed
sys.path.insert(0, str(Path(__file__).parent))
from ingester import UniversalIngester

# Create ingester instance (no ingestion, just load existing data)
ingester = UniversalIngester(data_base_path="../data")

# Use the last build_id that had the issue
build_id = "ingestion_20260420_120157"  # from your log

lancedb_path = ingester.data_base_path / build_id / "lancedb"
ingester.lance_db = lancedb.connect(str(lancedb_path))  # Fix: use lancedb.connect()

# Open the structured_test_results table
table = ingester.lance_db.open_table("structured_test_results")
df = table.to_pandas()

print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")

# Check nulls in 'tests' column
null_count = df['tests'].isna().sum()
print(f"Null values in 'tests': {null_count}")

# Sample first 3 non-null values
non_null = df[df['tests'].notna()]
print(f"\nNon-null rows: {len(non_null)}")
print("\nSample values (first 3):")
for i, (idx, row) in enumerate(non_null.head(3).iterrows()):
    tests_val = row['tests']
    print(f"\n--- Row {i+1} (index {idx}) ---")
    print(f"Type: {type(tests_val)}")
    # Show first 500 chars to see structure
    val_str = str(tests_val)[:500]
    print(f"Content preview: {val_str}")
    # If it's a string, try to parse as JSON and show keys if it's a dict
    if isinstance(tests_val, str):
        try:
            parsed = json.loads(tests_val)
            print(f"Parsed type: {type(parsed)}")
            if isinstance(parsed, dict):
                print(f"Dict keys: {list(parsed.keys())}")
            elif isinstance(parsed, list) and len(parsed) > 0:
                print(f"List length: {len(parsed)}")
                print(f"First element type: {type(parsed[0])}")
                if isinstance(parsed[0], dict):
                    print(f"First element keys: {list(parsed[0].keys())}")
        except Exception as e:
            print(f"JSON parse error: {e}")
    elif isinstance(tests_val, dict):
        print(f"Dict keys: {list(tests_val.keys())}")
    elif isinstance(tests_val, list):
        print(f"List length: {len(tests_val)}")
        if len(tests_val) > 0:
            print(f"First element type: {type(tests_val[0])}")
            if isinstance(tests_val[0], dict):
                print(f"First element keys: {list(tests_val[0].keys())}")
    print("-" * 50)