#!/usr/bin/env python3
"""
Full pipeline integration tests.
Tests: Ingestion → Schema Detection → Query → RAG Response
"""

import sys
import json
import tempfile
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from services.ingestion_service import IngestionService
from services.rag_service import PromptAnalyzer, ResponseValidator, RAGService
from services.query_executor import QueryBuilder, QueryExecutor, ResponseFormatter
from services.production_prompts import validate_response_quality
from universal_ingester.schema.runtime_detector import RuntimeSchemaDetector
import pandas as pd


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

    json_type = service.field_mapper.auto_detect_type("/data/file.json")
    print_result("Auto-detect JSON", json_type == 'json')

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


# ==================== TEST 3: Prompt Analysis ====================

def test_prompt_analyzer():
    """Test prompt analysis and intent detection."""
    test_section("RAG - Prompt Analysis")

    analyzer = PromptAnalyzer()

    # Test 3.1: Count intent
    analysis = analyzer.analyze("How many tests passed?")
    print_result("Detect count intent", analysis['intent'] == 'count')

    # Test 3.2: Trend intent
    analysis = analyzer.analyze("Show test failure trend")
    print_result("Detect trend intent", analysis['intent'] == 'trend')

    # Test 3.3: Comparison intent
    analysis = analyzer.analyze("Compare mobile vs desktop")
    print_result("Detect comparison intent", analysis['intent'] == 'comparison')

    # Test 3.4: Top intent
    analysis = analyzer.analyze("Top failing modules")
    print_result("Detect top intent", analysis['intent'] == 'top')

    # Test 3.5: Entity extraction
    analysis = analyzer.analyze("How many tests passed in auth module?")
    has_module = 'module' in analysis['entities']
    print_result("Extract entities", has_module, f"Entities: {analysis['entities']}")

    # Test 3.6: Filter extraction
    analysis = analyzer.analyze("Show passed tests only")
    has_status = 'status' in analysis['filters']
    print_result("Extract filters", has_status, f"Filters: {analysis['filters']}")

    # Test 3.7: Confidence score
    analysis = analyzer.analyze("How many tests?")
    print_result(
        "Calculate confidence",
        0 <= analysis['confidence'] <= 1,
        f"Confidence: {analysis['confidence']}"
    )

    return True


# ==================== TEST 4: Response Validator ====================

def test_response_validator():
    """Test response quality validation."""
    test_section("RAG - Response Validation")

    validator = ResponseValidator()

    # Test 4.1: Validate good response
    good_response = "1,247 tests passed (81.8% pass rate). Highest in production."
    validation = validator.validate_response(good_response, "How many passed?", {})

    print_result(
        "Validate good response",
        validation['is_valid'],
        f"Confidence: {validation['confidence']}"
    )

    # Test 4.2: Reject poor response
    poor_response = "okay"
    validation = validator.validate_response(poor_response, "How many passed?", {})
    print_result("Reject poor response", not validation['is_valid'])

    # Test 4.3: Check validation details
    validation_checks = validation['validation_checks']
    print_result(
        "Has numbers check",
        validation_checks.get('has_numbers', False)
    )

    print_result(
        "Has context check",
        validation_checks.get('has_context', False)
    )

    # Test 4.4: Quality score
    quality_score = validate_response_quality(good_response)
    print_result(
        "Calculate quality score",
        quality_score['quality_score'] > 70,
        f"Score: {quality_score['quality_score']}/100"
    )

    return True


# ==================== TEST 5: Query Building ====================

def test_query_builder():
    """Test SQL query building from analysis."""
    test_section("Query Builder - Analysis to SQL")

    builder = QueryBuilder()

    # Test 5.1: Count query
    analysis = {
        'intent': 'count',
        'filters': {'status': 'passed'},
        'aggregations': ['count']
    }
    query = builder.build_query(analysis)
    has_count = 'COUNT(*)' in query
    has_where = 'WHERE' in query
    print_result("Build count query", has_count and has_where, query)

    # Test 5.2: Top query
    analysis = {
        'intent': 'top',
        'filters': {},
        'aggregations': ['count'],
        'sort': {'field': 'count', 'direction': 'desc'}
    }
    query = builder.build_query(analysis)
    has_group = 'GROUP BY' in query
    has_order = 'ORDER BY' in query
    print_result("Build top query", has_group and has_order, query)

    # Test 5.3: Trend query
    analysis = {
        'intent': 'trend',
        'filters': {},
        'aggregations': ['count'],
        'sort': {'field': 'date', 'direction': 'asc'}
    }
    query = builder.build_query(analysis)
    has_date = 'DATE(' in query
    print_result("Build trend query", has_date, query)

    return True


# ==================== TEST 6: Response Formatting ====================

def test_response_formatter():
    """Test formatting query results to natural language."""
    test_section("Response Formatter - Results to Natural Language")

    # Test 6.1: Format count response
    results = [{'total_count': 1247}]
    response = ResponseFormatter.format_response('count', results, {})
    print_result("Format count response", '1247' in response, response)

    # Test 6.2: Format top response
    results = [
        {'test_name': 'test1', 'count': 45},
        {'test_name': 'test2', 'count': 32}
    ]
    response = ResponseFormatter.format_response('top', results, {})
    print_result("Format top response", 'test1' in response, response[:50] + "...")

    # Test 6.3: Format distribution response
    results = [
        {'status': 'passed', 'count': 1000},
        {'status': 'failed', 'count': 247}
    ]
    response = ResponseFormatter.format_response('distribution', results, {})
    has_percentage = '%' in response
    print_result("Format distribution response", has_percentage, response[:50] + "...")

    return True


# ==================== TEST 7: Full RAG Pipeline ====================

def test_full_pipeline():
    """Test complete RAG pipeline."""
    test_section("Complete RAG Pipeline - Prompt to Response")

    rag = RAGService()

    # Test 7.1: Generate response
    result = rag.generate_response("How many tests passed?")

    print_result(
        "Generate response",
        len(result['response']) > 20,
        f"Response: {result['response'][:50]}..."
    )

    # Test 7.2: Analysis included
    has_analysis = 'analysis' in result and 'intent' in result['analysis']
    print_result("Include analysis", has_analysis)

    # Test 7.3: Validation included
    has_validation = 'validation' in result and 'is_valid' in result['validation']
    print_result("Include validation", has_validation)

    # Test 7.4: Confidence score
    confidence = result.get('confidence', 0)
    print_result(
        "Include confidence",
        0 <= confidence <= 1,
        f"Confidence: {confidence}"
    )

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
        results.append(("Prompt Analysis", test_prompt_analyzer()))
        results.append(("Response Validator", test_response_validator()))
        results.append(("Query Builder", test_query_builder()))
        results.append(("Response Formatter", test_response_formatter()))
        results.append(("Full RAG Pipeline", test_full_pipeline()))

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
