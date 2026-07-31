"""
ingestion_jobs.py — Lightweight in-process background ingestion runner.

Ingestion previously ran synchronously inside the FastAPI request handler,
blocking the single asyncio event loop (and therefore every other
concurrent request — dashboard loads, chat, other users' requests) for the
entire duration of large imports.

This module offloads the actual (CPU/IO-bound, synchronous) UniversalIngester
call to a worker thread via anyio.to_thread.run_sync, so the event loop stays
responsive, and tracks status both in-memory and in a small job_status.json
file inside each ingestion's own output folder — so status for a given
ingestion survives a backend restart without needing a new database, queue,
or external service (per the "lightweight, no new infra" choice).
"""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import anyio

from . import config

logger = logging.getLogger(__name__)

_jobs: Dict[str, dict] = {}
_lock = threading.Lock()
# get_status() falls back to the on-disk job_status.json when a build_id
# isn't cached here, so this dict is purely a fast-path cache - safe to cap.
# Without a cap, a long-running backend process grows one entry per
# ingestion ever run, forever.
_MAX_TRACKED_JOBS = 200


def _status_path(build_id: str) -> Path:
    return config.DATA_BASE_PATH / build_id / "job_status.json"


def _write_status(build_id: str, status: dict) -> None:
    with _lock:
        _jobs[build_id] = status
        if len(_jobs) > _MAX_TRACKED_JOBS:
            for key in list(_jobs.keys())[: len(_jobs) - _MAX_TRACKED_JOBS]:
                _jobs.pop(key, None)
    try:
        path = _status_path(build_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.warning("Could not persist job status for %s", build_id, exc_info=True)


def get_status(build_id: str) -> Optional[dict]:
    with _lock:
        cached = _jobs.get(build_id)
    if cached:
        return cached
    path = _status_path(build_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def is_failed(build_id: str) -> bool:
    status = get_status(build_id)
    return bool(status and status.get("status") == "failed")


def _check_source_size(source_path: str) -> Optional[str]:
    """Basic guard against absurdly large single-file sources. Directory
    sources (e.g. an Allure results folder) aren't cheaply sizeable up
    front, so those are left to the connector layer / row-count guard."""
    try:
        p = Path(source_path)
    except Exception:
        return None
    if p.exists() and p.is_file():
        size = p.stat().st_size
        if size > config.INGEST_MAX_FILE_SIZE_BYTES:
            limit_mb = config.INGEST_MAX_FILE_SIZE_BYTES / (1024 * 1024)
            actual_mb = size / (1024 * 1024)
            return f"Source file is {actual_mb:.1f}MB, exceeds the {limit_mb:.0f}MB ingestion limit"
    return None


async def start_ingestion(build_id: str, dynamic_cfg: dict, source_path: str) -> None:
    """Runs as a FastAPI BackgroundTask: the HTTP response has already been
    sent by the time this executes, so blocking here doesn't delay the
    client — and the actual ingestion work is further offloaded to a
    worker thread so it doesn't block the event loop for other requests."""
    started_at = datetime.now(timezone.utc).isoformat()

    size_error = _check_source_size(source_path)
    if size_error:
        _write_status(build_id, {
            "build_id": build_id, "status": "failed", "error": size_error,
            "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        return

    _write_status(build_id, {
        "build_id": build_id, "status": "running", "error": None,
        "started_at": started_at, "finished_at": None,
    })

    temp_cfg_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as tf:
            json.dump(dynamic_cfg, tf, indent=2, ensure_ascii=False)
            temp_cfg_path = tf.name

        from universal_ingester.ingester import UniversalIngester

        ingester = UniversalIngester(data_base_path=str(config.DATA_BASE_PATH))

        try:
            with anyio.fail_after(config.INGEST_TIMEOUT_SECONDS):
                await anyio.to_thread.run_sync(
                    ingester.run_ingestion_from_config, temp_cfg_path, build_id
                )
        except TimeoutError:
            # Note: the worker thread itself cannot be force-killed from here —
            # Python has no safe thread-cancellation primitive. Marking the job
            # failed stops the *frontend* from waiting on it; the thread may
            # still finish writing files in the background. Acceptable for
            # this lightweight approach; a real cancellation signal would
            # require restructuring the ingester to poll a stop flag.
            raise RuntimeError(f"Ingestion timed out after {config.INGEST_TIMEOUT_SECONDS:.0f}s")

        _write_status(build_id, {
            "build_id": build_id, "status": "completed", "error": None,
            "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.exception("Ingestion %s failed: %s", build_id, e)
        _write_status(build_id, {
            "build_id": build_id, "status": "failed", "error": str(e),
            "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        if temp_cfg_path:
            try:
                os.remove(temp_cfg_path)
            except Exception:
                pass
