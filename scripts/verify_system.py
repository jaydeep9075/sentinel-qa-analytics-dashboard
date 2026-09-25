#!/usr/bin/env python3
"""
Environment sanity check: dependencies, storage engines, backend import, ingester import.

Usage: python scripts/verify_system.py [path/to/allure-results]
"""

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

REQUIRED_PACKAGES = ["fastapi", "duckdb", "lancedb", "pandas", "uvicorn"]


def check_python() -> bool:
    print(f"\n[1] Python {sys.version_info.major}.{sys.version_info.minor}")
    return sys.version_info >= (3, 11)


def check_dependencies() -> bool:
    print("\n[2] Dependencies")
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            print(f"    OK   {pkg}")
        except ImportError:
            print(f"    MISS {pkg}")
            missing.append(pkg)
    if missing:
        print(f"    Install with: pip install {' '.join(missing)}")
        return False
    return True


def check_database() -> bool:
    print("\n[3] Storage engines")
    try:
        import duckdb

        duckdb.connect(":memory:").query("SELECT 1").fetchall()
        print("    OK   DuckDB")
    except Exception as exc:
        print(f"    FAIL DuckDB: {exc}")
        return False

    try:
        import lancedb

        with tempfile.TemporaryDirectory() as tmpdir:
            lancedb.connect(tmpdir)
        print("    OK   LanceDB")
    except Exception as exc:
        print(f"    FAIL LanceDB: {exc}")
        return False

    return True


def check_api_server() -> bool:
    print("\n[4] Backend")
    try:
        from services.main import app  # noqa: F401

        print("    OK   services.main imports")
        return True
    except Exception as exc:
        print(f"    FAIL services.main: {exc}")
        return False


def check_ingestion() -> bool:
    print("\n[5] Ingester")
    try:
        from universal_ingester.connectors.allure_connector import AllureConnector  # noqa: F401

        print("    OK   AllureConnector imports")
        return True
    except Exception as exc:
        print(f"    FAIL AllureConnector: {exc}")
        return False


def check_allure_path(data_path: str) -> bool:
    print(f"\n[6] Data path: {data_path}")
    abs_path = os.path.abspath(data_path.strip('"').strip("'"))

    if not os.path.isdir(abs_path):
        print(f"    FAIL not a directory: {abs_path}")
        parent = os.path.dirname(abs_path)
        if os.path.isdir(parent):
            print(f"    Available in parent: {os.listdir(parent)}")
        return False

    result_files = list(Path(abs_path).glob("**/*-result.json"))
    if result_files:
        print(f"    OK   {len(result_files)} Allure result files")
    else:
        print("    WARN no *-result.json files found")
    return True


def main() -> bool:
    print("\n" + "=" * 70)
    print("TR-INSIGHT - SYSTEM VERIFICATION")
    print("=" * 70)

    checks = [
        ("Python Version", check_python),
        ("Dependencies", check_dependencies),
        ("Storage Engines", check_database),
        ("Backend", check_api_server),
        ("Ingester", check_ingestion),
    ]

    results = []
    for name, check in checks:
        try:
            results.append((name, check()))
        except Exception as exc:
            print(f"\n    FAIL {name}: {exc}")
            results.append((name, False))

    if len(sys.argv) > 1:
        results.append(("Data Path", check_allure_path(sys.argv[1])))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'} - {name}")

    passed = sum(1 for _, ok in results if ok)
    print(f"\nResult: {passed}/{len(results)} checks passed")

    if passed == len(results):
        print("\nAll checks passed. Start the stack with:")
        print("   python -m services.main        # backend on :8000")
        print("   cd frontend && npm run dev     # dashboard on :3000")
        return True

    print("\nSome checks failed. See errors above.")
    return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
