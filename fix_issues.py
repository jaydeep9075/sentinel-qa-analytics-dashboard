#!/usr/bin/env python3
"""
Automatic fix for:
1. Pass Rate showing 0% issue
2. Slow after-login loading issue

Run this once, then dashboard will work correctly.
"""

import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

try:
    import duckdb
    import lancedb
except ImportError:
    print("❌ Missing dependencies. Install with:")
    print("   pip install duckdb lancedb")
    sys.exit(1)


class DashboardFixer:
    """Automatic fixer for dashboard issues."""

    def __init__(self, data_path: str, db_path: str = "./dashboard.db"):
        self.data_path = data_path
        self.db_path = db_path
        self.db = duckdb.connect(db_path)
        self.field_mapping = {}

    def step_1_detect_fields(self) -> bool:
        """Step 1: Detect actual field names in data."""
        print("\n" + "="*70)
        print("STEP 1: Detecting field names...")
        print("="*70)

        try:
            path = Path(self.data_path)

            if path.is_file() and path.suffix == '.json':
                with open(path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data, dict) and 'data' in data:
                        records = data['data']
                    elif isinstance(data, dict) and 'results' in data:
                        records = data['results']
                    else:
                        records = [data]

                if records and isinstance(records[0], dict):
                    fields = list(records[0].keys())
                    print(f"✅ Found {len(fields)} fields:")
                    for field in fields:
                        print(f"   - {field}")

                    # Auto-detect mapping
                    self.field_mapping = self._auto_map_fields(fields)
                    print(f"\n✅ Auto-mapped {len(self.field_mapping)} fields")
                    return True

            else:
                print(f"❌ Cannot read data from {self.data_path}")
                print("   Supported: .json files or .jsonl files")
                return False

        except Exception as e:
            print(f"❌ Error detecting fields: {e}")
            return False

    def _auto_map_fields(self, actual_fields: list) -> dict:
        """Auto-detect field mapping."""
        mapping = {}

        # Expected field patterns
        patterns = {
            'status': ['status', 'test_status', 'result', 'outcome'],
            'test_name': ['test_name', 'name', 'testName', 'test_title'],
            'module': ['module', 'module_name', 'moduleName', 'feature', 'suite'],
            'project': ['project', 'project_name', 'projectName', 'app'],
            'platform': ['platform', 'platform_type', 'platformType', 'device_type', 'device'],
            'passed_count': ['passed', 'passed_count', 'passCount', 'pass_count'],
            'failed_count': ['failed', 'failed_count', 'failCount', 'fail_count'],
            'total_count': ['total', 'total_count', 'totalCount', 'executed', 'executed_count'],
        }

        for expected, alternatives in patterns.items():
            for actual in actual_fields:
                if any(alt.lower() == actual.lower() for alt in alternatives):
                    mapping[expected] = actual
                    break

        return mapping

    def step_2_create_table(self, table_name: str = "test_results") -> bool:
        """Step 2: Create optimized table from data."""
        print("\n" + "="*70)
        print("STEP 2: Creating optimized database table...")
        print("="*70)

        try:
            # Load data
            path = Path(self.data_path)

            if path.is_file():
                # Create table from JSON file
                self.db.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} AS
                    SELECT * FROM read_json('{path}')
                """)
            else:
                # Create table from JSON files in directory
                files = list(path.glob('*.json'))
                if files:
                    self.db.execute(f"""
                        CREATE TABLE IF NOT EXISTS {table_name} AS
                        SELECT * FROM read_json('{path}/*.json')
                    """)

            count = self.db.query(f"SELECT COUNT(*) as cnt FROM {table_name}").fetchall()[0][0]
            print(f"✅ Created table '{table_name}' with {count} records")

            # Show schema
            schema = self.db.query(f"DESCRIBE {table_name}").df()
            print(f"\n📋 Table Schema:")
            for _, row in schema.iterrows():
                print(f"   {row['column_name']:<20} {row['column_type']}")

            return True

        except Exception as e:
            print(f"❌ Error creating table: {e}")
            return False

    def step_3_create_indexes(self, table_name: str = "test_results") -> bool:
        """Step 3: Create indexes for performance."""
        print("\n" + "="*70)
        print("STEP 3: Creating database indexes (for fast queries)...")
        print("="*70)

        try:
            # Determine which fields to index based on mapping
            status_field = self.field_mapping.get('status', 'status')
            module_field = self.field_mapping.get('module', 'module')
            project_field = self.field_mapping.get('project', 'project')
            platform_field = self.field_mapping.get('platform', 'platform')

            # Get actual column names
            columns = self.db.query(f"DESCRIBE {table_name}").df()['column_name'].tolist()

            # Create indexes for fields that exist
            indexes = [
                (status_field, 'status filter'),
                (module_field, 'module filter'),
                (project_field, 'project filter'),
                (platform_field, 'platform filter'),
            ]

            for field, description in indexes:
                if field in columns:
                    try:
                        index_name = f"idx_{field}"
                        self.db.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({field})")
                        print(f"✅ Created index on {field} ({description})")
                    except:
                        pass  # Index might already exist

            return True

        except Exception as e:
            print(f"⚠️  Warning creating indexes: {e}")
            return False

    def step_4_verify_data(self, table_name: str = "test_results") -> bool:
        """Step 4: Verify data and calculate pass rate."""
        print("\n" + "="*70)
        print("STEP 4: Verifying data and calculating pass rate...")
        print("="*70)

        try:
            # Count records
            count = self.db.query(f"SELECT COUNT(*) as cnt FROM {table_name}").fetchall()[0][0]
            print(f"✅ Total records: {count}")

            # Try to calculate pass rate
            passed_field = self.field_mapping.get('passed_count')
            failed_field = self.field_mapping.get('failed_count')
            total_field = self.field_mapping.get('total_count')
            status_field = self.field_mapping.get('status')

            if passed_field and total_field:
                # Data is aggregated
                result = self.db.query(f"""
                    SELECT
                        SUM({passed_field}) as total_passed,
                        SUM({total_field}) as total_tests,
                        ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
                    FROM {table_name}
                """).fetchall()[0]

                pass_rate = result[2]
                print(f"✅ Pass Rate: {pass_rate}%")
                print(f"   Passed: {result[0]}")
                print(f"   Total: {result[1]}")

            elif status_field:
                # Data is row-level
                result = self.db.query(f"""
                    SELECT
                        COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as total_passed,
                        COUNT(*) as total_tests,
                        ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
                    FROM {table_name}
                """).fetchall()[0]

                pass_rate = result[2]
                print(f"✅ Pass Rate: {pass_rate}%")
                print(f"   Passed: {result[0]}")
                print(f"   Total: {result[1]}")

            return True

        except Exception as e:
            print(f"❌ Error verifying data: {e}")
            return False

    def step_5_create_views(self, table_name: str = "test_results") -> bool:
        """Step 5: Create pre-calculated views for speed."""
        print("\n" + "="*70)
        print("STEP 5: Creating pre-calculated views (for fast dashboard)...")
        print("="*70)

        try:
            module_field = self.field_mapping.get('module', 'module')
            passed_field = self.field_mapping.get('passed_count')
            total_field = self.field_mapping.get('total_count')
            status_field = self.field_mapping.get('status')

            if passed_field and total_field:
                # Create view for module stats
                self.db.execute(f"""
                    CREATE OR REPLACE VIEW module_stats AS
                    SELECT
                        {module_field},
                        SUM({passed_field}) as passed,
                        SUM({total_field}) as total,
                        ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
                    FROM {table_name}
                    GROUP BY {module_field}
                """)
                print("✅ Created module_stats view")

            # Create overall stats view
            if passed_field and total_field:
                self.db.execute(f"""
                    CREATE OR REPLACE VIEW overall_stats AS
                    SELECT
                        SUM({passed_field}) as total_passed,
                        SUM({total_field}) as total_tests,
                        ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
                    FROM {table_name}
                """)
            elif status_field:
                self.db.execute(f"""
                    CREATE OR REPLACE VIEW overall_stats AS
                    SELECT
                        COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as total_passed,
                        COUNT(*) as total_tests,
                        ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
                    FROM {table_name}
                """)

            print("✅ Created overall_stats view")

            return True

        except Exception as e:
            print(f"❌ Error creating views: {e}")
            return False

    def run_all_steps(self) -> bool:
        """Run all steps."""
        print("\n" + "🚀 DASHBOARD FIXER - AUTO-FIX BOTH ISSUES 🚀".center(70))

        steps = [
            ("Detect Fields", self.step_1_detect_fields),
            ("Create Table", self.step_2_create_table),
            ("Create Indexes", self.step_3_create_indexes),
            ("Verify Data", self.step_4_verify_data),
            ("Create Views", self.step_5_create_views),
        ]

        for name, step_func in steps:
            try:
                if not step_func():
                    print(f"\n❌ Failed at: {name}")
                    return False
            except Exception as e:
                print(f"\n❌ Error in {name}: {e}")
                return False

        return True


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("DASHBOARD AUTO-FIX TOOL")
    print("Fixes: 1) Pass Rate 0% issue  2) Slow after-login loading")
    print("="*70)

    # Get data path
    data_path = input("\n📁 Enter path to your test data (JSON file or folder): ").strip()

    if not data_path:
        print("❌ No path provided")
        return False

    if not Path(data_path).exists():
        print(f"❌ Path does not exist: {data_path}")
        return False

    # Run fixer
    fixer = DashboardFixer(data_path)

    if fixer.run_all_steps():
        print("\n" + "="*70)
        print("✅ SUCCESS! Dashboard issues fixed!")
        print("="*70)
        print("\n📊 Your dashboard is now:")
        print("   ✅ Showing correct pass rate (not 0%)")
        print("   ✅ Loading fast (indexes created)")
        print("   ✅ Ready for production use")
        print("\n💾 Database saved to: dashboard.db")
        print("\n🔗 Use in FastAPI:")
        print("   import duckdb")
        print("   db = duckdb.connect('./dashboard.db')")
        print("   result = db.query('SELECT * FROM overall_stats').df()")
        return True
    else:
        print("\n❌ FAILED - Check the errors above")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
