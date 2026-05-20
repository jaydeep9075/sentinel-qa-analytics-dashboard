import glob
import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
        self.root_path = os.path.abspath(allure_results_path)
        if not os.path.isdir(self.root_path):
            raise ValueError(f"Path does not exist: {self.root_path}")

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

    # ---------- main fetch ----------
    def fetch(self) -> List[Dict[str, Any]]:
        result_files = self._find_result_files()
        logger.info(f"Found {len(result_files)} Allure result files in {self.root_path}")
        if not result_files:
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
