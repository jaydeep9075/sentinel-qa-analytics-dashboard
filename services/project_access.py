"""
project_access.py - Lightweight per-user project visibility mapping.

This intentionally lives in STATE_DIR as JSON for a fast rollout:
- no DB migration needed,
- easy backup/restore,
- admin changes take effect immediately.

Shape:
{
  "users": {
    "alice": ["FSA"],
    "bob": ["FSA", "HSA"]
  },
  "updated_at": "..."
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from . import config

_ACCESS_FILE: Path = config.STATE_DIR / "project_access.json"


def _norm_user(username: str) -> str:
    return str(username or "").strip().lower()


def _norm_project(project_id: str) -> str:
    return str(project_id or "").strip()


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in items:
        item = _norm_project(raw)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _load() -> Dict:
    if not _ACCESS_FILE.exists():
        return {"users": {}, "updated_at": ""}
    try:
        payload = json.loads(_ACCESS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}, "updated_at": ""}
    if not isinstance(payload, dict):
        return {"users": {}, "updated_at": ""}
    users = payload.get("users")
    if not isinstance(users, dict):
        users = {}
    normalized = {}
    for username, projects in users.items():
        if not isinstance(projects, list):
            continue
        normalized[_norm_user(username)] = _dedupe_keep_order([str(p) for p in projects])
    return {
        "users": normalized,
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _save(payload: Dict) -> None:
    payload = dict(payload)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ACCESS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_user_projects(username: str) -> List[str]:
    data = _load()
    return list(data.get("users", {}).get(_norm_user(username), []))


def set_user_projects(username: str, projects: List[str]) -> List[str]:
    data = _load()
    users = dict(data.get("users", {}))
    uname = _norm_user(username)
    users[uname] = _dedupe_keep_order(projects)
    data["users"] = users
    _save(data)
    return list(users[uname])


def list_access_map() -> Dict[str, List[str]]:
    data = _load()
    users = data.get("users", {})
    if not isinstance(users, dict):
        return {}
    return {str(k): list(v or []) for k, v in users.items()}


def get_visible_projects(
    username: str,
    role: str,
    available_projects: List[str],
) -> List[str]:
    """Project list for this account.

    - admin/cto: every project that exists, always. An administrator is the
      account that grants access, so it cannot be locked out of the thing it
      administers.
    - everyone else: explicit assignment only. There is deliberately no
      "default project" fallback - a silent grant is indistinguishable from a
      real one when you audit who can see what, and the bootstrap case is
      handled explicitly at project-creation time instead
      (see seed_project_for_users).
    """
    all_projects = _dedupe_keep_order(available_projects)
    role_norm = str(role or "").strip().lower()
    if role_norm in {"admin", "cto"}:
        return all_projects

    assigned = list_user_projects(username)
    if not assigned:
        return []

    allowed = {p.lower() for p in assigned}
    return [p for p in all_projects if p.lower() in allowed]


def seed_project_for_users(usernames: List[str], project_id: str) -> int:
    """Assign `project_id` to users that currently have no mapping.

    Returns number of users updated.
    """
    data = _load()
    users = dict(data.get("users", {}))
    pid = _norm_project(project_id)
    if not pid:
        return 0

    changed = 0
    for username in usernames:
        uname = _norm_user(username)
        if not uname:
            continue
        current = list(users.get(uname, []))
        if current:
            continue
        users[uname] = [pid]
        changed += 1

    if changed > 0:
        data["users"] = users
        _save(data)
    return changed


def grant_project_to_users(usernames: List[str], project_id: str) -> int:
    """Add `project_id` to every listed user that doesn't already have it.

    Unlike seed_project_for_users this does not skip users who already have
    some other project - it is the "everyone works on this one too" action.
    Returns the number of users actually changed.
    """
    data = _load()
    users = dict(data.get("users", {}))
    pid = _norm_project(project_id)
    if not pid:
        return 0

    changed = 0
    for username in usernames:
        uname = _norm_user(username)
        if not uname:
            continue
        current = list(users.get(uname, []))
        if any(p.lower() == pid.lower() for p in current):
            continue
        users[uname] = _dedupe_keep_order(current + [pid])
        changed += 1

    if changed > 0:
        data["users"] = users
        _save(data)
    return changed


def remove_project_everywhere(project_id: str) -> int:
    """Drop `project_id` from every user's assignment list.

    Called when a project is deleted, so the access file never keeps pointing
    at a project directory that no longer exists.
    """
    pid = _norm_project(project_id).lower()
    if not pid:
        return 0

    data = _load()
    users = dict(data.get("users", {}))
    changed = 0
    for uname, projects in list(users.items()):
        kept = [p for p in projects if p.lower() != pid]
        if len(kept) != len(projects):
            users[uname] = kept
            changed += 1

    if changed > 0:
        data["users"] = users
        _save(data)
    return changed
