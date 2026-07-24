"""Reads a run_result.json exported from the live-execution SQLite store
(services/live_exec/store.export_run) and turns it into a structured
dataset using the exact same connector contract as any other source -
Allure, CSV, DB (see connectors/base.py).

Unlike Allure, there is no format-guessing to do here: Sentinel's own
reporter already sent clean, typed data, so this connector is a direct
mapping, not a parser. The engine (ingester.py) takes it from there:
schema detection, storage into `structured_test_results`, and - for row
counts under the embed cap - automatic embedding for AI/semantic search,
identical to every other structured source.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .base import BaseConnector


class LiveRunConnector(BaseConnector):
    def __init__(self, path: str):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Live run export not found: {path}")

    def fetch(self) -> List[Dict[str, Any]]:
        with open(self.path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        run = payload.get("run") or {}
        tests = payload.get("tests") or []
        logs = payload.get("logs") or []
        attachments = payload.get("attachments") or []

        logs_by_test: Dict[str, list] = {}
        for line in logs:
            logs_by_test.setdefault(line.get("test_id"), []).append(line)

        attachments_by_test: Dict[str, list] = {}
        for a in attachments:
            attachments_by_test.setdefault(a.get("test_id"), []).append(a)

        rows = []
        for t in tests:
            test_id = t.get("test_id")
            test_logs = logs_by_test.get(test_id, [])
            # Last 20 lines is enough context for AI search without bloating
            # every row with an unbounded log dump.
            log_excerpt = "\n".join(
                f"[{l.get('level', 'log')}] {l.get('message', '')}" for l in test_logs[-20:]
            )
            rows.append({
                "build_id": run.get("run_id"),
                "test_id": test_id,
                "spec_file": t.get("file") or "",
                "title": t.get("title") or test_id,
                "status": t.get("status") or "unknown",
                "duration_ms": t.get("duration_ms"),
                "retry_count": t.get("retry", 0),
                "worker_id": t.get("worker_id"),
                "error": t.get("error") or "",
                "log_excerpt": log_excerpt,
                "attachment_count": len(attachments_by_test.get(test_id, [])),
                "framework": run.get("framework", "playwright"),
                "environment": run.get("environment"),
                "ci_provider": run.get("ci_provider"),
                "branch": run.get("branch"),
                "commit_sha": run.get("commit_sha"),
            })

        df = pd.DataFrame(rows)
        return [{
            # Ends up as Lance table "structured_test_results" - the engine
            # prefixes table_key with "structured_" (see
            # ingester.py::_store_structured_frame) - matching the table
            # name every other ingestion path already writes and queries.
            "name": "test_results",
            "data": df,
            "type": "structured",
            "metadata": {
                "source": "live_execution",
                "run_id": run.get("run_id"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "run_status": run.get("status"),
                "rows": len(df),
            },
        }]
