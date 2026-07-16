"""
Adaptive Query Builder - Auto-detects actual field names and builds correct SQL.
Fixes the 0% pass rate issue by mapping to your data structure.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class FieldNameMapper:
    """Maps expected field names to actual field names in data."""

    # Priority order for field detection
    FIELD_ALIASES = {
        'status': {
            'priority': ['status', 'test_status', 'result', 'outcome', 'state', 'result_status'],
            'values': ['passed', 'failed', 'skipped', 'pending', 'broken']
        },
        'test_name': {
            'priority': ['test_name', 'name', 'test_title', 'test_id', 'testName'],
            'values': []
        },
        'module': {
            'priority': ['module_name', 'module', 'feature', 'suite', 'component', 'moduleName'],
            'values': []
        },
        'project': {
            'priority': ['project_name', 'project', 'app', 'application', 'projectName'],
            'values': []
        },
        'platform': {
            'priority': ['platform_type', 'platform', 'device_type', 'environment', 'device'],
            'values': ['desktop', 'mobile', 'web', 'api']
        },
        'duration': {
            'priority': ['duration_seconds', 'duration', 'execution_time', 'time', 'durationMs'],
            'values': []
        },
        'timestamp': {
            'priority': ['executed_at', 'timestamp', 'created_at', 'date', 'start_time', 'executedAt'],
            'values': []
        },
        'passed_count': {
            'priority': ['passed', 'pass_count', 'passed_count', 'passCount'],
            'values': []
        },
        'failed_count': {
            'priority': ['failed', 'fail_count', 'failed_count', 'failCount'],
            'values': []
        },
        'total_count': {
            'priority': ['total', 'total_count', 'executed', 'executed_count', 'totalCount'],
            'values': []
        }
    }

    def __init__(self, actual_fields: List[str]):
        """Initialize with actual fields from data."""
        self.actual_fields = {f.lower(): f for f in actual_fields}  # Case-insensitive map
        self.mapping = self._build_mapping()

    def _build_mapping(self) -> Dict[str, str]:
        """Build mapping from expected to actual field names."""
        mapping = {}

        for expected, aliases in self.FIELD_ALIASES.items():
            # Try to find exact match
            for priority_name in aliases['priority']:
                lower_name = priority_name.lower()
                if lower_name in self.actual_fields:
                    mapping[expected] = self.actual_fields[lower_name]
                    logger.info(f"Mapped '{expected}' to '{mapping[expected]}'")
                    break

            # If not found, skip it (it's optional)
            if expected not in mapping:
                logger.warning(f"Could not find field for '{expected}'")

        return mapping

    def get(self, field_name: str, default: str = None) -> str:
        """Get actual field name for expected field."""
        if field_name in self.mapping:
            return self.mapping[field_name]
        return default or field_name

    def has_field(self, field_name: str) -> bool:
        """Check if field is available."""
        return field_name in self.mapping

    def __str__(self) -> str:
        """Print mapping."""
        return json.dumps(self.mapping, indent=2)


class AdaptiveQueryBuilder:
    """Build SQL queries using actual field names from data."""

    def __init__(self, field_mapper: FieldNameMapper):
        self.mapper = field_mapper

    def build_pass_rate_query(self, table_name: str = "test_results") -> str:
        """Build query to calculate pass rate."""

        # Check if data has aggregated counts (passed/failed columns)
        if self.mapper.has_field('passed_count') and self.mapper.has_field('total_count'):
            # Data is pre-aggregated
            passed_field = self.mapper.get('passed_count')
            total_field = self.mapper.get('total_count')

            return f"""
            SELECT
                SUM({passed_field}) as total_passed,
                SUM({total_field}) as total_tests,
                ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
            FROM {table_name}
            """

        # Data is row-level (individual test results)
        elif self.mapper.has_field('status'):
            status_field = self.mapper.get('status')

            return f"""
            SELECT
                COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as total_passed,
                COUNT(*) as total_tests,
                ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
            FROM {table_name}
            """

        else:
            raise ValueError("Cannot calculate pass rate - no status or count fields found")

    def build_module_pass_rate_query(self, table_name: str = "test_results") -> str:
        """Build query for pass rate by module."""

        module_field = self.mapper.get('module', 'module')

        if self.mapper.has_field('passed_count') and self.mapper.has_field('total_count'):
            # Pre-aggregated data
            passed_field = self.mapper.get('passed_count')
            total_field = self.mapper.get('total_count')

            return f"""
            SELECT
                {module_field},
                SUM({passed_field}) as passed,
                SUM({total_field}) as total,
                ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
            FROM {table_name}
            GROUP BY {module_field}
            ORDER BY pass_rate_pct DESC
            """

        else:
            # Row-level data
            status_field = self.mapper.get('status', 'status')

            return f"""
            SELECT
                {module_field},
                COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as passed,
                COUNT(*) as total,
                ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
            FROM {table_name}
            GROUP BY {module_field}
            ORDER BY pass_rate_pct DESC
            """

    def build_project_platform_pass_rate_query(self, table_name: str = "test_results") -> str:
        """Build query for pass rate by project and platform."""

        project_field = self.mapper.get('project', 'project')
        platform_field = self.mapper.get('platform', 'platform')

        if self.mapper.has_field('passed_count') and self.mapper.has_field('total_count'):
            passed_field = self.mapper.get('passed_count')
            total_field = self.mapper.get('total_count')

            return f"""
            SELECT
                {project_field},
                {platform_field},
                SUM({passed_field}) as passed,
                SUM({total_field}) as total,
                ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
            FROM {table_name}
            GROUP BY {project_field}, {platform_field}
            ORDER BY {project_field}, {platform_field}
            """

        else:
            status_field = self.mapper.get('status', 'status')

            return f"""
            SELECT
                {project_field},
                {platform_field},
                COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as passed,
                COUNT(*) as total,
                ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
            FROM {table_name}
            GROUP BY {project_field}, {platform_field}
            ORDER BY {project_field}, {platform_field}
            """

    def build_top_failing_modules_query(self, table_name: str = "test_results", limit: int = 5) -> str:
        """Build query to find top failing modules."""

        module_field = self.mapper.get('module', 'module')

        if self.mapper.has_field('failed_count'):
            failed_field = self.mapper.get('failed_count')

            return f"""
            SELECT
                {module_field},
                {failed_field} as failure_count
            FROM {table_name}
            WHERE {failed_field} > 0
            ORDER BY failure_count DESC
            LIMIT {limit}
            """

        else:
            status_field = self.mapper.get('status', 'status')

            return f"""
            SELECT
                {module_field},
                COUNT(CASE WHEN {status_field} = 'failed' THEN 1 END) as failure_count
            FROM {table_name}
            WHERE {status_field} = 'failed'
            GROUP BY {module_field}
            ORDER BY failure_count DESC
            LIMIT {limit}
            """

    def build_trend_query(self, table_name: str = "test_results") -> str:
        """Build query for test trends over time."""

        timestamp_field = self.mapper.get('timestamp', 'timestamp')

        if self.mapper.has_field('passed_count') and self.mapper.has_field('total_count'):
            passed_field = self.mapper.get('passed_count')
            total_field = self.mapper.get('total_count')

            return f"""
            SELECT
                DATE({timestamp_field}) as date,
                SUM({passed_field}) as passed,
                SUM({total_field}) as total,
                ROUND(100.0 * SUM({passed_field}) / SUM({total_field}), 2) as pass_rate_pct
            FROM {table_name}
            GROUP BY DATE({timestamp_field})
            ORDER BY date DESC
            """

        else:
            status_field = self.mapper.get('status', 'status')

            return f"""
            SELECT
                DATE({timestamp_field}) as date,
                COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) as passed,
                COUNT(*) as total,
                ROUND(100.0 * COUNT(CASE WHEN {status_field} = 'passed' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
            FROM {table_name}
            GROUP BY DATE({timestamp_field})
            ORDER BY date DESC
            """

    def __str__(self) -> str:
        """String representation."""
        return f"AdaptiveQueryBuilder(fields={list(self.mapper.mapping.keys())})"
