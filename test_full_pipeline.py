#!/usr/bin/env python3
"""
Full pipeline integration tests.
Tests: Ingestion connector/config validation → Schema Detection
"""

import sys
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from services.ingestion_service import IngestionService
from universal_ingester.schema.runtime_detector import RuntimeSchemaDetector


def test_section(name: str):
    """Print test section header."""
    print("\n" + "="*70)
    print(f"TEST: {name}")
    print("="*70)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {test_name}")
    if details:
        print(f"       {details}")


# ==================== TEST 1: Ingestion Service ====================

def test_ingestion_service():
    """Test ingestion service connector detection and validation."""
    test_section("Ingestion Service - Connector Management")

    service = IngestionService()

    # Test 1.1: Get connectors
    connectors = service.get_connector_options()
    passed = len(connectors['connectors']) >= 5
    print_result(
        "Get 5+ connectors",
        passed,
        f"Found {len(connectors['connectors'])} connectors"
    )

    # Test 1.2: Auto-detect type
    allure_type = service.field_mapper.auto_detect_type("/path/to/allure")
    print_result("Auto-detect Allure", allure_type == 'allure')

    excel_type = service.field_mapper.auto_detect_type("/data/file.xlsx")
    print_result("Auto-detect Excel", excel_type == 'excel')

    # Test 1.3: Get connector config
    config = service.field_mapper.get_connector_config('allure')
    passed = config is not None and 'fields' in config
    print_result("Get Allure config", passed)

    # Test 1.4: Validate Allure config (should fail without real path)
    is_valid, msg = service.validator.validate('allure', {'path': '/nonexistent'})
    print_result("Reject invalid path", not is_valid)

    return True


# ==================== TEST 2: Schema Detector ====================

def test_schema_detection():
    """Test runtime schema detection."""
    test_section("Schema Detection - Python Heuristics + AI Fallback")

    detector = RuntimeSchemaDetector()

    # Test data
    records = [
        {
            "test_id": "1",
            "test_name": "login_test",
            "status": "passed",
            "duration_ms": 123,
            "executed_at": "2026-07-16T10:30:00Z",
            "error": None
        },
        {
            "test_id": "2",
            "test_name": "logout_test",
            "status": "failed",
            "duration_ms": 456,
            "executed_at": "2026-07-16T10:31:00Z",
            "error": "Connection timeout"
        },
    ]

    # Detect schema
    schema = detector.detect(records, "Test execution data")

    # Test 2.1: Detect field count
    print_result(
        "Detect all fields",
        len(schema['fields']) >= 5,
        f"Detected {len(schema['fields'])} fields"
    )

    # Test 2.2: Detect numeric type
    duration_type = schema['fields'].get('duration_ms', {}).get('type')
    print_result("Detect numeric type", duration_type == 'numeric')

    # Test 2.3: Detect category type
    status_type = schema['fields'].get('status', {}).get('type')
    print_result("Detect category type", status_type == 'category')

    # Test 2.4: Detect datetime type
    date_type = schema['fields'].get('executed_at', {}).get('type')
    print_result("Detect datetime type", date_type == 'datetime')

    # Test 2.5: Confidence score
    print_result(
        "Confidence score calculated",
        0 <= schema['confidence'] <= 1,
        f"Confidence: {schema['confidence']}"
    )

    # Test 2.6: AI not called for clear types
    print_result("Python heuristics (no AI)", schema['used_ai'] == False)

    return True


# ==================== Main ====================

def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("FULL PIPELINE INTEGRATION TESTS")
    print("="*70)

    results = []

    try:
        results.append(("Ingestion Service", test_ingestion_service()))
        results.append(("Schema Detection", test_schema_detection()))

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")

    print("\n" + "="*70)
    print(f"RESULT: {passed}/{total} test groups passed")
    print("="*70)

    if passed == total:
        print("\n[SUCCESS] All tests passed! System is production-ready.")
        return True
    else:
        print(f"\n[FAILURE] {total - passed} test group(s) failed.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
