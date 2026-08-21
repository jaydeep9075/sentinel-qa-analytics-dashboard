"""
auto_ingest.py — Optional drop-box watcher: ingest anything that appears in
AUTO_INGEST_DIR, with no human in the loop.

Off unless AUTO_INGEST_ENABLED=true. The manual paths (the dashboard's "Add
Build" box -> POST /ingest/config2, and `docker compose run --rm ingest`) keep
working exactly as before either way; this is an additional trigger, not a
replacement, and it funnels into the same ingestion_jobs.start_ingestion() call
they use, so a build produced by the watcher is indistinguishable from a
manually-triggered one.

Three problems any "just watch a folder" implementation has to solve, and how
this one does:

1. Partial writes. A 500MB zip being uploaded is visible in the directory
   listing long before it is complete, and handing it to the ingester
   mid-write produces a corrupt build. Solved by requiring an entry's
   (size, mtime) to hold steady for AUTO_INGEST_STABLE_SECONDS before it is
   considered a candidate - no inotify equivalent tells you "the writer is
   done", so quiescence is the only portable signal.

2. Re-ingesting on restart. The processed set is persisted to
   auto_ingest_state.json in the data dir, keyed by (name, size, mtime), so a
   backend restart doesn't re-import everything still sitting in the drop-box.
   Because the key includes size+mtime, *replacing* a file with a new version
   of the same name is correctly treated as new work.

3. More than one watcher. Two uvicorn workers (WEB_CONCURRENCY>1) or two
   backend replicas sharing a data volume would otherwise each ingest every
   dropped file, producing duplicate builds. A lock file in the data dir
   elects exactly one watcher; the others stay idle and take over only if the
   holder stops heartbeating.

Polling, not inotify/watchdog: bind mounts on Docker Desktop (Windows/macOS)
and most network filesystems do not deliver inotify events reliably, which is
precisely where this feature is expected to run. Polling costs one stat per
top-level entry per interval and always works.
"""

import asyncio
import json
import logging
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import config, ingestion_jobs, project_builds

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None

_STATE_FILENAME = "auto_ingest_state.json"
_LOCK_FILENAME = "auto_ingest.lock"

# Suffixes writers use while a transfer is still in flight (browsers, scp,
# rsync, Office). These are skipped outright rather than waited on: the final
# file arrives under its real name, and that is what gets ingested.
_IGNORED_SUFFIXES = (
    ".part", ".partial", ".crdownload", ".tmp", ".temp", ".swp", ".filepart", ".download",
)

# Cap on how many entries are remembered as processed. The drop-box is
# expected to be pruned by whoever fills it; this just stops the state file
# growing without bound on a long-lived deployment.
_MAX_STATE_ENTRIES = 5000


def _state_path() -> Path:
    return config.DATA_BASE_PATH / _STATE_FILENAME


def _lock_path() -> Path:
    return config.DATA_BASE_PATH / _LOCK_FILENAME


# ---------------------------------------------------------------- state file


def _load_state() -> Dict[str, dict]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw.get("processed", {})
        return entries if isinstance(entries, dict) else {}
    except Exception:
        # A corrupt state file must not wedge the backend. Worst case of
        # starting empty is that files still in the drop-box get re-ingested
        # once, which is recoverable; refusing to start is not.
        logger.warning("Could not read %s - starting with an empty processed set", path, exc_info=True)
        return {}


def _save_state(processed: Dict[str, dict]) -> None:
    if len(processed) > _MAX_STATE_ENTRIES:
        # Drop the oldest by recorded timestamp.
        ordered = sorted(processed.items(), key=lambda kv: kv[1].get("at", ""))
        processed = dict(ordered[-_MAX_STATE_ENTRIES:])
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"processed": processed}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except Exception:
        logger.warning("Could not persist auto-ingest state to %s", path, exc_info=True)


# ---------------------------------------------------------------- single-owner lock


def _lock_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _stale_after() -> float:
    """A lock is considered abandoned once it stops being heartbeated. Five
    intervals of slack, floored at two minutes, so a slow scan or a long
    ingestion never looks like a crash to another instance."""
    return max(config.AUTO_INGEST_INTERVAL_SECONDS * 5, 120.0)


def _owner_process_alive(owner: str) -> Optional[bool]:
    """True/False when we can tell, None when we can't.

    Only decidable when the recorded hostname matches ours. Inside a container
    the hostname is the container id, which survives `docker compose restart`
    while the PID namespace does not - so "same host, PID gone" is a precise
    signal that the previous watcher died without releasing its lock, letting
    the new process take over immediately instead of sitting idle for the
    whole staleness window.
    """
    try:
        host, _, pid_text = str(owner).rpartition(":")
        if host != socket.gethostname():
            return None
        pid = int(pid_text)
    except (ValueError, AttributeError):
        return None
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by another user - alive as far as we're concerned.
        return True
    except OSError:
        return None


def _abandoned_reason(path: Path) -> Optional[str]:
    """Why the existing lock may be taken over, or None if it must be left alone."""
    try:
        owner = json.loads(path.read_text(encoding="utf-8")).get("owner", "")
    except Exception:
        owner = ""

    if _owner_process_alive(owner) is False:
        return f"holder {owner} is no longer running"

    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return "lock file vanished"

    if age > _stale_after():
        return f"last heartbeat {age:.0f}s ago, limit {_stale_after():.0f}s"
    return None


def _try_acquire_lock() -> bool:
    path = _lock_path()
    payload = json.dumps({"owner": _lock_identity(), "at": datetime.now(timezone.utc).isoformat()})
    for attempt in (1, 2):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            return True
        except FileExistsError:
            if attempt == 2:
                return False
            reason = _abandoned_reason(path)
            if reason is None:
                return False
            logger.info("Auto-ingest: taking over an abandoned watcher lock (%s)", reason)
            try:
                path.unlink()
            except FileNotFoundError:
                pass  # Already gone - loop round and claim it.
            except OSError:
                return False
        except OSError:
            logger.warning("Could not create auto-ingest lock at %s", path, exc_info=True)
            return False
    return False


def _heartbeat_lock() -> None:
    try:
        os.utime(_lock_path(), None)
    except OSError:
        logger.debug("Auto-ingest lock heartbeat failed", exc_info=True)


def _release_lock() -> None:
    path = _lock_path()
    try:
        if not path.exists():
            return
        owner = json.loads(path.read_text(encoding="utf-8")).get("owner")
        # Only remove our own lock - if another instance took over after
        # deciding ours was stale, deleting theirs would let a third in.
        if owner == _lock_identity():
            path.unlink()
    except Exception:
        logger.debug("Could not release auto-ingest lock", exc_info=True)


# ---------------------------------------------------------------- scanning


def _entry_signature(path: Path) -> Optional[Tuple[int, int]]:
    """(size, mtime) for a file, or the aggregate of a directory tree. Returns
    None if the entry disappeared or can't be read - callers skip those."""
    try:
        if path.is_file():
            st = path.stat()
            return (st.st_size, int(st.st_mtime))
        if path.is_dir():
            total = 0
            newest = 0
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        st = os.stat(os.path.join(root, name))
                    except OSError:
                        continue
                    total += st.st_size
                    newest = max(newest, int(st.st_mtime))
            return (total, newest)
    except OSError:
        return None
    return None


def _infer_source_type(path: Path) -> str:
    """Filesystem-aware source-type pick.

    Deliberately separate from main._infer_source_type, which only ever sees a
    user-typed string and so has to guess from substrings. Here the entry is
    known to exist and can be stat'd, so the rule is simply:
      directory -> allure (the only directory-shaped source type there is)
      .zip      -> allure (the allure connector auto-extracts zips)
      anything  -> file   (file_connector dispatches on extension)
    """
    if path.is_dir():
        return "allure"
    if path.suffix.lower() == ".zip":
        return "allure"
    return "file"


def _next_build_id() -> str:
    """`ingestion_YYYYMMDD_HHMMSS`, matching the pattern the dashboard's build
    list matches on strictly - a disambiguating suffix would make the build
    invisible in the UI, so collisions advance the clock instead."""
    stamp = datetime.now(timezone.utc)
    for _ in range(120):
        build_id = f"ingestion_{stamp.strftime('%Y%m%d_%H%M%S')}"
        if not (config.DATA_BASE_PATH / build_id).exists():
            return build_id
        stamp += timedelta(seconds=1)
    raise RuntimeError("Could not allocate a free ingestion build id")


_workspace_cache: Tuple[float, frozenset] = (0.0, frozenset())
_WORKSPACE_CACHE_TTL = 60.0


def _known_workspaces() -> frozenset:
    """Workspace names that currently have at least one member.

    Cached for a minute: this is consulted on every scan, and a workspace
    created in the admin UI becoming a routable drop-box folder within a
    minute is plenty responsive for something whose scan interval is 30s.

    Imported lazily and defensively — the watcher must keep working even if
    the auth store is unreachable, in which case everything simply routes to
    the default workspace instead of the scan dying.
    """
    global _workspace_cache
    now = time.monotonic()
    cached_at, cached = _workspace_cache
    if cached and now - cached_at < _WORKSPACE_CACHE_TTL:
        return cached

    names = {config.AUTO_INGEST_DEFAULT_WORKSPACE}
    try:
        from .auth import get_user_store

        names.update(get_user_store().list_workspaces())
    except Exception:
        logger.debug("Could not list workspaces for auto-ingest routing", exc_info=True)

    result = frozenset(n for n in names if n)
    _workspace_cache = (now, result)
    return result


def _existing_projects() -> list:
    """Project ids on disk, read straight from PROJECTS_ROOT.

    Deliberately not via ProjectManager: that pulls in lancedb and the
    sentence-transformers embedder, and the watcher only needs the names.
    Same rule as ProjectManager.list_projects - a directory holding a
    context.md is a project.
    """
    root = Path(config.PROJECTS_ROOT)
    try:
        return [entry.name for entry in root.iterdir() if entry.is_dir() and (entry / "context.md").exists()]
    except Exception:
        logger.debug("Could not list projects for auto-ingest routing", exc_info=True)
        return []


def _project_for_dropbox(path: Path) -> str:
    """Which project a dropped file belongs to, or "" when it is ambiguous.

    The drop-box has no caller to authenticate, so the path carries the
    routing here exactly as it does for the workspace:

        <AUTO_INGEST_DIR>/FSA/report.zip   -> project "FSA"

    With no matching folder, a single-project install is unambiguous and the
    build goes there. A multi-project install is not, so the build is left
    unassigned and shows up in Admin - Projects for someone to place. Guessing
    would silently file one team's results under another team's project.
    """
    projects = _existing_projects()
    if not projects:
        return ""

    parent = path.parent.name.strip().lower()
    match = next((project for project in projects if project.lower() == parent), "")
    if match:
        return match
    return projects[0] if len(projects) == 1 else ""


def _eligible(entry: Path) -> Optional[Tuple[int, int]]:
    """(size, mtime) if this entry is ready to ingest, else None."""
    if entry.name.startswith("."):
        return None
    if entry.suffix.lower() in _IGNORED_SUFFIXES:
        return None
    signature = _entry_signature(entry)
    if signature is None:
        return None
    if entry.is_file() and signature[0] == 0:
        # An empty file is either a placeholder or a write that hasn't
        # started; either way there is nothing to ingest yet.
        return None
    return signature


def _candidates() -> Dict[str, Tuple[Path, Tuple[int, int], str]]:
    """Eligible drop-box entries, mapped to the workspace they belong to.

    The drop-box is a filesystem and has no caller to authenticate, so the
    PATH carries the routing:

        <AUTO_INGEST_DIR>/report.zip              -> default workspace
        <AUTO_INGEST_DIR>/platform/report.zip     -> workspace "platform"

    A top-level directory is read as a workspace folder only when its name
    matches a workspace that actually exists. That matters because a directory
    is also a legitimate source (an unzipped Allure results folder), and the
    two are otherwise indistinguishable — so an unrecognised directory stays a
    source, which is the older behaviour and the safer default. Create the
    team first (admin UI or CLI), then its folder starts routing.

    Only one level deep, deliberately: deeper nesting would make an Allure
    results tree inside a workspace folder ambiguous all over again.
    """
    found: Dict[str, Tuple[Path, Tuple[int, int], str]] = {}
    directory = config.AUTO_INGEST_DIR
    if not directory.is_dir():
        return found

    workspaces = _known_workspaces()
    default_ws = config.AUTO_INGEST_DEFAULT_WORKSPACE

    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if entry.is_dir() and entry.name.strip().lower() in workspaces:
            workspace = entry.name.strip().lower()
            for child in sorted(entry.iterdir(), key=lambda p: p.name):
                signature = _eligible(child)
                if signature is not None:
                    found[f"{workspace}/{child.name}"] = (child, signature, workspace)
            continue

        signature = _eligible(entry)
        if signature is not None:
            found[entry.name] = (entry, signature, default_ws)
    return found


def _state_key(name: str, signature: Tuple[int, int]) -> str:
    return f"{name}|{signature[0]}|{signature[1]}"


async def _ingest(path: Path, build_id: str, workspace_id: str) -> None:
    source_path = str(path)
    source_type = _infer_source_type(path)
    dynamic_cfg = {
        "ingestion_name": f"{workspace_id}_{source_type}",
        "sources": [
            {
                "type": source_type,
                "path": source_path,
                "params": {"path": source_path},
            }
        ],
        "output": {"base_path": str(config.DATA_BASE_PATH)},
    }
    logger.info(
        "Auto-ingest: starting %s for %s (type=%s, workspace=%s)",
        build_id, source_path, source_type, workspace_id,
    )
    await ingestion_jobs.start_ingestion(
        build_id,
        dynamic_cfg,
        source_path,
        workspace_id=workspace_id,
        created_by="",  # no human actor: a file appeared on disk
        source="auto-ingest",
    )


async def _scan_once(pending: Dict[str, Tuple[Tuple[int, int], float]], processed: Dict[str, dict]) -> None:
    """One pass. `pending` carries per-entry (signature, first_seen_monotonic)
    between passes so stability can be measured across them."""
    now = time.monotonic()
    current = _candidates()

    # Forget entries that were removed from the drop-box while settling.
    for name in list(pending):
        if name not in current:
            pending.pop(name, None)

    stable_for = max(config.AUTO_INGEST_STABLE_SECONDS, config.AUTO_INGEST_INTERVAL_SECONDS)

    for name, (path, signature, workspace_id) in current.items():
        if _state_key(name, signature) in processed:
            continue

        previous = pending.get(name)
        if previous is None or previous[0] != signature:
            # First sighting, or it changed since the last pass - restart the
            # settle timer against the new signature.
            pending[name] = (signature, now)
            continue

        if now - previous[1] < stable_for:
            continue

        pending.pop(name, None)
        key = _state_key(name, signature)
        try:
            build_id = _next_build_id()
        except RuntimeError:
            logger.error("Auto-ingest: no free build id for %s, will retry next scan", name)
            continue

        project_id = _project_for_dropbox(path)
        record = {
            "build_id": build_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        # Recorded before the ingestion runs: the build directory exists from
        # the first write, and a build that appears on disk without a project
        # is invisible to everyone but an admin until this lands.
        if project_id:
            project_builds.set_build_project(build_id, project_id)
        try:
            await _ingest(path, build_id, workspace_id)
            record["status"] = "completed" if not ingestion_jobs.is_failed(build_id) else "failed"
        except Exception as exc:
            logger.exception("Auto-ingest failed for %s", name)
            record["status"] = "error"
            record["error"] = str(exc)

        # Recorded either way, deliberately. Retrying a source that failed
        # would re-fail every interval forever and bury the real error in log
        # noise; the failure is visible via GET /ingest/status/{build_id}, and
        # re-dropping the file (new mtime -> new key) retries it explicitly.
        processed[key] = record
        _save_state(processed)


async def _run_loop() -> None:
    assert _stop_event is not None
    interval = max(config.AUTO_INGEST_INTERVAL_SECONDS, 1.0)

    if not _try_acquire_lock():
        logger.info(
            "Auto-ingest: another instance holds the watcher lock at %s - this process will not watch. "
            "This is expected with WEB_CONCURRENCY>1 or multiple replicas.",
            _lock_path(),
        )
        return

    logger.info(
        "Auto-ingest: watching %s every %.0fs (settle %.0fs) -> %s",
        config.AUTO_INGEST_DIR, interval,
        max(config.AUTO_INGEST_STABLE_SECONDS, interval), config.DATA_BASE_PATH,
    )
    if not config.AUTO_INGEST_DIR.is_dir():
        logger.warning(
            "Auto-ingest: %s does not exist yet - it will be picked up automatically once created",
            config.AUTO_INGEST_DIR,
        )

    processed = _load_state()
    pending: Dict[str, Tuple[Tuple[int, int], float]] = {}

    try:
        while not _stop_event.is_set():
            try:
                _heartbeat_lock()
                await _scan_once(pending, processed)
            except Exception:
                # Never let one bad pass kill the watcher for the life of the
                # process - log and try again next interval.
                logger.exception("Auto-ingest scan failed")
            try:
                await asyncio.wait_for(_stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    finally:
        _release_lock()


async def start() -> None:
    """Called from the FastAPI lifespan. No-op unless AUTO_INGEST_ENABLED."""
    global _task, _stop_event
    if not config.AUTO_INGEST_ENABLED:
        logger.info("Auto-ingest: disabled (set AUTO_INGEST_ENABLED=true to enable)")
        return
    if _task is not None and not _task.done():
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_run_loop())


async def stop() -> None:
    """Signals the loop and waits briefly for it to release its lock. A scan
    already in flight is allowed to finish; only if it overruns is the task
    cancelled, since killing a running ingestion mid-write is worse than a
    slightly slower shutdown."""
    global _task, _stop_event
    if _task is None:
        return
    if _stop_event is not None:
        _stop_event.set()
    try:
        await asyncio.wait_for(_task, timeout=10.0)
    except asyncio.TimeoutError:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        # The task was cancelled mid-scan, so its `finally` may not have run.
        _release_lock()
    except Exception:
        logger.debug("Auto-ingest task ended with an error", exc_info=True)
    finally:
        _task = None
        _stop_event = None
