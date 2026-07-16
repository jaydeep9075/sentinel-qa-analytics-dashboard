import glob
import json
import logging
import os
import uuid
import zipfile
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

import pandas as pd

from .base import BaseConnector

logger = logging.getLogger(__name__)

_PARENT_SUITE_MAP = {
    "fsa store tests": "FSA",
    "hsa store tests": "HSA",
    "wdh store tests": "WDH",
}
_SKIP_SUITE_LEVELS = {
    "regression tests suite", "regression suite", "smoke tests suite",
    "smoke suite", "regression", "smoke",
}
_MOBILE_PROJECT_KEYWORDS = ("iphone", "ipad", "android", "mobile", "pixel", "samsung", "galaxy", "appium")


class AllureConnector(BaseConnector):
    def __init__(self, allure_results_path: str):
        if not allure_results_path:
            raise ValueError("Allure results path is required")

        # Clean up path: remove extra quotes, normalize slashes, handle spaces
        cleaned_path = allure_results_path.strip('"').strip("'")
        cleaned_path = cleaned_path.replace('\\\\', '\\')  # Fix double backslashes
        self.input_path = os.path.abspath(cleaned_path)

        # Check if it's a zip file
        if self.input_path.endswith('.zip') and os.path.isfile(self.input_path):
            logger.info(f"Detected zip file: {self.input_path}")
            # Extract zip to temp directory
            self.root_path = self._extract_zip(self.input_path)
            logger.info(f"Extracted to: {self.root_path}")
        else:
            # Regular directory path
            self.root_path = self.input_path

            # Try to find the actual path (handles nested folders, spaces, special chars)
            if not os.path.isdir(self.root_path):
                # Try parent directories
                for _ in range(3):
                    parent = os.path.dirname(self.root_path)
                    if parent == self.root_path:  # Reached root
                        break
                    if os.path.isdir(parent):
                        self.root_path = parent
                        logger.warning(f"Path didn't exist, using parent: {self.root_path}")
                        break

                # Final check
                if not os.path.isdir(self.root_path):
                    raise ValueError(
                        f"Path does not exist: {self.root_path}\n"
                        f"Original: {allure_results_path}\n"
                        f"Please verify the path is a valid zip file or directory."
                    )

        self.processed_files = set()

    def _extract_zip(self, zip_path: str) -> str:
        """Extract zip file to temp directory."""
        try:
            # Create temp directory for extraction
            temp_dir = tempfile.mkdtemp(prefix="allure_")

            # Extract zip
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            logger.info(f"Extracted {len(zip_ref.namelist())} files to {temp_dir}")

            # Find the actual results directory
            results_dir = self._find_results_directory(temp_dir)
            if results_dir:
                return results_dir

            # If no specific results dir found, return temp dir
            return temp_dir

        except zipfile.BadZipFile:
            raise ValueError(f"Invalid zip file: {zip_path}")
        except Exception as e:
            raise ValueError(f"Failed to extract zip: {e}")

    def _find_results_directory(self, base_path: str) -> Optional[str]:
        """Find the actual Allure results directory in extracted files."""
        # Look for directories containing *-result.json files
        for root, dirs, files in os.walk(base_path):
            for f in files:
                if f.endswith("-result.json"):
                    # Found Allure results, return this directory
                    return root

        # Look for 'results' or 'allure-results' directory
        for root, dirs, files in os.walk(base_path):
            for d in dirs:
                if d in ('results', 'allure-results', 'allure'):
                    results_path = os.path.join(root, d)
                    # Check if it contains Allure files
                    for sub_root, sub_dirs, sub_files in os.walk(results_path):
                        if any(f.endswith("-result.json") for f in sub_files):
                            return results_path

        return None

    # ---------- improved file discovery ----------
    def _find_result_files(self):
        """Recursively find all files ending with -result.json (or result.json)."""
        matches = []
        for root, dirs, files in os.walk(self.root_path):
            for f in files:
                if f.endswith("-result.json") or f.endswith("result.json"):
                    matches.append(os.path.join(root, f))
        return matches

    # ---------- helpers (unchanged) ----------
    def _map_status(self, raw: str) -> str:
        return {
            "passed": "passed",
            "failed": "failed",
            "broken": "failed",
            "skipped": "skipped",
            "pending": "pending",
            "unknown": "unknown",
        }.get((raw or "unknown").lower(), (raw or "unknown").lower())

    def _duration_seconds(self, start: Optional[int], stop: Optional[int]) -> float:
        if start is not None and stop is not None:
            return round((stop - start) / 1000.0, 3)
        return 0.0

    def _extract_history_id(self, data: Dict[str, Any]) -> str:
        for key in ("historyId", "fullName", "name"):
            val = data.get(key)
            if val:
                return val
        return data.get("uuid", str(uuid.uuid4()))

    def _extract_project_name(self, label_dict: Dict[str, str]) -> str:
        parent = label_dict.get("parentSuite", "").strip().lower()
        if parent in _PARENT_SUITE_MAP:
            return _PARENT_SUITE_MAP[parent]
        for k, v in _PARENT_SUITE_MAP.items():
            if k in parent or v.lower() in parent:
                return v
        title_path = label_dict.get("titlePath", "")
        for token in ("FSA", "HSA", "WDH"):
            if token in title_path.upper():
                return token
        return "unknown"

    def _extract_module_name(self, full_name: str, label_dict: Dict[str, str]) -> str:
        sub_suite = label_dict.get("subSuite", "").strip()
        if sub_suite and sub_suite.lower() not in _SKIP_SUITE_LEVELS:
            return sub_suite
        suite = label_dict.get("suite", "").strip()
        if suite and suite.lower() not in _SKIP_SUITE_LEVELS:
            return suite
        if full_name:
            path_part = full_name.split("#")[0].replace("\\", "/")
            parts = [p for p in path_part.split("/") if p]
            if parts:
                last = parts[-1]
                for ext in (".spec.ts", ".spec.js", ".test.ts", ".test.js"):
                    last = last.replace(ext, "")
                if last:
                    return last
        return "unknown"

    def _extract_platform_type(self, data: Dict[str, Any]) -> str:
        for param in data.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if str(param.get("name", "")).strip().lower() == "project":
                value = str(param.get("value", "")).strip().lower()
                if any(kw in value for kw in _MOBILE_PROJECT_KEYWORDS):
                    return "mobile"
                return "desktop"
        return "desktop"

    def _extract_browser(self, data: Dict[str, Any]) -> str:
        for param in data.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if str(param.get("name", "")).strip().lower() == "project":
                return str(param.get("value", "")).strip()
        return "GoogleChrome"

    def _merge_retries(self, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not runs:
            return {}
        base = sorted(runs, key=lambda x: x.get("stop", 0), reverse=True)[0].copy()
        if any(r["status"] == "passed" for r in runs):
            final_status = "passed"
            error = ""
        else:
            priority = {"failed": 4, "broken": 3, "skipped": 1, "pending": 0, "unknown": 0}
            worst = max(runs, key=lambda r: priority.get(r.get("status", "unknown"), 0))
            final_status = worst["status"]
            error = worst.get("error", "")
        base["status"] = final_status
        base["error"] = error
        base["duration_seconds"] = max((r.get("duration_seconds", 0.0) for r in runs), default=0.0)
        return base

    # ---------- HTML artifact parsing (NEW) ----------
    def _parse_html_artifacts(self) -> List[Dict[str, Any]]:
        """Extract test data from Allure HTML reports (index.html, report.html)."""
        html_files = []
        for root, dirs, files in os.walk(self.root_path):
            for f in files:
                if f in ("index.html", "report.html") or f.endswith("-report.html"):
                    html_files.append(os.path.join(root, f))

        records = []
        for html_path in html_files:
            try:
                import re
                with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Extract test data from HTML (look for JSON embedded in scripts)
                json_matches = re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>([^<]+)</script>', content)
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, list):
                            records.extend(data)
                        elif isinstance(data, dict):
                            records.append(data)
                    except json.JSONDecodeError:
                        continue

                # Fallback: extract from data attributes or tables
                if not records:
                    test_data = re.findall(r'data-test="([^"]*)"[^>]*>([^<]*)</[^>]*>', content)
                    for test_id, test_name in test_data:
                        records.append({"test_id": test_id, "test_name": test_name})

                logger.info(f"Extracted {len(records)} records from {html_path}")
            except Exception as e:
                logger.warning(f"Failed to parse HTML {html_path}: {e}")

        return records

    # ---------- Nested JSON handling (NEW) ----------
    def _flatten_nested_json(self, obj: Any, prefix: str = "") -> Dict[str, Any]:
        """Flatten nested JSON objects with dot notation."""
        result = {}

        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    result.update(self._flatten_nested_json(value, new_key))
                else:
                    result[new_key] = value
        elif isinstance(obj, list):
            if obj and isinstance(obj[0], dict):
                # For arrays of objects, take first item's keys
                for i, item in enumerate(obj[:1]):
                    result.update(self._flatten_nested_json(item, prefix))
            else:
                result[prefix] = json.dumps(obj) if obj else None
        else:
            result[prefix] = obj

        return result

    def _parse_any_json_format(self, json_data: Any, source_file: str = "") -> List[Dict[str, Any]]:
        """Parse any JSON format (nested, flat, arrays, objects)."""
        records = []

        if isinstance(json_data, list):
            for item in json_data:
                if isinstance(item, dict):
                    records.append(self._flatten_nested_json(item))
                else:
                    records.append({"value": item})
        elif isinstance(json_data, dict):
            # Check if dict contains a list of records
            list_fields = [v for v in json_data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]

            if list_fields:
                for item in list_fields[0]:
                    records.append(self._flatten_nested_json(item))
            else:
                # Single object, flatten it
                records.append(self._flatten_nested_json(json_data))

        return records

    def _find_all_json_files(self) -> List[str]:
        """Find all JSON files (not just Allure result files)."""
        json_files = []
        for root, dirs, files in os.walk(self.root_path):
            for f in files:
                if f.endswith(".json"):
                    json_files.append(os.path.join(root, f))
        return json_files

    # ---------- create dataset from generic records ----------
    def _create_dataset_from_records(self, records: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
        """Create dataset from generic JSON records (non-Allure format)."""
        if not records:
            return []

        df = pd.DataFrame(records)

        return [{
            "name": "raw_data",
            "data": df,
            "type": "structured",
            "metadata": {
                "source": source,
                "rows": len(df),
                "columns": list(df.columns),
                "data_type": "generic_json",
                "detected_at_runtime": True
            }
        }]

    # ---------- main fetch ----------
    def fetch(self) -> List[Dict[str, Any]]:
        result_files = self._find_result_files()
        logger.info(f"Found {len(result_files)} Allure result files in {self.root_path}")

        # Try HTML artifacts if no Allure JSON found
        if not result_files:
            logger.info("No Allure JSON results found, trying HTML artifacts...")
            html_records = self._parse_html_artifacts()
            if html_records:
                logger.info(f"Found {len(html_records)} records in HTML artifacts")
                return self._create_dataset_from_records(html_records, "html")

            # Try any JSON files in folder
            logger.info("No HTML artifacts found, trying any JSON files...")
            json_files = self._find_all_json_files()
            all_records = []
            for json_file in json_files:
                if json_file in self.processed_files:
                    continue
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    records = self._parse_any_json_format(data, json_file)
                    all_records.extend(records)
                    self.processed_files.add(json_file)
                    logger.info(f"Parsed {len(records)} records from {json_file}")
                except Exception as e:
                    logger.warning(f"Failed to parse JSON file {json_file}: {e}")

            if all_records:
                logger.info(f"Found {len(all_records)} records in JSON files")
                return self._create_dataset_from_records(all_records, "json")

            # Empty fallback
            empty_df = pd.DataFrame(columns=[
                "id", "executed_at", "test_name", "full_name", "history_id",
                "status", "duration_seconds", "error_message",
                "project_name", "module_name", "platform_type", "browser",
                "spec_file", "description", "labels", "tags",
                "steps_count", "attachments_count"
            ])
            return [{
                "name": "test_results",
                "data": empty_df,
                "type": "structured",
                "metadata": {"source": "allure", "rows": 0}
            }]

        raw_tests = []
        min_start = float("inf")

        for fp in result_files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                logger.error(f"Failed to read {fp}: {exc}")
                continue

            labels = data.get("labels", [])
            label_dict = {lbl["name"]: lbl["value"] for lbl in labels if "name" in lbl and "value" in lbl}
            full_name = data.get("fullName") or data.get("name", "")
            start = data.get("start")
            stop = data.get("stop")
            status = self._map_status(data.get("status", "unknown"))
            status_details = data.get("statusDetails") or {}
            err_msg = status_details.get("message", "")
            err_trace = status_details.get("trace", "")
            error = err_msg if err_msg else (err_trace[:500] if err_trace else "")
            tags = [lbl["value"] for lbl in labels if lbl.get("name") == "tag"]
            if start is not None:
                min_start = min(min_start, start)

            raw_tests.append({
                "history_id": self._extract_history_id(data),
                "full_name": full_name,
                "name": data.get("name", ""),
                "status": status,
                "duration_seconds": self._duration_seconds(start, stop),
                "error": error,
                "spec_file": label_dict.get("suite", ""),
                "description": data.get("description", ""),
                "labels": label_dict,
                "tags": tags,
                "project_name": self._extract_project_name(label_dict),
                "module_name": self._extract_module_name(full_name, label_dict),
                "platform_type": self._extract_platform_type(data),
                "browser": self._extract_browser(data),
                "uuid": data.get("uuid"),
                "start": start,
                "stop": stop,
                "steps_count": len(data.get("steps", [])),
                "attachments_count": len(data.get("attachments", [])),
            })

        logger.info(f"Parsed {len(raw_tests)} raw test records")

        # group by history_id and merge retries
        by_id = {}
        for t in raw_tests:
            by_id.setdefault(t["history_id"], []).append(t)
        merged = [runs[0] if len(runs) == 1 else self._merge_retries(runs) for runs in by_id.values()]

        status_counts = {}
        for t in merged:
            status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
        logger.info(f"After retry‑merge: {len(merged)} logical tests | {status_counts}")

        executed_at = (
            datetime.fromtimestamp(min_start / 1000, tz=timezone.utc).isoformat()
            if min_start != float("inf")
            else datetime.now(timezone.utc).isoformat()
        )

        # build DataFrame
        rows = []
        for t in merged:
            rows.append({
                "id": str(uuid.uuid4()),
                "executed_at": executed_at,
                "test_name": t.get("full_name") or t.get("name", ""),
                "full_name": t.get("full_name", ""),
                "history_id": t.get("history_id", ""),
                "status": t["status"],
                "duration_seconds": round(float(t.get("duration_seconds", 0.0)), 3),
                "error_message": t.get("error", ""),
                "project_name": t["project_name"],
                "module_name": t["module_name"],
                "platform_type": t["platform_type"],
                "browser": t.get("browser", "GoogleChrome"),
                "spec_file": t.get("spec_file", ""),
                "description": t.get("description", ""),
                "labels": json.dumps(t.get("labels", {})),
                "tags": json.dumps(t.get("tags", [])),
                "steps_count": t.get("steps_count", 0),
                "attachments_count": t.get("attachments_count", 0),
            })
        df_results = pd.DataFrame(rows)

        # module metrics
        mod_agg = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0,
                                       "skipped": 0, "pending": 0, "unknown": 0, "duration": 0.0})
        for t in merged:
            key = (t["project_name"], t["module_name"], t["platform_type"])
            a = mod_agg[key]
            a["total"] += 1
            a["duration"] += float(t.get("duration_seconds", 0.0) or 0.0)
            s = t["status"]
            if s == "passed":
                a["passed"] += 1
            elif s in ("failed", "broken"):
                a["failed"] += 1
            elif s == "skipped":
                a["skipped"] += 1
            elif s == "pending":
                a["pending"] += 1
            else:
                a["unknown"] += 1

        module_rows = []
        for (proj, mod, plat), a in mod_agg.items():
            executed = a["passed"] + a["failed"]
            pass_rate = round(a["passed"] / executed * 100, 2) if executed else 0.0
            module_rows.append({
                "id": str(uuid.uuid4()),
                "project_name": proj,
                "module_name": mod,
                "platform_type": plat,
                "total_tests": a["total"],
                "passed": a["passed"],
                "failed": a["failed"],
                "skipped": a["skipped"],
                "pending": a["pending"],
                "unknown": a["unknown"],
                "pass_rate": pass_rate,
                "total_duration_seconds": round(a["duration"], 2),
                "avg_duration_seconds": round(a["duration"] / a["total"], 2) if a["total"] else 0.0,
                "executed_at": executed_at,
            })
        df_module = pd.DataFrame(module_rows)

        # project metrics
        proj_agg = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0,
                                        "skipped": 0, "pending": 0, "unknown": 0,
                                        "duration": 0.0, "modules": set()})
        for r in module_rows:
            key = (r["project_name"], r["platform_type"])
            a = proj_agg[key]
            a["total"] += r["total_tests"]
            a["passed"] += r["passed"]
            a["failed"] += r["failed"]
            a["skipped"] += r["skipped"]
            a["pending"] += r["pending"]
            a["unknown"] += r["unknown"]
            a["duration"] += r["total_duration_seconds"]
            a["modules"].add(r["module_name"])

        project_rows = []
        for (proj, plat), a in proj_agg.items():
            executed = a["passed"] + a["failed"]
            pass_rate = round(a["passed"] / executed * 100, 2) if executed else 0.0
            project_rows.append({
                "id": str(uuid.uuid4()),
                "project_name": proj,
                "platform_type": plat,
                "module_count": len(a["modules"]),
                "total_tests": a["total"],
                "passed": a["passed"],
                "failed": a["failed"],
                "skipped": a["skipped"],
                "pending": a["pending"],
                "unknown": a["unknown"],
                "pass_rate": pass_rate,
                "total_duration_seconds": round(a["duration"], 2),
                "avg_duration_seconds": round(a["duration"] / a["total"], 2) if a["total"] else 0.0,
                "executed_at": executed_at,
            })
        df_project = pd.DataFrame(project_rows)

        return [
            {"name": "test_results", "data": df_results, "type": "structured",
             "metadata": {"source": "allure", "rows": len(df_results), "raw_files": len(result_files),
                          "logical_tests": len(merged), "status_breakdown": status_counts,
                          "executed_at": executed_at}},
            {"name": "test_module_metrics", "data": df_module, "type": "structured",
             "metadata": {"source": "allure", "rows": len(df_module)}},
            {"name": "test_project_metrics", "data": df_project, "type": "structured",
             "metadata": {"source": "allure", "rows": len(df_project)}},
        ]
