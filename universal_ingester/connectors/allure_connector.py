import json
import uuid
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class AllureConnector(BaseConnector):
    def __init__(self, directory: str):
        self.directory = Path(directory)
        if not self.directory.exists():
            raise FileNotFoundError(f"Allure directory not found: {directory}")

    def fetch(self) -> List[Dict[str, Any]]:
        """Parse Allure results and return two datasets: test_results and test_cases."""
        result_files = list(self.directory.glob("*-result.json"))
        if not result_files:
            logger.warning(f"No Allure result files found in {self.directory}")
            return []

        # Prepare rows for test_results
        results_rows = []
        # Collect unique test definitions for test_cases
        test_case_map = {}

        for file_path in result_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract core fields
            test_name = data.get('name', '')
            status = data.get('status', '').lower()
            duration_ms = data.get('stop', 0) - data.get('start', 0) if data.get('stop') and data.get('start') else 0
            error = ''
            if status == 'failed':
                details = data.get('statusDetails', {})
                error = details.get('message', '') or details.get('trace', '')

            labels = data.get('labels', [])
            tags = [l['value'] for l in labels if l.get('name') == 'tag']
            suite = next((l['value'] for l in labels if l.get('name') == 'suite'), 'Unknown')
            # Extract executed_at from start timestamp (milliseconds)
            executed_at = None
            if data.get('start'):
                executed_at = pd.to_datetime(data['start'], unit='ms')

            # Build test execution dict
            test_execution = {
                "full_title": test_name,
                "status": status,
                "duration": duration_ms / 1000.0,          # seconds
                "error": error,
                "spec_file": file_path.name,
                "suite": suite,
                "tags": ','.join(tags),
            }

            # Create a row for test_results (one row per result file)
            results_rows.append({
                "id": str(uuid.uuid4()),
                "project_id": "allure_project",           # static, can be overridden
                "executed_at": executed_at,
                "tests": [test_execution]                 # list with one test
            })

            # Record test case definition (unique by test_name)
            if test_name not in test_case_map:
                test_case_map[test_name] = {
                    "title": test_name,
                    "module_name": suite,
                    "priority": "Medium",                  # default, can be inferred from tags
                    "description": data.get('description', ''),
                }

        # Build test_cases DataFrame
        test_cases_df = pd.DataFrame(list(test_case_map.values()))
        # Build test_results DataFrame
        test_results_df = pd.DataFrame(results_rows)

        logger.info(f"Loaded {len(test_results_df)} test result rows and {len(test_cases_df)} unique test cases")

        return [
            {
                'name': 'test_results',
                'data': test_results_df,
                'type': 'structured',
                'metadata': {'directory': str(self.directory), 'file_count': len(result_files)}
            },
            {
                'name': 'test_cases',
                'data': test_cases_df,
                'type': 'structured',
                'metadata': {'directory': str(self.directory), 'unique_tests': len(test_cases_df)}
            }
        ]