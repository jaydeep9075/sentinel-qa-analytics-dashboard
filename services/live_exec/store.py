

"""SQLite (WAL mode) store for in-progress live runs.

This is the "hot" layer for live execution: small, frequent writes about
runs currently in progress. It is intentionally separate from LanceDB, which
stays the durable analytical store for finished runs (see the finalize step,
which exports a run from here into a JSON file and feeds it through the
existing universal_ingester pipeline).

Each call opens a short-lived connection. WAL mode lets the API process
(writer) and anything else reading the same file do so safely without a
long-lived shared connection or an app-level lock.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .. import config
from .schemas import EventBatch, ExecutionEvent, RunCreate

DB_PATH: Path = config.DATA_BASE_PATH / "live_runs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    run_id TEXT PRIMARY KEY,
    name TEXT,
    workspace_id TEXT,
    project_id TEXT,
    framework TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    environment TEXT,
    ci_provider TEXT,
    branch TEXT,
    commit_sha TEXT,
    build_url TEXT,
    worker_count INTEGER,
    metadata TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS test (
    run_id TEXT NOT NULL,
    test_id TEXT NOT NULL,
    title TEXT,
    file TEXT,
    status TEXT,
    retry INTEGER DEFAULT 0,
    duration_ms INTEGER,
    worker_id INTEGER,
    error TEXT,
    updated_at TEXT,
    PRIMARY KEY (run_id, test_id)
);

CREATE TABLE IF NOT EXISTS log_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    test_id TEXT,
    ts TEXT,
    level TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    test_id TEXT,
    kind TEXT,
    storage_path TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_test_run ON test(run_id);
CREATE INDEX IF NOT EXISTS idx_log_run ON log_line(run_id);
CREATE INDEX IF NOT EXISTS idx_attachment_run ON attachment(run_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)
        # This is the hot/ephemeral layer (see module docstring) - existing
        # rows are never precious - but a plain ADD COLUMN is still cheaper
        # and less surprising than wiping the file on every schema tweak.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(run)").fetchall()}
        if "name" not in existing_cols:
            conn.execute("ALTER TABLE run ADD COLUMN name TEXT")


def create_run(run_id: str, data: RunCreate) -> dict:
    started_at = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO run (
                run_id, name, workspace_id, project_id, framework, status,
                environment, ci_provider, branch, commit_sha, build_url,
                worker_count, metadata, started_at
            ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                data.name,
                data.workspace_id,
                data.project_id,
                data.framework,
                data.environment,
                data.ci_provider,
                data.branch,
                data.commit_sha,
                data.build_url,
                data.worker_count,
                json.dumps(data.metadata),
                started_at,
            ),
        )
    return {"run_id": run_id, "name": data.name, "status": "running", "started_at": started_at}


def get_run(run_id: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM run WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def update_run_status(run_id: str, status: str) -> None:
    finished_at = _now() if status in {"passed", "failed", "cancelled"} else None
    with _conn() as conn:
        conn.execute(
            "UPDATE run SET status = ?, finished_at = COALESCE(?, finished_at) WHERE run_id = ?",
            (status, finished_at, run_id),
        )


def list_runs(workspace_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if workspace_id:
            rows = conn.execute(
                "SELECT * FROM run WHERE workspace_id = ? ORDER BY started_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM run ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def apply_event(run_id: str, event: ExecutionEvent) -> None:
    """Persist a single normalized event (opens its own connection - fine
    for one-off callers like the attachment endpoint). Batched ingestion
    goes through apply_batch instead, which shares one connection/transaction
    across the whole batch rather than paying a connect+commit per event."""
    with _conn() as conn:
        _apply_event(conn, run_id, event)


def _apply_event(conn: sqlite3.Connection, run_id: str, event: ExecutionEvent) -> None:
    if event.event_type in {"test.started", "test.finished"} and event.test:
        t = event.test
        conn.execute(
            """
            INSERT INTO test (run_id, test_id, title, file, status, retry, duration_ms, worker_id, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, test_id) DO UPDATE SET
                title=excluded.title, file=excluded.file, status=excluded.status,
                retry=excluded.retry, duration_ms=excluded.duration_ms,
                worker_id=excluded.worker_id, error=excluded.error, updated_at=excluded.updated_at
            """,
            (
                run_id, t.id, t.title, t.file, t.status, t.retry,
                t.duration_ms, event.worker_id, t.error, event.ts,
            ),
        )
    elif event.event_type == "test.log":
        conn.execute(
            "INSERT INTO log_line (run_id, test_id, ts, level, message) VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                event.test.id if event.test else None,
                event.ts,
                str(event.payload.get("level", "info")),
                str(event.payload.get("message", "")),
            ),
        )
    elif event.event_type == "test.attachment":
        conn.execute(
            "INSERT INTO attachment (run_id, test_id, kind, storage_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                event.test.id if event.test else None,
                str(event.payload.get("kind", "")),
                str(event.payload.get("storage_path", "")),
                event.ts,
            ),
        )
    # run.started / run.finished / worker.heartbeat carry no additional row
    # of their own here — run status is handled via update_run_status.


def apply_batch(run_id: str, batch: EventBatch) -> None:
    """Share one connection and one transaction across the whole batch
    instead of a connect+autocommit cycle per event - the previous version
    did the latter, which meant a 20-event flush from the reporter paid 20
    separate SQLite commits (each a WAL fsync) instead of one. This is the
    hot path under real load (many workers, frequent flushes), so it's
    worth not paying that per-event."""
    if not batch.events:
        return
    with _conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for event in batch.events:
                _apply_event(conn, run_id, event)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def add_attachment(run_id: str, test_id: Optional[str], kind: str, storage_path: str) -> dict:
    """Separate from apply_event/apply_batch on purpose: attachments always
    arrive one at a time through the dedicated upload endpoint (never
    batched), and the frontend needs the real row id back to be able to
    request the file later via GET /live/attachments/{id} - apply_event's
    normalized-event path had no way to hand that id back to the caller."""
    ts = _now()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO attachment (run_id, test_id, kind, storage_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, test_id, kind, storage_path, ts),
        )
        attachment_id = cur.lastrowid
    return {
        "id": attachment_id,
        "run_id": run_id,
        "test_id": test_id,
        "kind": kind,
        "storage_path": storage_path,
        "created_at": ts,
    }


def get_attachment(attachment_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM attachment WHERE id = ?", (attachment_id,)).fetchone()
        return dict(row) if row else None


def get_snapshot(run_id: str) -> dict:
    run = get_run(run_id)
    with _conn() as conn:
        tests = [dict(r) for r in conn.execute(
            "SELECT * FROM test WHERE run_id = ? ORDER BY updated_at", (run_id,)
        ).fetchall()]
        logs = [dict(r) for r in conn.execute(
            "SELECT * FROM log_line WHERE run_id = ? ORDER BY id DESC LIMIT 200", (run_id,)
        ).fetchall()]
        attachments = [dict(r) for r in conn.execute(
            "SELECT * FROM attachment WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()]
    return {"run": run, "tests": tests, "logs": logs, "attachments": attachments}


def export_run(run_id: str) -> dict:
    """Full export used by the finalize step to build run_result.json before
    handing it to the universal_ingester live_run connector."""
    run = get_run(run_id)
    with _conn() as conn:
        tests = [dict(r) for r in conn.execute(
            "SELECT * FROM test WHERE run_id = ?", (run_id,)
        ).fetchall()]
        logs = [dict(r) for r in conn.execute(
            "SELECT * FROM log_line WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()]
        attachments = [dict(r) for r in conn.execute(
            "SELECT * FROM attachment WHERE run_id = ?", (run_id,)
        ).fetchall()]
    return {"run": run, "tests": tests, "logs": logs, "attachments": attachments}


def delete_run(run_id: str) -> None:
    """Discard all hot-layer data for a run once it has been finalized into
    LanceDB. Nothing live is kept once it's permanent."""
    with _conn() as conn:
        conn.execute("DELETE FROM log_line WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM attachment WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM test WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM run WHERE run_id = ?", (run_id,))
