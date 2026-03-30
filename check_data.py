import lancedb
import duckdb
import pandas as pd
import json
import os

DB_PATH = "./sentinel_data"

print("=" * 80)
print("🔍 LANCE DB DIAGNOSTIC – FULL DATA INSPECTION")
print("=" * 80)

# Connect to LanceDB
db = lancedb.connect(DB_PATH)

# Get list of tables (handles tuple response)
result = db.list_tables()
if hasattr(result, 'tables'):
    tables = result.tables
elif isinstance(result, tuple):
    tables = result[0]
else:
    tables = result

print(f"\n📂 Tables found ({len(tables)}):")
for t in tables:
    try:
        table = db.open_table(t)
        rows = table.count_rows()
        print(f"   • {t}: {rows:,} rows")
    except Exception as e:
        print(f"   • {t}: error - {e}")

# ============================================================
# Detailed inspection of local_test_results
# ============================================================
print("\n" + "=" * 80)
print("📊 Detailed inspection of local_test_results")
print("=" * 80)

if "local_test_results" in tables:
    print("\n1. Raw table structure (first row):")
    try:
        table = db.open_table("local_test_results")
        df_raw = table.to_pandas()
        print(f"   Row count: {len(df_raw):,}")
        print(f"   Columns: {list(df_raw.columns)}")
        print("\n   Sample of raw data (first 2 rows):")
        print(df_raw.head(2).to_string())
    except Exception as e:
        print(f"   Error reading raw table: {e}")

    print("\n2. Flattened test results (nested 'tests' JSON expanded):")
    try:
        # Use DuckDB to query the Lance table (similar to app.py)
        con = duckdb.connect()
        con.execute("INSTALL lance; LOAD lance;")
        lance_file = f"{DB_PATH}/local_test_results.lance"
        if not os.path.exists(lance_file):
            lance_file = f"{DB_PATH}/local_test_results"
            if not os.path.exists(lance_file):
                print("   ❌ local_test_results file not found")
                exit(1)
        df_raw = con.execute(f"SELECT * FROM '{lance_file}'").df()
        con.close()
    except Exception as e:
        print(f"   ❌ DuckDB query failed: {e}")
        exit(1)

    # Flatten manually
    rows = []
    for _, row in df_raw.iterrows():
        tests_json = row.get('tests')
        if isinstance(tests_json, str):
            try:
                tests = json.loads(tests_json)
            except:
                continue
        elif isinstance(tests_json, list):
            tests = tests_json
        else:
            continue

        for test in tests:
            test_name = test.get('full_title', '')
            status = test.get('status', '').lower()
            duration_raw = test.get('duration', '0ms')
            if isinstance(duration_raw, str) and duration_raw.endswith('ms'):
                try:
                    duration = float(duration_raw[:-2]) / 1000.0
                except:
                    duration = 0.0
            else:
                duration = float(duration_raw) if duration_raw else 0.0

            error = test.get('error') or ''
            module = test.get('spec_file', '').split('/')[-1] if test.get('spec_file') else ''

            rows.append({
                'test_name': test_name,
                'status': status,
                'duration': duration,
                'error_message': error,
                'module': module,
                'build_id': row.get('build_id'),
                'executed_at': row.get('executed_at'),
            })

    df_flat = pd.DataFrame(rows)
    print(f"   Total flattened test records: {len(df_flat):,}")
    if not df_flat.empty:
        print(f"   Columns: {list(df_flat.columns)}")
        print("\n   First 5 flattened records:")
        print(df_flat.head(5).to_string())

        print("\n📈 Status distribution:")
        if 'status' in df_flat.columns:
            status_counts = df_flat['status'].value_counts()
            for status, count in status_counts.items():
                print(f"   • {status}: {count}")

        print("\n⏱️ Duration statistics (seconds):")
        if 'duration' in df_flat.columns:
            print(f"   • Mean: {df_flat['duration'].mean():.2f}")
            print(f"   • Max:  {df_flat['duration'].max():.2f}")
            print(f"   • Min:  {df_flat['duration'].min():.2f}")

        print("\n📦 Top 10 modules by test count:")
        if 'module' in df_flat.columns:
            top_modules = df_flat['module'].value_counts().head(10)
            for module, count in top_modules.items():
                print(f"   • {module}: {count}")

        print("\n📝 Sample of failed tests (first 5):")
        if 'status' in df_flat.columns:
            failed = df_flat[df_flat['status'] == 'failed']
            if not failed.empty:
                for _, row in failed.head(5).iterrows():
                    print(f"   - {row['test_name']} (duration {row['duration']:.2f}s)")
            else:
                print("   No failed tests found.")
    else:
        print("   ❌ No data after flattening.")
else:
    print("\n⚠️ 'local_test_results' table not found in the database.")

# ============================================================
# Check other tables for completeness (optional)
# ============================================================
print("\n" + "=" * 80)
print("📋 Quick look at other tables")
print("=" * 80)
for t in tables:
    if t == "local_test_results":
        continue
    try:
        table = db.open_table(t)
        rows = table.count_rows()
        print(f"\n{t} ({rows} rows):")
        if rows > 0:
            df = table.to_pandas()
            print(f"   Columns: {list(df.columns)}")
            print("   First 2 rows:")
            print(df.head(2).to_string())
        else:
            print("   (empty)")
    except Exception as e:
        print(f"   Error: {e}")

print("\n" + "=" * 80)
print("✅ Diagnostic complete.")