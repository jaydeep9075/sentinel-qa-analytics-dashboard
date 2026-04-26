import json
import os
import glob
import uuid
from typing import List, Dict, Any
from collections import defaultdict
import pandas as pd
from datetime import datetime, timezone
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class AllureConnector(BaseConnector):
    def __init__(self, allure_results_path: str):
        if not allure_results_path:
            raise ValueError("Allure results path is required")
        self.root_path = allure_results_path
        if not os.path.isdir(self.root_path):
            raise ValueError(f"Path does not exist: {self.root_path}")

    def _find_result_files(self) -> List[str]:
        result_files = []
        if os.path.basename(self.root_path) == "allure-results":
            result_files = glob.glob(os.path.join(self.root_path, "*-result.json"))
            if result_files:
                return result_files
        artifact_pattern = os.path.join(self.root_path, "artifact_*", "allure-results", "*-result.json")
        result_files = glob.glob(artifact_pattern)
        if result_files:
            return result_files
        for root, dirs, files in os.walk(self.root_path):
            if os.path.basename(root) == "allure-results":
                result_files.extend(glob.glob(os.path.join(root, "*-result.json")))
        return result_files

    def _map_status(self, allure_status: str) -> str:
        status_map = {
            "passed": "passed",
            "failed": "failed",
            "broken": "failed",   # broken still counts as failed unless retry passes
            "skipped": "skipped",
            "pending": "pending",
            "unknown": "unknown"
        }
        return status_map.get(allure_status.lower(), allure_status.lower())

    def _parse_duration_seconds(self, start: int, stop: int) -> float:
        if start is not None and stop is not None:
            return round((stop - start) / 1000.0, 2)
        return 0.0

    def _parse_duration_string(self, duration_seconds: float) -> str:
        return f"{int(duration_seconds * 1000)}ms"

    def _extract_history_id(self, data: Dict[str, Any]) -> str:
        history_id = data.get("historyId")
        if history_id:
            return history_id
        full_name = data.get("fullName")
        if full_name:
            return full_name
        name = data.get("name")
        if name:
            return name
        return data.get("uuid", str(uuid.uuid4()))

    def _extract_project_name(self, data: Dict[str, Any], label_dict: Dict[str, Any]) -> str:
        parameters = data.get("parameters", [])
        for param in parameters:
            if not isinstance(param, dict):
                continue
            param_name = str(param.get("name", "")).strip().lower()
            if param_name == "project":
                value = str(param.get("value", "")).strip()
                if value:
                    return value

        title_path = label_dict.get("titlePath", "")
        if isinstance(title_path, str) and title_path:
            parts = [p.strip() for p in title_path.split(">") if p.strip()]
            if len(parts) >= 2:
                return parts[1]

        thread = label_dict.get("thread", "")
        if isinstance(thread, str) and "-playwright-worker-" in thread:
            return "Playwright"

        return "unknown"

    def _extract_module_name(self, full_name: str, spec_file: str, label_dict: Dict[str, Any]) -> str:
        normalized_spec = (spec_file or "").replace("\\", "/")
        spec_looks_like_path = "/" in normalized_spec or normalized_spec.endswith(".spec.ts") or normalized_spec.endswith(".spec.js")
        if normalized_spec and spec_looks_like_path:
            parts = [p for p in normalized_spec.split("/") if p]
            if len(parts) >= 3:
                return "/".join(parts[:3])
            if parts:
                return parts[-1]

        normalized_full = (full_name or "").replace("\\", "/")
        if normalized_full:
            path_like = normalized_full.split("#")[0]
            path_parts = [p for p in path_like.split("/") if p]
            if len(path_parts) >= 3:
                return "/".join(path_parts[:3])
            if path_parts:
                return path_parts[-1]

        parent_suite = str(label_dict.get("parentSuite", "")).strip()
        sub_suite = str(label_dict.get("subSuite", "")).strip()
        if parent_suite and sub_suite:
            return f"{parent_suite}/{sub_suite}"
        if parent_suite:
            return parent_suite
        if sub_suite:
            return sub_suite
        return "unknown"

    def _detect_platform_type(self, project_name: str, module_name: str, full_name: str, tags: List[str]) -> str:
        source = " ".join([
            str(project_name or ""),
            str(module_name or ""),
            str(full_name or ""),
            " ".join([str(t) for t in tags or []]),
        ]).lower()
        mobile_keywords = [
            "iphone", "ipad", "android", "mobile", "pixel", "samsung", "ios", "appium"
        ]
        if any(k in source for k in mobile_keywords):
            return "mobile"
        return "desktop"

    def _merge_test_runs(self, tests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple runs of the same test case using Allure's optimistic retry logic:
        If any run passed -> final status = passed.
        Otherwise, use the most severe status among failures."""
        if not tests:
            return None
        
        # Base on the latest run (for metadata like description, labels, etc.)
        sorted_tests = sorted(tests, key=lambda x: x.get('stop', 0), reverse=True)
        base = sorted_tests[0].copy()
        
        # Determine final status: PASSED if any run passed
        has_passed = any(t.get("status") == "passed" for t in tests)
        if has_passed:
            final_status = "passed"
        else:
            # No passes: choose most severe among failures/broken
            status_priority = {"failed": 4, "broken": 3, "skipped": 1, "pending": 0, "unknown": 0}
            final_status = "failed"
            highest = 0
            for t in tests:
                s = t.get("status", "unknown")
                p = status_priority.get(s, 0)
                if p > highest:
                    highest = p
                    final_status = s
        
        # Collect errors from failed/broken runs (only if final_status is not passed)
        errors = []
        if final_status != "passed":
            for t in tests:
                if t.get("status") in ["failed", "broken"]:
                    err = t.get("error", "")
                    if err and err.strip():
                        errors.append(err)
        
        # Maximum duration across runs
        max_duration = max((t.get("duration_seconds", 0) for t in tests), default=0)
        
        base["status"] = final_status
        base["duration_seconds"] = max_duration
        base["duration"] = self._parse_duration_string(max_duration)
        base["error"] = errors[0] if errors else ""
        
        return base

    def fetch(self) -> List[Dict[str, Any]]:
        result_files = self._find_result_files()
        logger.info(f"Found {len(result_files)} result.json files")

        if not result_files:
            empty_df = pd.DataFrame(columns=[
                "id", "project_id", "executed_at", "test_name", "status",
                "duration_seconds", "duration", "error_message", "spec_file",
                "labels", "tags", "full_name", "description", "steps_count",
                "attachments_count", "history_id"
            ])
            return [{
                'name': 'test_results',
                'data': empty_df,
                'type': 'structured',
                'metadata': {'source': 'allure', 'rows': 0}
            }]

        all_raw_tests = []
        min_start = float('inf')

        for file_path in result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                continue

            name = data.get("name")
            full_name = data.get("fullName", name)
            status = self._map_status(data.get("status", "unknown"))
            start = data.get("start")
            stop = data.get("stop")
            duration_seconds = self._parse_duration_seconds(start, stop)
            duration_str = self._parse_duration_string(duration_seconds)
            description = data.get("description")
            status_details = data.get("statusDetails", {})
            error_message = status_details.get("message", "")
            error_trace = status_details.get("trace", "")
            error = error_message if error_message else (error_trace[:500] if error_trace else "")

            labels = data.get("labels", [])
            label_dict = {l["name"]: l["value"] for l in labels if "name" in l and "value" in l}
            spec_file = label_dict.get("suite", "")
            history_id = self._extract_history_id(data)
            tags = [l["value"] for l in labels if l.get("name") == "tag"]
            project_name = self._extract_project_name(data, label_dict)
            module_name = self._extract_module_name(full_name, spec_file, label_dict)
            platform_type = self._detect_platform_type(project_name, module_name, full_name, tags)

            if start is not None:
                min_start = min(min_start, start)

            test_obj = {
                "history_id": history_id,
                "full_name": full_name,
                "name": name,
                "status": status,
                "duration_seconds": duration_seconds,
                "duration": duration_str,
                "error": error,
                "spec_file": spec_file,
                "description": description,
                "labels": label_dict,
                "tags": tags,
                "project_name": project_name,
                "module_name": module_name,
                "platform_type": platform_type,
                "uuid": data.get("uuid"),
                "start": start,
                "stop": stop,
                "steps_count": len(data.get("steps", [])),
                "attachments_count": len(data.get("attachments", [])),
            }
            all_raw_tests.append(test_obj)

        logger.info(f"Parsed {len(all_raw_tests)} raw test results")

        # Group by history_id
        tests_by_id = {}
        for test in all_raw_tests:
            tid = test["history_id"]
            tests_by_id.setdefault(tid, []).append(test)

        logger.info(f"Grouped into {len(tests_by_id)} logical test cases")

        merged_tests = []
        for tid, runs in tests_by_id.items():
            if len(runs) == 1:
                merged_tests.append(runs[0])
            else:
                merged_tests.append(self._merge_test_runs(runs))

        logger.info(f"Final test count: {len(merged_tests)}")
        status_counts = {}
        for t in merged_tests:
            status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
        logger.info(f"Status breakdown: {status_counts}")

        executed_at = datetime.fromtimestamp(min_start / 1000, tz=timezone.utc).isoformat() if min_start != float('inf') else datetime.now(timezone.utc).isoformat()

        rows = []
        for test in merged_tests:
            rows.append({
                "id": str(uuid.uuid4()),
                "project_id": None,
                "executed_at": executed_at,
                "test_name": test.get("full_name", test.get("name", "")),
                "status": test.get("status", ""),
                "duration_seconds": test.get("duration_seconds", 0.0),
                "duration": test.get("duration", "0ms"),
                "error_message": test.get("error", ""),
                "spec_file": test.get("spec_file", ""),
                "labels": json.dumps(test.get("labels", {})),
                "tags": json.dumps(test.get("tags", [])),
                "full_name": test.get("full_name", ""),
                "project_name": test.get("project_name", "unknown"),
                "module_name": test.get("module_name", "unknown"),
                "platform_type": test.get("platform_type", "desktop"),
                "description": test.get("description", ""),
                "steps_count": test.get("steps_count", 0),
                "attachments_count": test.get("attachments_count", 0),
                "history_id": test.get("history_id", ""),
            })

        df = pd.DataFrame(rows)
        logger.info(f"Created DataFrame with {len(df)} rows (logical tests)")
        
        grouped = defaultdict(lambda: {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "pending": 0,
            "unknown": 0,
            "total_duration_seconds": 0.0
        })

        for test in merged_tests:
            project_name = test.get("project_name", "unknown")
            module_name = test.get("module_name", "unknown")
            platform_type = test.get("platform_type", "desktop")
            status = test.get("status", "unknown")
            duration = float(test.get("duration_seconds", 0.0) or 0.0)

            key = (project_name, module_name, platform_type)
            agg = grouped[key]
            agg["total_tests"] += 1
            agg["total_duration_seconds"] += duration
            if status == "passed":
                agg["passed"] += 1
            elif status in ("failed", "broken"):
                agg["failed"] += 1
            elif status == "skipped":
                agg["skipped"] += 1
            elif status == "pending":
                agg["pending"] += 1
            else:
                agg["unknown"] += 1

        module_rows = []
        for (project_name, module_name, platform_type), agg in grouped.items():
            total = agg["total_tests"]
            executed = agg["passed"] + agg["failed"]
            pass_rate = round((agg["passed"] / executed * 100), 2) if executed > 0 else 0.0
            module_rows.append({
                "id": str(uuid.uuid4()),
                "project_name": project_name,
                "module_name": module_name,
                "platform_type": platform_type,
                "total_tests": total,
                "passed": agg["passed"],
                "failed": agg["failed"],
                "skipped": agg["skipped"],
                "pending": agg["pending"],
                "unknown": agg["unknown"],
                "pass_rate": pass_rate,
                "total_duration_seconds": round(agg["total_duration_seconds"], 2),
                "avg_duration_seconds": round((agg["total_duration_seconds"] / total), 2) if total else 0.0,
                "status_breakdown": json.dumps({
                    "passed": agg["passed"],
                    "failed": agg["failed"],
                    "skipped": agg["skipped"],
                    "pending": agg["pending"],
                    "unknown": agg["unknown"],
                }),
                "executed_at": executed_at
            })

        df_module = pd.DataFrame(module_rows)

        project_grouped = defaultdict(lambda: {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "pending": 0,
            "unknown": 0,
            "total_duration_seconds": 0.0,
            "module_names": set()
        })
        for row in module_rows:
            key = (row["project_name"], row["platform_type"])
            agg = project_grouped[key]
            agg["total_tests"] += int(row["total_tests"])
            agg["passed"] += int(row["passed"])
            agg["failed"] += int(row["failed"])
            agg["skipped"] += int(row["skipped"])
            agg["pending"] += int(row["pending"])
            agg["unknown"] += int(row["unknown"])
            agg["total_duration_seconds"] += float(row["total_duration_seconds"])
            agg["module_names"].add(row["module_name"])

        project_rows = []
        for (project_name, platform_type), agg in project_grouped.items():
            executed = agg["passed"] + agg["failed"]
            pass_rate = round((agg["passed"] / executed * 100), 2) if executed > 0 else 0.0
            project_rows.append({
                "id": str(uuid.uuid4()),
                "project_name": project_name,
                "platform_type": platform_type,
                "module_count": len(agg["module_names"]),
                "total_tests": agg["total_tests"],
                "passed": agg["passed"],
                "failed": agg["failed"],
                "skipped": agg["skipped"],
                "pending": agg["pending"],
                "unknown": agg["unknown"],
                "pass_rate": pass_rate,
                "total_duration_seconds": round(agg["total_duration_seconds"], 2),
                "avg_duration_seconds": round((agg["total_duration_seconds"] / agg["total_tests"]), 2) if agg["total_tests"] else 0.0,
                "executed_at": executed_at
            })

        df_project = pd.DataFrame(project_rows)

        return [{
            'name': 'test_results',
            'data': df,
            'type': 'structured',
            'metadata': {
                'source': 'allure',
                'rows': len(df),
                'raw_files': len(result_files),
                'logical_tests': len(merged_tests),
                'status_breakdown': status_counts,
                'executed_at': executed_at
            }
        }, {
            'name': 'test_module_metrics',
            'data': df_module,
            'type': 'structured',
            'metadata': {
                'source': 'allure',
                'rows': len(df_module),
                'executed_at': executed_at
            }
        }, {
            'name': 'test_project_metrics',
            'data': df_project,
            'type': 'structured',
            'metadata': {
                'source': 'allure',
                'rows': len(df_project),
                'executed_at': executed_at
            }
        }]