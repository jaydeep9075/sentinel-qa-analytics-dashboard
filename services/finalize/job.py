"""Finalize step: promote a finished live run from the SQLite hot layer
(services/live_exec/store.py) into LanceDB, then discard the hot-layer rows.

Deliberately reuses services/ingestion_jobs.py's existing background runner
(threadpool offload + timeout + job_status.json tracking) instead of
duplicating it - a live run is ingested the same way any other source is,
just via the new "live_run" connector (universal_ingester/connectors/
live_run_connector.py). See LIVE_EXECUTION_ARCHITECTURE.md #8 and
LIVE_EXECUTION_IMPLEMENTATION_PLAN.md "Data lifecycle".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import config, ingestion_jobs
from ..live_exec import store as live_store

logger = logging.getLogger(__name__)


def _export_path(run_id: str) -> Path:
    return config.LIVE_RUNS_DIR / run_id / "run_result.json"


def _preserve_attachments(run_id: str, attachments: list) -> None:
    """Move attachment files (screenshots/videos/traces) into the permanent
    ingestion folder before the hot-layer cleanup below deletes their
    SQLite rows. Only logs and run/test bookkeeping are meant to be
    ephemeral - a screenshot someone will want to look at later must
    survive finalize, not just exist for the few seconds a run is "live".
    """
    if not attachments:
        return
    dest_dir = config.DATA_BASE_PATH / run_id / "attachments"
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for a in attachments:
        src = Path(a.get("storage_path", ""))
        if not src.exists():
            continue
        dest = dest_dir / src.name
        try:
            src.replace(dest)
        except OSError:
            logger.warning("could not move attachment %s for run %s", src, run_id)
            continue
        manifest.append({"test_id": a.get("test_id"), "kind": a.get("kind"), "filename": dest.name})

    if manifest:
        manifest_path = config.DATA_BASE_PATH / run_id / "attachments_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Best-effort cleanup of the now-empty staging folder.
    staging_dir = config.LIVE_RUNS_DIR / run_id / "attachments"
    try:
        if staging_dir.exists() and not any(staging_dir.iterdir()):
            staging_dir.rmdir()
    except OSError:
        pass


async def finalize_run(run_id: str) -> None:
    """Runs as a FastAPI BackgroundTask, scheduled right after a run is
    marked finished (see live_exec/router.py::patch_run)."""
    export = live_store.export_run(run_id)
    if not export.get("run"):
        logger.warning("finalize_run: run %s not found, skipping", run_id)
        return

    json_path = _export_path(run_id)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(export, default=str, indent=2), encoding="utf-8")

    # One run -> one ingestion folder (data/<run_id>/lancedb/...), exactly
    # like every other build already shows up under GET /ingestions - no
    # separate "live run history" UI needed, it's the same list.
    dynamic_cfg = {"sources": [{"type": "live_run", "params": {"path": str(json_path)}}]}
    build_id = run_id

    await ingestion_jobs.start_ingestion(build_id, dynamic_cfg, source_path=str(json_path))

    status = ingestion_jobs.get_status(build_id)
    if status and status.get("status") == "completed":
        _preserve_attachments(run_id, export.get("attachments") or [])
        live_store.delete_run(run_id)
        try:
            json_path.unlink()
        except OSError:
            pass
        logger.info(
            "live run %s finalized into LanceDB and discarded from the hot layer", run_id
        )
    else:
        error = status.get("error") if status else "unknown error"
        logger.error(
            "live run %s failed to finalize (%s) - leaving hot-layer data in place for retry",
            run_id, error,
        )
