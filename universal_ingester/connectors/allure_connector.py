# connectors/allure_connector.py
import json
import os
import glob
import uuid
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime, timezone
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)


class AllureConnector(BaseConnector):
    """
    Connector for Allure test results.
    Produces a single dataset 'test_results' with a 'tests' JSON column,
    exactly matching the TiDB ingestion schema.
    """
    def __init__(self, allure_results_path: str):
        if not allure_results_path:
            raise ValueError("Allure results path is required")
        self.root_path = allure_results_path
        if not os.path.isdir(self.root_path):
            raise ValueError(f"Path does not exist: {self.root_path}")

    def _find_result_files(self) -> List[str]:
        """Find all *-result.json files, supporting nested artifact folders."""
        result_files = []
        # Check if the path itself is an allure-results directory
        if os.path.basename(self.root_path) == "allure-results":
            result_files = glob.glob(os.path.join(self.root_path, "*-result.json"))
            if result_files:
                return result_files

        # Look for artifact_*/allure-results subdirectories
        artifact_pattern = os.path.join(self.root_path, "artifact_*", "allure-results", "*-result.json")
        result_files = glob.glob(artifact_pattern)
        if result_files:
            return result_files

        # Fallback: recursive search for allure-results folders
        for root, dirs, files in os.walk(self.root_path):
            if os.path.basename(root) == "allure-results":
                result_files.extend(glob.glob(os.path.join(root, "*-result.json")))
        return result_files

    def _map_status(self, allure_status: str) -> str:
        """Map Allure status to a consistent value expected by data_loader."""
        status_map = {
            "passed": "passed",
            "failed": "failed",
            "broken": "failed",
            "skipped": "skipped",
            "pending": "pending",
            "unknown": "unknown"
        }
        return status_map.get(allure_status.lower(), allure_status.lower())

    def _parse_duration(self, start: int, stop: int) -> str:
        """Convert start/stop timestamps (ms) to duration string like '43758ms'."""
        if start is not None and stop is not None:
            duration_ms = stop - start
            return f"{duration_ms}ms"
        return "0ms"

    def fetch(self) -> List[Dict[str, Any]]:
        result_files = self._find_result_files()
        logger.info(f"Found {len(result_files)} result.json files")

        if not result_files:
            logger.warning(f"No result.json files found in {self.root_path}")
            # Return empty dataset with correct schema
            empty_df = pd.DataFrame(columns=["id", "project_id", "executed_at", "tests"])
            return [{
                'name': 'test_results',
                'data': empty_df,
                'type': 'structured',
                'metadata': {'source': 'allure', 'rows': 0}
            }]

        all_tests = []
        min_start = float('inf')
        max_stop = 0

        for file_path in result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                continue

            # Extract basic fields
            name = data.get("name")
            full_name = data.get("fullName", name)
            status = self._map_status(data.get("status", "unknown"))
            start = data.get("start")
            stop = data.get("stop")
            duration_str = self._parse_duration(start, stop)
            description = data.get("description")
            status_details = data.get("statusDetails", {})
            error_message = status_details.get("message", "")
            error_trace = status_details.get("trace", "")
            error = error_message if error_message else (error_trace[:200] if error_trace else "")

            # Extract labels for additional metadata
            labels = data.get("labels", [])
            label_dict = {l["name"]: l["value"] for l in labels if "name" in l and "value" in l}
            spec_file = label_dict.get("suite", "")  # or use another label

            # Track overall execution time window
            if start is not None:
                min_start = min(min_start, start)
            if stop is not None:
                max_stop = max(max_stop, stop)

            # Build test object matching expected schema
            test_obj = {
                "full_title": full_name,
                "status": status,
                "duration": duration_str,
                "error": error,
                "spec_file": spec_file,
                # Additional fields that might be useful
                "name": name,
                "description": description,
                "labels": label_dict,
                "uuid": data.get("uuid"),
            }
            all_tests.append(test_obj)

        logger.info(f"Parsed {len(all_tests)} test results")

        # Create a single row with all tests
        executed_at = datetime.fromtimestamp(min_start / 1000, tz=timezone.utc).isoformat() if min_start != float('inf') else datetime.now(timezone.utc).isoformat()
        row_id = str(uuid.uuid4())

        df = pd.DataFrame([{
            "id": row_id,
            "project_id": None,  # Can be set from config later if needed
            "executed_at": executed_at,
            "tests": json.dumps(all_tests)  # Store as JSON string
        }])

        return [{
            'name': 'test_results',
            'data': df,
            'type': 'structured',
            'metadata': {'source': 'allure', 'rows': 1, 'test_count': len(all_tests)}
        }]