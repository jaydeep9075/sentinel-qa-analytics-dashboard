"""Ingestion run report: per-dataset outcomes, errors, warnings, dedup stats.

One malformed dataset must never abort a whole run — instead every outcome
(success, partial, failure) is collected here and written to
`ingestion_report.json` inside the build folder so failures are debuggable
after the fact.


"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IngestionReport:
    def __init__(self, build_id: str):
        self.build_id = build_id
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: Optional[datetime] = None
        self.datasets: Dict[str, Dict[str, Any]] = {}
        self.warnings: List[Dict[str, str]] = []

    def _entry(self, name: str) -> Dict[str, Any]:
        if name not in self.datasets:
            self.datasets[name] = {
                "status": "pending",
                "rows_stored": 0,
                "documents_stored": 0,
                "duplicates_skipped": 0,
                "records_failed": 0,
                "tables": [],
                "parser_strategy": None,
                "parser_confidence": None,
                "schema_changes": [],
                "error": None,
            }
        return self.datasets[name]

    def dataset_started(self, name: str, source_type: str) -> None:
        entry = self._entry(name)
        entry["status"] = "running"
        entry["source_type"] = source_type

    def dataset_completed(
        self,
        name: str,
        rows_stored: int = 0,
        documents_stored: int = 0,
        tables: Optional[List[str]] = None,
        parser_strategy: Optional[str] = None,
        parser_confidence: Optional[float] = None,
    ) -> None:
        entry = self._entry(name)
        entry["status"] = "partial" if entry["records_failed"] else "completed"
        entry["rows_stored"] += int(rows_stored)
        entry["documents_stored"] += int(documents_stored)
        if tables:
            for t in tables:
                if t not in entry["tables"]:
                    entry["tables"].append(t)
        if parser_strategy:
            entry["parser_strategy"] = parser_strategy
        if parser_confidence is not None:
            entry["parser_confidence"] = parser_confidence

    def dataset_failed(self, name: str, error: Exception | str) -> None:
        entry = self._entry(name)
        entry["status"] = "failed"
        entry["error"] = str(error)
        logger.error("Dataset %s failed: %s", name, error)

    def record_failures(self, name: str, count: int, reason: str = "") -> None:
        if count <= 0:
            return
        entry = self._entry(name)
        entry["records_failed"] += int(count)
        if reason:
            self.warn(name, f"{count} record(s) skipped: {reason}")

    def record_duplicates(self, name: str, count: int) -> None:
        if count > 0:
            self._entry(name)["duplicates_skipped"] += int(count)

    def record_schema_change(self, name: str, description: str) -> None:
        self._entry(name)["schema_changes"].append(description)

    def warn(self, dataset: str, message: str) -> None:
        self.warnings.append({"dataset": dataset, "message": message})
        logger.warning("[%s] %s", dataset, message)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        statuses = [d["status"] for d in self.datasets.values()]
        if not statuses:
            overall = "empty"
        elif all(s == "failed" for s in statuses):
            overall = "failed"
        elif any(s in ("failed", "partial") for s in statuses):
            overall = "partial"
        else:
            overall = "completed"
        return {
            "build_id": self.build_id,
            "overall_status": overall,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "datasets": self.datasets,
            "warnings": self.warnings,
            "totals": {
                "rows_stored": sum(d["rows_stored"] for d in self.datasets.values()),
                "documents_stored": sum(d["documents_stored"] for d in self.datasets.values()),
                "duplicates_skipped": sum(d["duplicates_skipped"] for d in self.datasets.values()),
                "records_failed": sum(d["records_failed"] for d in self.datasets.values()),
                "datasets_failed": sum(1 for s in statuses if s == "failed"),
            },
        }

    def write(self, folder: Path) -> None:
        try:
            path = Path(folder) / "ingestion_report.json"
            path.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Could not write ingestion report for %s", self.build_id, exc_info=True)
