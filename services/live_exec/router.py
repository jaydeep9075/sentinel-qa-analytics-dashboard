"""API surface for live test execution.

Two different auth models on purpose:
- Ingestion endpoints (called by the @sentinel/playwright reporter, i.e. a
  CI runner or a developer's laptop) use a simple shared `x-api-key` header,
  matching the reporter-SDK pattern described in LIVE_EXECUTION_ARCHITECTURE.md.
- Browser-facing endpoints (called by the Sentinel dashboard) reuse the
  existing JWT auth. The SSE endpoint additionally accepts the token as a
  `?token=` query param because browsers' EventSource cannot set custom
  headers - that's a documented limitation of SSE, not a shortcut.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from jose import JWTError, jwt

from .. import config
from . import screencast, store
from .bus import bus
from .schemas import EventBatch, LiveFrameIn, RunCreate, RunStatusUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["live-execution"])

_warned_no_ingest_key = False


def require_ingest_key(x_api_key: str = Header(default="")) -> None:
    global _warned_no_ingest_key
    if not config.LIVE_INGEST_API_KEY:
        if not _warned_no_ingest_key:
            logger.warning(
                "LIVE_INGEST_API_KEY is unset AND couldn't be auto-generated "
                "(state directory unwritable - see the error logged at startup) - "
                "live-execution ingestion endpoints are unauthenticated. Set "
                "LIVE_INGEST_API_KEY in .env or fix state directory permissions."
            )
            _warned_no_ingest_key = True
        return
    if x_api_key != config.LIVE_INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing x-api-key")


def get_dashboard_user(request: Request, token: Optional[str] = Query(default=None)) -> dict:
    """Same JWT contract as services.auth.get_current_user, plus a query-param
    fallback so EventSource (which can't set headers) can authenticate."""
    raw_token = token
    if not raw_token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            raw_token = header.split(" ", 1)[1]
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(raw_token, config.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"username": username, "role": role, "workspace_id": payload.get("workspace_id")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _snapshot_with_frames(run_id: str) -> dict:
    # store.get_snapshot does 3 synchronous SQLite reads - offload to a
    # thread so it can't stall the single event loop this whole backend
    # runs on (see the asyncio.to_thread note on post_live_frame below for
    # why that matters here specifically).
    snapshot = await asyncio.to_thread(store.get_snapshot, run_id)
    worker_count = (snapshot.get("run") or {}).get("worker_count") or 1
    frame_values = await asyncio.gather(
        *(screencast.get_frame(run_id, w) for w in range(worker_count))
    )
    snapshot["frames"] = {str(w): frame for w, frame in enumerate(frame_values) if frame}
    return snapshot


@router.post("/runs", dependencies=[Depends(require_ingest_key)])
async def create_run(data: RunCreate) -> dict:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    result = await asyncio.to_thread(store.create_run, run_id, data)
    bus.publish(run_id, {"event_type": "run.started", "ts": _now(), "run": result})
    logger.info("live run started: %s (%s)", run_id, data.framework)
    return result


@router.post("/runs/{run_id}/events", dependencies=[Depends(require_ingest_key)])
async def post_events(run_id: str, batch: EventBatch) -> dict:
    # This is the hottest of hot paths - every reporter flushes here on a
    # 1s timer per worker. Both the existence check and the batch write are
    # synchronous SQLite calls; run them off the event loop so one run's
    # ingestion traffic can't stall every other run's SSE stream and every
    # other API request this single-process backend is serving concurrently.
    if not await asyncio.to_thread(store.get_run, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    await asyncio.to_thread(store.apply_batch, run_id, batch)
    for event in batch.events:
        bus.publish(run_id, event.model_dump())
    return {"accepted": len(batch.events)}


@router.patch("/runs/{run_id}", dependencies=[Depends(require_ingest_key)])
async def patch_run(run_id: str, data: RunStatusUpdate, background_tasks: BackgroundTasks) -> dict:
    existing = await asyncio.to_thread(store.get_run, run_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Run not found")
    await asyncio.to_thread(store.update_run_status, run_id, data.status)
    bus.publish(run_id, {"event_type": "run.finished", "ts": _now(), "status": data.status})
    await screencast.clear_run(run_id, worker_count=existing.get("worker_count") or 8)
    logger.info("live run finished: %s -> %s", run_id, data.status)

    from ..finalize.job import finalize_run

    background_tasks.add_task(finalize_run, run_id)
    return {"run_id": run_id, "status": data.status}


@router.post("/runs/{run_id}/attachments", dependencies=[Depends(require_ingest_key)])
async def upload_attachment(
    run_id: str,
    test_id: str,
    kind: str,
    file: UploadFile = File(...),
) -> dict:
    if not await asyncio.to_thread(store.get_run, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    dest_dir: Path = config.LIVE_RUNS_DIR / run_id / "attachments"
    safe_name = f"{uuid.uuid4().hex}_{Path(file.filename or 'attachment').name}"
    dest_path = dest_dir / safe_name
    # UploadFile.read() is already non-blocking; only the actual disk write
    # (mkdir + fwrite, both syscalls) needs offloading to a thread. Videos in
    # particular can be several MB, so writing them synchronously on the
    # event loop would stall every other in-flight request for that long.
    contents = await file.read()

    def _write() -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(contents)

    await asyncio.to_thread(_write)

    attachment = await asyncio.to_thread(store.add_attachment, run_id, test_id, kind, str(dest_path))
    bus.publish(run_id, {
        "event_type": "test.attachment",
        "ts": attachment["created_at"],
        "test": {"id": test_id, "title": test_id},
        "payload": {"id": attachment["id"], "kind": kind, "storage_path": str(dest_path)},
    })
    return {"id": attachment["id"], "storage_path": str(dest_path)}


@router.post("/runs/{run_id}/live-frame", dependencies=[Depends(require_ingest_key)])
async def post_live_frame(run_id: str, data: LiveFrameIn) -> dict:
    """Latest-frame-wins (see screencast.py) - overwrite-only, never queried
    historically, so a missing run just means 'nothing to show yet' rather
    than a hard error worth failing the reporter's request over."""
    # The single highest-frequency call in this whole API (up to 1x/sec per
    # worker, every worker, for the life of every live run) - definitely
    # can't afford to block the event loop here.
    if not await asyncio.to_thread(store.get_run, run_id):
        return {"accepted": False}
    await screencast.set_frame(run_id, data.worker_id, data.frame)
    bus.publish(run_id, {
        "event_type": "worker.frame",
        "ts": _now(),
        "worker_id": data.worker_id,
        "payload": {"frame": data.frame},
    })
    return {"accepted": True}


@router.get("/attachments/{attachment_id}", dependencies=[Depends(get_dashboard_user)])
async def get_attachment_file(attachment_id: int):
    """Serves the actual file bytes (screenshot/video/trace) so the
    dashboard can render an <img>/<video> tag directly against this URL.
    Auth via get_dashboard_user (JWT header or ?token= - same rule as the
    SSE stream: <img>/<video> tags can't set custom headers either).

    Only valid while the run is still in the hot layer - once finalized,
    use /history-attachments/{run_id}/{filename} instead (see
    get_finalized_run below for why these can't share one endpoint: the
    numeric id here only exists in SQLite, which finalize deliberately
    discards)."""
    attachment = await asyncio.to_thread(store.get_attachment, attachment_id)
    if not attachment or not Path(attachment["storage_path"]).exists():
        raise HTTPException(status_code=404, detail="Attachment not found")
    media_type, _ = mimetypes.guess_type(attachment["storage_path"])
    return FileResponse(attachment["storage_path"], media_type=media_type or "application/octet-stream")


@router.get("/history/{run_id}", dependencies=[Depends(get_dashboard_user)])
async def get_finalized_run(run_id: str) -> dict:
    """Fallback for a run that has already finalized - its hot-layer SQLite
    rows are gone by design (see finalize/job.py), but the permanent record
    (LanceDB structured_test_results + preserved attachment files) is still
    there. This is what the live-run page falls back to once GET
    /runs/{run_id} 404s, so a screenshot/video is still reachable after the
    run finishes, not just while it's in progress. Logs are NOT recovered
    here - discarding them once permanent is the point (see
    LIVE_EXECUTION_WHY_THIS_APPROACH.md)."""
    ingestion_dir = config.DATA_BASE_PATH / run_id
    if not ingestion_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    def _read_tests() -> list[dict]:
        import lancedb  # local import: only needed for this rarely-hit fallback path

        db = lancedb.connect(str(ingestion_dir / "lancedb"))
        df = db.open_table("structured_test_results").to_pandas()
        return [
            {
                "test_id": row.get("test_id") or row.get("title", ""),
                "title": row.get("title", ""),
                "status": row.get("status", ""),
                "duration_ms": row.get("duration_ms"),
                "error": row.get("error") or None,
            }
            for _, row in df.iterrows()
        ]

    try:
        # LanceDB connect + Arrow->pandas materialization is blocking I/O -
        # offload it like every other disk-touching call in this router.
        # (Not a scaling risk in itself: each run finalizes into its own
        # lancedb/ folder under data/<run_id>/, so this only ever scans that
        # one run's handful of rows, never the whole history.)
        tests: list[dict] = await asyncio.to_thread(_read_tests)
    except Exception:
        tests = []
        logger.warning("get_finalized_run: could not read structured_test_results for %s", run_id, exc_info=True)

    attachments: list[dict] = []
    manifest_path = ingestion_dir / "attachments_manifest.json"
    if manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            attachments = [
                {
                    "id": f"{run_id}/{a['filename']}",
                    "test_id": a.get("test_id"),
                    "kind": a.get("kind"),
                }
                for a in raw
            ]
        except Exception:
            logger.warning("get_finalized_run: could not read attachments manifest for %s", run_id, exc_info=True)

    overall_status = "failed" if any(t["status"] == "failed" for t in tests) else ("passed" if tests else "unknown")
    return {
        "run": {"run_id": run_id, "status": overall_status, "finished_at": None, "finalized": True},
        "tests": tests,
        "logs": [],
        "attachments": attachments,
    }


@router.get("/history-attachments/{run_id}/{filename}", dependencies=[Depends(get_dashboard_user)])
async def get_history_attachment(run_id: str, filename: str):
    """Serves a permanently-preserved attachment by (run_id, filename)
    instead of a SQLite id, since finalize deliberately deletes the id that
    used to identify it (see get_attachment_file)."""
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = config.DATA_BASE_PATH / run_id / "attachments" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment not found")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.get("/runs", dependencies=[Depends(get_dashboard_user)])
async def list_runs(workspace_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    # Polled every 2s by the Live Runs list page - frequent enough that it's
    # worth keeping off the event loop too.
    return await asyncio.to_thread(store.list_runs, workspace_id, limit)


@router.get("/runs/{run_id}", dependencies=[Depends(get_dashboard_user)])
async def get_run(run_id: str) -> dict:
    snapshot = await _snapshot_with_frames(run_id)
    if not snapshot["run"]:
        raise HTTPException(status_code=404, detail="Run not found")
    return snapshot


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request, user: dict = Depends(get_dashboard_user)):
    if not await asyncio.to_thread(store.get_run, run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    queue = bus.subscribe(run_id)

    async def event_gen():
        try:
            snapshot = await _snapshot_with_frames(run_id)
            yield f"event: snapshot\ndata: {json.dumps(snapshot, default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_type = message.get("event_type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(message, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
