#!/usr/bin/env python3
"""
Diagnostic tool to analyze actual data structure and find mismatches.
Helps identify why queries return 0% pass rate.
"""

import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataDiagnostic:
    """Diagnose data structure and field mismatches."""

    # Expected field names by the query builder
    EXPECTED_FIELDS = {
        'status': ['status', 'test_status', 'result', 'outcome', 'state'],
        'module': ['module_name', 'module', 'feature', 'suite', 'component'],
        'project': ['project_name', 'project', 'app', 'application'],
        'platform': ['platform_type', 'platform', 'device_type', 'environment'],
        'test_name': ['test_name', 'name', 'test_title', 'test_id'],
        'duration': ['duration_seconds', 'duration', 'execution_time', 'time'],
        'timestamp': ['executed_at', 'timestamp', 'created_at', 'date', 'start_time'],
        'pass_count': ['passed', 'pass_count', 'passed_count'],
        'fail_count': ['failed', 'fail_count', 'failed_count'],
        'total_count': ['total', 'total_count', 'executed', 'executed_count'],
    }

    def __init__(self):
        self.actual_fields: Set[str] = set()
        self.field_samples: Dict[str, List[Any]] = defaultdict(list)
        self.data_records: List[Dict] = []

    def load_data(self, data_path: str) -> bool:
        """Load data from various sources."""
        try:
            path = Path(data_path)

            if path.is_file():
                if path.suffix == '.json':
                    with open(path) as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.data_records = data
                        elif isinstance(data, dict):
                            if 'data' in data:
                                self.data_records = data['data']
                            elif 'results' in data:
                                self.data_records = data['results']
                            elif 'records' in data:
                                self.data_records = data['records']
                            else:
                                self.data_records = [data]

                elif path.suffix == '.jsonl':
                    with open(path) as f:
                        self.data_records = [json.loads(line) for line in f]

            elif path.is_dir():
                # Load all JSON files from directory
                for json_file in path.glob('*.json'):
                    with open(json_file) as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.data_records.extend(data)
                        else:
                            self.data_records.append(data)

            if not self.data_records:
                print(f"[ERROR] No data loaded from {data_path}")
                return False

            self._analyze_fields()
            return True

        except Exception as e:
            print(f"[ERROR] Failed to load data: {e}")
            return False

    def _analyze_fields(self):
        """Analyze actual fields in data."""
        for record in self.data_records[:100]:  # Sample first 100
            if isinstance(record, dict):
                for key, value in record.items():
                    self.actual_fields.add(key)
                    if len(self.field_samples[key]) < 5:
                        self.field_samples[key].append(value)

    def find_field_mapping(self) -> Dict[str, str]:
        """Find mapping between expected fields and actual fields."""
        mapping = {}

        for expected_group, alternatives in self.EXPECTED_FIELDS.items():
            best_match = None
            best_similarity = 0

            for actual_field in self.actual_fields:
                actual_lower = actual_field.lower()

                # Check exact match
                for alt in alternatives:
                    if actual_lower == alt.lower():
                        best_match = actual_field
                        best_similarity = 1.0
                        break

                # Check partial match
                if best_similarity < 1.0:
                    for alt in alternatives:
                        if alt.lower() in actual_lower or actual_lower in alt.lower():
                            similarity = max(
                                len(set(alt.lower()) & set(actual_lower)) / max(len(alt), len(actual_lower)),
                                0.5  # Min similarity
                            )
                            if similarity > best_similarity:
                                best_match = actual_field
                                best_similarity = similarity

            if best_match and best_similarity > 0.5:
                mapping[expected_group] = best_match

        return mapping

    def print_report(self):
        """Print diagnostic report."""
        print("\n" + "="*80)
        print("DATA DIAGNOSTIC REPORT")
        print("="*80)

        print(f"\n📊 DATA OVERVIEW")
        print(f"   Total records: {len(self.data_records)}")
        print(f"   Actual fields found: {len(self.actual_fields)}")

        print(f"\n📋 ACTUAL FIELDS IN DATA")
        for i, field in enumerate(sorted(self.actual_fields), 1):
            samples = self.field_samples[field][:3]
            print(f"   {i:2}. {field:<30} | Samples: {samples}")

        field_mapping = self.find_field_mapping()

        print(f"\n🔄 FIELD MAPPING (Expected ← Actual)")
        print(f"   {'Expected':<20} {'Mapped To':<30} {'Status'}")
        print("   " + "-"*70)

        for expected, actual in field_mapping.items():
            status = "✅ FOUND"
            print(f"   {expected:<20} {actual:<30} {status}")

        missing = set(self.EXPECTED_FIELDS.keys()) - set(field_mapping.keys())
        if missing:
            print(f"\n   ⚠️  MISSING FIELDS:")
            for field in missing:
                print(f"   ❌ {field:<20} (Expected one of: {', '.join(self.EXPECTED_FIELDS[field])})")

        print(f"\n💡 RECOMMENDATIONS")

        if len(field_mapping) < len(self.EXPECTED_FIELDS) * 0.7:
            print("   ⚠️  Low field coverage! Consider:")
            print("      1. Check if data format is correct")
            print("      2. Verify data was ingested properly")
            print("      3. Check data transformation settings")

        if 'pass_count' in field_mapping or 'total_count' in field_mapping:
            print("   ✅ Appears to be aggregated data (pass/fail counts)")
            print("      → Query should use: SELECT pass_count, fail_count FROM data")
        else:
            print("   ✅ Appears to be row-level data (individual test results)")
            print("      → Query should use: SELECT status, COUNT(*) FROM data GROUP BY status")

        print("\n" + "="*80)

        return field_mapping

    def generate_query_template(self, field_mapping: Dict[str, str]) -> str:
        """Generate corrected SQL query template."""

        status_field = field_mapping.get('status', 'status')
        module_field = field_mapping.get('module', 'module_name')
        project_field = field_mapping.get('project', 'project_name')
        platform_field = field_mapping.get('platform', 'platform_type')

        template = f"""
-- CORRECTED QUERY TEMPLATE FOR YOUR DATA
-- Replace {status_field}, {module_field}, {project_field}, {platform_field} with actual fields

-- 1. PASS RATE (Overall)
SELECT
    COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as passed_count,
    COUNT(CASE WHEN {status_field} = 'failed' THEN 1 END) as failed_count,
    COUNT(*) as total_count,
    ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
FROM test_results;

-- 2. PASS RATE BY MODULE
SELECT
    {module_field},
    COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as passed_count,
    COUNT(CASE WHEN {status_field} = 'failed' THEN 1 END) as failed_count,
    COUNT(*) as total_count,
    ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
FROM test_results
GROUP BY {module_field}
ORDER BY pass_rate_pct DESC;

-- 3. PASS RATE BY PROJECT & PLATFORM
SELECT
    {project_field},
    {platform_field},
    COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as passed_count,
    COUNT(CASE WHEN {status_field} = 'failed' THEN 1 END) as failed_count,
    COUNT(*) as total_count,
    ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
FROM test_results
GROUP BY {project_field}, {platform_field}
ORDER BY {project_field}, {platform_field};

-- 4. TOP FAILING TESTS
SELECT
    {module_field},
    COUNT(CASE WHEN {status_field} = 'failed' THEN 1 END) as failure_count
FROM test_results
WHERE {status_field} = 'failed'
GROUP BY {module_field}
ORDER BY failure_count DESC
LIMIT 5;
"""
        return template.strip()


def main():
    """Run diagnostic."""
    print("\n🔍 DATA DIAGNOSTIC TOOL")
    print("="*80)
    print("This tool identifies why your queries return 0% pass rate.")
    print("It finds the actual field names in your data and generates correct queries.\n")

    data_path = input("📁 Enter path to your data (JSON file or folder): ").strip()

    if not data_path:
        print("Using example path: ./data/test_results.json")
        data_path = "./data/test_results.json"

    diagnostic = DataDiagnostic()

    if not diagnostic.load_data(data_path):
        print("\n❌ Could not load data. Check the path and try again.")
        return

    field_mapping = diagnostic.print_report()

    # Generate corrected query
    print("\n" + "="*80)
    print("CORRECTED QUERY TEMPLATES")
    print("="*80)
    query_template = diagnostic.generate_query_template(field_mapping)
    print(query_template)

    print("\n" + "="*80)
    print("✅ Diagnostic complete. Use the corrected queries above.")
    print("="*80)


if __name__ == "__main__":
    main()
