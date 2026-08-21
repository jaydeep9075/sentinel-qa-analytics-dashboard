"""
project_builds.py - Maps build ids to project ids.

This keeps rollout simple and reversible while project-scoped data ownership
is being introduced incrementally.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from . import config

_MAP_FILE: Path = config.STATE_DIR / "build_project_map.json"
_BUILD_FOLDER_PATTERN = re.compile(r"^(ingestion_\d{8}_\d{6}|run_[0-9a-f]{8,})$")


def _norm_build_id(build_id: str) -> str:
    return str(build_id or "").strip()


def _norm_project_id(project_id: str) -> str:
    return str(project_id or "").strip()


def _load() -> Dict:
    if not _MAP_FILE.exists():
        return {"builds": {}, "updated_at": ""}
    try:
        payload = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"builds": {}, "updated_at": ""}
    if not isinstance(payload, dict):
        return {"builds": {}, "updated_at": ""}

    builds = payload.get("builds")
    if not isinstance(builds, dict):
        builds = {}
    normalized = {}
    for bid, pid in builds.items():
        build_id = _norm_build_id(str(bid))
        project_id = _norm_project_id(str(pid))
        if build_id and project_id:
            normalized[build_id] = project_id
    return {
        "builds": normalized,
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _save(payload: Dict) -> None:
    data = dict(payload)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MAP_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_build_project(build_id: str) -> str:
    data = _load()
    return str(data.get("builds", {}).get(_norm_build_id(build_id), ""))


def set_build_project(build_id: str, project_id: str) -> bool:
    bid = _norm_build_id(build_id)
    pid = _norm_project_id(project_id)
    if not bid or not pid:
        return False

    data = _load()
    builds = dict(data.get("builds", {}))
    builds[bid] = pid
    data["builds"] = builds
    _save(data)
    return True


def remove_build(build_id: str) -> None:
    bid = _norm_build_id(build_id)
    if not bid:
        return
    data = _load()
    builds = dict(data.get("builds", {}))
    if bid in builds:
        builds.pop(bid, None)
        data["builds"] = builds
        _save(data)


def list_map() -> Dict[str, str]:
    data = _load()
    builds = data.get("builds", {})
    if not isinstance(builds, dict):
        return {}
    return {str(k): str(v) for k, v in builds.items()}


def get_snapshot() -> Dict[str, object]:
    data = _load()
    builds = data.get("builds", {})
    if not isinstance(builds, dict):
        builds = {}
    return {
        "builds": {str(k): str(v) for k, v in builds.items()},
        "updated_at": str(data.get("updated_at") or ""),
    }


def discover_existing_build_ids() -> List[str]:
    ids: List[str] = []
    try:
        for entry in config.DATA_BASE_PATH.iterdir():
            if not entry.is_dir():
                continue
            if not _BUILD_FOLDER_PATTERN.match(entry.name):
                continue
            if not (entry / "lancedb").exists():
                continue
            ids.append(entry.name)
    except Exception:
        return []
    return sorted(ids)


def list_unassigned_build_ids() -> List[str]:
    """Builds on disk that no project claims yet.

    These are the pre-project builds of an existing install. They are visible
    to administrators only until somebody assigns them, which is what
    claim_unassigned_builds does.
    """
    mapped = _load().get("builds", {})
    return [bid for bid in discover_existing_build_ids() if not mapped.get(bid)]


def claim_unassigned_builds(project_id: str) -> Dict[str, int]:
    """Assign every currently unassigned build to `project_id` (idempotent).

    Deliberately does *not* touch builds that already belong somewhere: a
    bulk re-parent is a data move, not a migration, and would silently pull
    another team's builds into this project. Reassigning a specific build is
    set_build_project's job.
    """
    pid = _norm_project_id(project_id)
    if not pid:
        return {"discovered": 0, "assigned": 0, "already_assigned": 0}

    data = _load()
    builds = dict(data.get("builds", {}))
    discovered = discover_existing_build_ids()

    assigned = 0
    already = 0
    for build_id in discovered:
        if builds.get(build_id):
            already += 1
            continue
        builds[build_id] = pid
        assigned += 1

    if assigned:
        data["builds"] = builds
        _save(data)

    return {
        "discovered": len(discovered),
        "assigned": assigned,
        "already_assigned": already,
    }


def count_builds_for_project(project_id: str) -> int:
    pid = _norm_project_id(project_id).lower()
    if not pid:
        return 0
    return sum(1 for value in _load().get("builds", {}).values() if str(value).lower() == pid)
