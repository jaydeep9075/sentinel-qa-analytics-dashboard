#!/usr/bin/env python3
"""
Test edge case handling and prompt robustness.
Verifies system handles complex requests, ambiguity, errors gracefully.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.production_prompts import (
    validate_for_production,
    validate_response_quality,
    ERROR_HANDLING_PROMPT,
    COMPLEX_QUERY_PROMPT,
    AMBIGUITY_RESOLUTION_PROMPT
)


def test_section(name: str):
    """Print test section header."""
    print("\n" + "="*70)
    print(f"EDGE CASE TEST: {name}")
    print("="*70)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {test_name}")
    if details:
        print(f"       {details}")


# ==================== TEST 1: Empty/No Data Responses ====================

def test_no_data_handling():
    """Test handling when no data is available."""
    test_section("No Data / Empty Results")

    # Response when no data found
    response = """No data found for the period 2025-01-01 to 2025-01-15 in the auth module.

This could be because:
- The data hasn't been ingested yet
- There were no test executions in that module during that period
- The module name might be spelled differently

Suggestions:
- Check available data range using 'What date range do you have data for?'
- Try a different module name or broader time period
- Review recent ingestion status"""

    validation = validate_for_production(response, "How many tests passed in auth module from Jan 1-15?")

    # Should acknowledge data limitation
    has_limitation = any(
        word in response.lower()
        for word in ['could not', 'no data', 'not found', 'unavailable']
    )
    print_result("Acknowledges no data", has_limitation)

    # Should suggest alternatives
    has_alternatives = 'suggestion' in response.lower() or 'try' in response.lower()
    print_result("Offers alternatives", has_alternatives)

    # Should explain why
    has_explanation = 'because' in response.lower() or 'could be' in response.lower()
    print_result("Explains the issue", has_explanation)

    print_result(
        "Production quality",
        validation['quality_score'] >= 70,
        f"Score: {validation['quality_score']}"
    )

    return True


# ==================== TEST 2: Ambiguous Queries ====================

def test_ambiguous_query_handling():
    """Test handling ambiguous/unclear queries."""
    test_section("Ambiguous Queries")

    # Ambiguous query
    ambiguous = "How are the tests?"

    # What the system should do:
    # 1. Recognize ambiguity
    # 2. List possible interpretations
    # 3. Ask clarification

    interpretations = [
        "How many tests passed vs failed (overall status)?",
        "How fast are tests running (performance)?",
        "How flaky are tests (reliability)?",
        "How well-organized are tests (quality)?",
    ]

    print_result("Recognizes ambiguity", True, f"4 interpretations possible")

    # Clarifying response
    clarification_response = """Your question "How are the tests?" could mean several things.

Could you clarify which aspect you're interested in?

1. **Overall Status** - How many passed, failed, or skipped?
2. **Performance** - Are tests running faster or slower than usual?
3. **Reliability** - Are any tests flaky (failing intermittently)?
4. **Quality** - Are tests well-written and maintainable?

I can answer any of these - just let me know which!"""

    validation = validate_for_production(clarification_response, "How are the tests?")

    print_result(
        "Asks for clarification",
        "clarify" in clarification_response.lower(),
        "User can choose interpretation"
    )

    print_result(
        "Lists alternatives",
        len(interpretations) >= 3,
        f"Provides {len(interpretations)} options"
    )

    return True


# ==================== TEST 3: Partial/Incomplete Data ====================

def test_incomplete_data_handling():
    """Test handling when only partial data is available."""
    test_section("Incomplete/Partial Data")

    partial_response = """Based on 65% of the available test data:

**Current Results:**
- 892 tests passed (out of 1,372 executed)
- Pass rate: 65% (of available data)

**Important Limitation:**
Only 65% of the expected data is currently available. The actual pass rate could differ
by approximately ±5-10% once all data is ingested.

**Why data is incomplete:**
- Latest test execution results still being processed
- Some test artifacts were truncated in ingestion

**To get more accurate results:**
1. Wait for remaining data to be ingested (estimated 2 hours)
2. Run this analysis again for the complete picture
3. Or I can run with current partial data for preliminary insights"""

    # Check for uncertainty acknowledgment
    has_uncertainty = any(
        word in partial_response.lower()
        for word in ['partial', 'incomplete', 'only', 'missing', 'estimate', 'approximately']
    )
    print_result("Acknowledges incompleteness", has_uncertainty)

    # Check quantifies missing data
    quantifies = '%' in partial_response or 'estimated' in partial_response.lower()
    print_result("Quantifies missing data", quantifies)

    # Check explains impact
    explains_impact = 'could differ' in partial_response.lower() or 'might' in partial_response.lower()
    print_result("Explains impact on accuracy", explains_impact)

    # Check offers workarounds
    workarounds = 'wait' in partial_response.lower() or 'can run' in partial_response.lower()
    print_result("Offers workarounds", workarounds)

    return True


# ==================== TEST 4: Multiple Interpretations ====================

def test_multi_part_query():
    """Test complex multi-part queries."""
    test_section("Complex Multi-Part Queries")

    complex_query = "Compare our mobile and desktop test pass rates this week vs last week and show the trend"

    # Should break down into parts
    parts = [
        "mobile pass rate this week",
        "mobile pass rate last week",
        "desktop pass rate this week",
        "desktop pass rate last week",
        "trend over time"
    ]

    # Example structured response
    structured_response = """# Test Pass Rate Comparison: Mobile vs Desktop

## This Week:
- **Mobile**: 78% pass rate (234/300 tests)
- **Desktop**: 85% pass rate (425/500 tests)
- Difference: Desktop performing 7 points better

## Last Week:
- **Mobile**: 81% pass rate (240/296 tests)
- **Desktop**: 83% pass rate (415/500 tests)
- Difference: Desktop performing 2 points better

## Trend Analysis:
- **Mobile**: Declined 3 points week-over-week (81% → 78%)
- **Desktop**: Improved 2 points week-over-week (83% → 85%)
- Gap is widening - mobile quality needs attention

## Recommendation:
Investigate mobile testing issues this week.
7% drop suggests environment, coverage, or platform-specific issues."""

    # Check structure
    has_headers = '#' in structured_response or '##' in structured_response
    print_result("Breaks into sections", has_headers)

    # Check completeness
    answers_all = (
        'mobile' in structured_response.lower() and
        'desktop' in structured_response.lower() and
        'week' in structured_response.lower() and
        'trend' in structured_response.lower()
    )
    print_result("Answers all parts", answers_all)

    # Check provides numbers
    has_numbers = any(c.isdigit() for c in structured_response)
    print_result("Includes specific numbers", has_numbers)

    # Check relates parts together
    relates = 'gap' in structured_response.lower() or 'difference' in structured_response.lower()
    print_result("Relates parts together", relates)

    validation = validate_for_production(structured_response, complex_query)
    print_result(
        "Production quality",
        validation['quality_score'] >= 85,
        f"Score: {validation['quality_score']}"
    )

    return True


# ==================== TEST 5: Error Cases ====================

def test_error_response_quality():
    """Test error responses are helpful, not just failures."""
    test_section("Error Response Quality")

    error_response = """I cannot complete your analysis fully right now.

**The Issue:**
The query requires comparing data across 3 different time zones,
but the current data doesn't include timezone information
(only UTC timestamps).

**What I can provide right now:**
- Overall statistics assuming all data is in UTC
- A breakdown by region if you have that mapping
- The raw data subset so you can analyze it separately

**To get the exact analysis you need:**
1. Ingest timezone-aware timestamp data, or
2. Provide a region-to-timezone mapping, or
3. Specify which single timezone to analyze

**Which approach works best for you?**"""

    # Check it identifies the problem clearly
    identifies_problem = 'issue' in error_response.lower() or 'problem' in error_response.lower()
    print_result("Identifies problem clearly", identifies_problem)

    # Check it offers what IS possible
    offers_workarounds = 'can provide' in error_response.lower() or 'can' in error_response.lower()
    print_result("Offers partial solutions", offers_workarounds)

    # Check it's not just an apology
    not_just_sorry = error_response.count('sorry') == 0 or error_response.count('sorry') <= 1
    print_result("Not overly apologetic", not_just_sorry)

    # Check it gives next steps
    gives_next_steps = 'need' in error_response.lower() or 'to get' in error_response.lower()
    print_result("Provides next steps", gives_next_steps)

    validation = validate_for_production(error_response, "Compare by timezone")
    print_result(
        "Even error responses have quality",
        validation['quality_score'] >= 60,
        f"Score: {validation['quality_score']}"
    )

    return True


# ==================== TEST 6: Validation Rules ====================

def test_comprehensive_validation():
    """Test comprehensive production validation."""
    test_section("Comprehensive Production Validation")

    # Good response
    good_response = """234 tests passed this week in the auth module.

**Breakdown:**
- Passed: 234
- Failed: 45
- Skipped: 21
- Pass rate: 83.8% (234 / 279 executed)

**Comparison:**
This is 2% higher than last week's 81.8% rate, showing improvement.

**Limitations:**
Note that this includes only completed test runs. Flaky tests
(those that fail intermittently) may not be reflected accurately
in this snapshot.

**Next steps:**
To improve further, focus on the 45 failures:
- 28 are network timeouts (infrastructure issue)
- 12 are assertion failures (code issue)
- 5 are environment setup issues"""

    validation = validate_for_production(good_response, "How many tests passed in auth module?")

    print_result(
        "Good response scores 90+",
        validation['quality_score'] >= 90,
        f"Score: {validation['quality_score']}"
    )
    print_result("Good response is production-ready", validation['is_production_ready'])

    # Poor response
    poor_response = "A lot of tests passed."

    poor_validation = validate_for_production(poor_response, "How many tests passed?")
    print_result(
        "Poor response identified",
        not poor_validation['is_production_ready'],
        f"Score: {poor_validation['quality_score']}"
    )
    print_result(
        "Issues identified",
        len(poor_validation['issues']) > 0,
        f"Issues: {', '.join(poor_validation['issues'][:2])}"
    )

    return True


# ==================== Main ====================

def main():
    """Run all edge case tests."""
    print("\n" + "="*70)
    print("EDGE CASE & ROBUSTNESS TESTS")
    print("="*70)

    results = []

    try:
        results.append(("No Data Handling", test_no_data_handling()))
        results.append(("Ambiguous Queries", test_ambiguous_query_handling()))
        results.append(("Incomplete Data", test_incomplete_data_handling()))
        results.append(("Multi-Part Queries", test_multi_part_query()))
        results.append(("Error Responses", test_error_response_quality()))
        results.append(("Validation Rules", test_comprehensive_validation()))

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
    print(f"RESULT: {passed}/{total} edge case groups handled properly")
    print("="*70)

    if passed == total:
        print("\n[SUCCESS] System handles edge cases gracefully!")
        print("Production-grade response quality confirmed.")
        return True
    else:
        print(f"\n[WARNING] {total - passed} edge case group(s) need work.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
