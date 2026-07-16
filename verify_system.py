#!/usr/bin/env python3
"""
System verification script - Check if everything is working correctly.
Run this to diagnose and fix issues.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def check_python():
    """Check Python version."""
    print("\n1️⃣  Checking Python...")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"   ✅ Python {version}")
    return True

def check_dependencies():
    """Check if required packages are installed."""
    print("\n2️⃣  Checking dependencies...")
    required = ['fastapi', 'duckdb', 'lancedb', 'pandas', 'uvicorn']
    missing = []

    for pkg in required:
        try:
            __import__(pkg)
            print(f"   ✅ {pkg}")
        except ImportError:
            print(f"   ❌ {pkg} - MISSING")
            missing.append(pkg)

    if missing:
        print(f"\n   Install missing: pip install {' '.join(missing)}")
        return False
    return True

def check_allure_path(data_path: str):
    """Check if allure path exists and is accessible."""
    print(f"\n3️⃣  Checking data path: {data_path}")

    # Clean up path
    cleaned = data_path.strip('"').strip("'").replace('\\\\', '\\')
    abs_path = os.path.abspath(cleaned)

    print(f"   Cleaned path: {abs_path}")

    if os.path.isdir(abs_path):
        print(f"   ✅ Path exists")

        # Check for Allure files
        result_files = list(Path(abs_path).glob('**/*-result.json'))
        if result_files:
            print(f"   ✅ Found {len(result_files)} Allure result files")
            return True, abs_path
        else:
            print(f"   ⚠️  No Allure result files found (*-result.json)")
            print(f"   Files in directory: {os.listdir(abs_path)[:5]}...")
            return True, abs_path
    else:
        print(f"   ❌ Path does NOT exist: {abs_path}")

        # Try to find it
        print(f"   \n   Searching for similar paths...")
        parent = os.path.dirname(abs_path)
        if os.path.isdir(parent):
            subdirs = os.listdir(parent)
            print(f"   Available in parent: {subdirs}")

        return False, None

def check_database():
    """Check if database connections work."""
    print("\n4️⃣  Checking database connections...")

    try:
        import duckdb
        conn = duckdb.connect(":memory:")
        result = conn.query("SELECT 1").fetchall()
        print(f"   ✅ DuckDB connection works")
    except Exception as e:
        print(f"   ❌ DuckDB error: {e}")
        return False

    try:
        import lancedb
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db = lancedb.connect(tmpdir)
            print(f"   ✅ LanceDB connection works")
    except Exception as e:
        print(f"   ❌ LanceDB error: {e}")
        return False

    return True

def check_api_server():
    """Check if FastAPI server can start."""
    print("\n5️⃣  Checking API server...")

    try:
        from services.main import app
        print(f"   ✅ FastAPI app imports successfully")
        return True
    except Exception as e:
        print(f"   ❌ FastAPI app error: {e}")
        return False

def check_ingestion():
    """Check ingestion pipeline."""
    print("\n6️⃣  Checking ingestion pipeline...")

    try:
        from universal_ingester.connectors.allure_connector import AllureConnector
        print(f"   ✅ AllureConnector imports successfully")
        return True
    except Exception as e:
        print(f"   ❌ AllureConnector error: {e}")
        return False

def main():
    """Run all checks."""
    print("\n" + "="*70)
    print("SENTINEL DASHBOARD - SYSTEM VERIFICATION")
    print("="*70)

    # Run all checks
    checks = [
        ("Python Version", check_python),
        ("Dependencies", check_dependencies),
        ("Database", check_database),
        ("API Server", check_api_server),
        ("Ingestion", check_ingestion),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name}: {e}")
            results.append((name, False))

    # Ask for data path check
    data_path = input("\n📁 Enter path to Allure results (or leave blank to skip): ").strip()
    if data_path:
        path_ok, cleaned = check_allure_path(data_path)
        results.append(("Data Path", path_ok))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\nResult: {passed}/{total} checks passed")

    if passed == total:
        print("\n🎉 All systems operational! You can now:")
        print("   1. Start server: python -m services.main")
        print("   2. Visit: http://localhost:8000/frontend/index.html")
        print("   3. Ingest Allure data via the UI")
        return True
    else:
        print("\n⚠️  Some systems need attention. See errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
