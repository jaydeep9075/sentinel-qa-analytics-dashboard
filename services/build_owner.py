"""
build_owner.py — Which workspace does a build belong to, and who may see it.

A build is a directory under DATA_BASE_PATH. Ownership is recorded as a small
`owner.json` written inside that directory at ingestion time:

    {"workspace_id": "platform", "created_by": "alice",
     "source": "auto-ingest", "created_at": "2026-..."}

Why a file next to the data rather than a row in a table:

  * The build directory is already the unit that gets copied, archived, backed
    up and deleted. Ownership travels with it for free - move the folder to
    another install and it still knows whose it is. A separate table would
    need its own migration and would go stale the moment someone moved,
    restored, or hand-deleted a build directory.
  * `docker compose run --rm ingest` and the auto-ingest watcher write builds
    without any database session in scope.

Builds created before this existed have no owner.json. Rather than making them
invisible (which would silently hide an existing install's entire history) or
visible to everyone (which would defeat the point), they are attributed to
config.LEGACY_BUILDS_WORKSPACE - the default workspace unless configured
otherwise. Set that to an unused label to quarantine them to admins.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

OWNER_FILENAME = "owner.json"

# A build id becomes a path segment, so it is validated rather than trusted.
# Anything outside this alphabet - notably "/", "\" and ".." - is rejected
# before it can be joined onto DATA_BASE_PATH.
_SAFE_BUILD_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def is_safe_build_id(build_id: str) -> bool:
    value = str(build_id or "")
    return bool(_SAFE_BUILD_ID.match(value)) and value not in {".", ".."}


def resolve_build_path(build_id: str) -> Optional[Path]:
    """DATA_BASE_PATH/build_id, or None if build_id could escape the base.

    Two independent checks - the character whitelist and a resolved-path
    containment test - because the first is easy to reason about and the
    second catches anything the first didn't anticipate (symlinks, platform
    path quirks).
    """
    if not is_safe_build_id(build_id):
        return None

    base = config.DATA_BASE_PATH.resolve()
    candidate = (base / build_id).resolve()
    if candidate != base and base not in candidate.parents:
        return None
    return candidate


def _normalize(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def write_owner(
    build_id: str,
    workspace_id: str,
    created_by: str = "",
    source: str = "",
    display_name: str = "",
) -> None:
    """Record ownership. Best-effort: never fail an ingestion over this.

    A build that ingested successfully but lost its owner.json falls back to
    the legacy workspace, which is recoverable. An ingestion aborted because
    a metadata write failed is not.
    """
    path = resolve_build_path(build_id)
    if path is None:
        logger.warning("Refusing to write owner metadata for unsafe build id %r", build_id)
        return

    payload = {
        "workspace_id": _normalize(workspace_id) or config.DEFAULT_WORKSPACE_ID,
        "created_by": _normalize(created_by),
        "source": str(source or ""),
        "display_name": str(display_name or "").strip()[:200],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        path.mkdir(parents=True, exist_ok=True)
        (path / OWNER_FILENAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        logger.warning("Could not write %s for %s", OWNER_FILENAME, build_id, exc_info=True)


def read_owner(build_path: Path) -> dict:
    """Ownership for a build directory, with legacy fallback applied."""
    legacy = {
        "workspace_id": config.LEGACY_BUILDS_WORKSPACE,
        "created_by": "",
        "source": "legacy",
        "display_name": "",
        "created_at": "",
        "is_legacy": True,
    }

    owner_file = build_path / OWNER_FILENAME
    if not owner_file.exists():
        return legacy

    try:
        data = json.loads(owner_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Unreadable %s in %s - treating as legacy", OWNER_FILENAME, build_path.name)
        return legacy

    if not isinstance(data, dict):
        return legacy

    return {
        "workspace_id": _normalize(data.get("workspace_id")) or config.LEGACY_BUILDS_WORKSPACE,
        "created_by": _normalize(data.get("created_by")),
        "source": str(data.get("source") or ""),
        "display_name": str(data.get("display_name") or ""),
        "created_at": str(data.get("created_at") or ""),
        "is_legacy": False,
    }


def rename_creator(old_username: str, new_username: str) -> int:
    """Rewrite `created_by` in every owner.json that names old_username.

    Called by auth.rename_account(). Without this, can_delete()'s "creator or
    admin" check would compare the new session's username against a
    created_by that still says the old one, and the rename would silently
    cost that person delete rights on everything they'd built before it.

    Walks every top-level build directory once; best-effort per file so one
    unreadable owner.json doesn't abort the rest. Cheap even at a few
    thousand builds since it's a JSON read/write, not a query.
    """
    old = _normalize(old_username)
    new = _normalize(new_username)
    if not old or not new or old == new:
        return 0

    base = config.DATA_BASE_PATH
    if not base.exists():
        return 0

    updated = 0
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        owner_file = entry / OWNER_FILENAME
        if not owner_file.exists():
            continue
        try:
            data = json.loads(owner_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or _normalize(data.get("created_by")) != old:
                continue
            data["created_by"] = new
            owner_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            updated += 1
        except Exception:
            logger.warning("Could not update created_by in %s", owner_file, exc_info=True)

    if updated:
        logger.info("Reassigned created_by from '%s' to '%s' on %d build(s)", old, new, updated)
    return updated


# Visibility used to live here as can_view(), comparing the build's workspace
# to the caller's. It has moved to project assignment (services/project_access
# + project_builds), because two independent invisible filters is one too many:
# an account could be granted a project and still not see half of its builds,
# with nothing in any screen explaining why. owner.json is still the record of
# who created a build and which workspace produced it - that is what can_delete
# below is built on, and what the UI labels rows with.


def can_delete(owner: dict, user: dict) -> bool:
    """Deletion is irreversible (shutil.rmtree), so it is narrower than
    viewing. Admins can delete anything. Beyond that:

      * A build someone ingested by hand belongs to that person - a colleague
        in the same workspace can look at it but not destroy it.
      * A build with no human creator came from automation (the drop-box
        watcher or a CI upload) on behalf of the whole team, so any member of
        its workspace can delete it. Otherwise nightly CI builds would pile up
        until disk pressure forced an admin to intervene, which is the kind of
        friction that ends with everyone being made an admin.
      * Legacy builds (no owner.json, so attributed by configuration rather
        than by record) stay admin-only. We don't actually know whose they
        are, and that is the wrong footing for an irreversible operation.
    """
    if str((user or {}).get("role") or "").strip().lower() in {"admin", "cto"}:
        return True
    if owner.get("is_legacy"):
        return False
    if _normalize(owner.get("workspace_id")) != _normalize((user or {}).get("workspace_id")):
        # Deleting is irreversible, so it keeps the narrower rule: you may
        # look at a colleague's build through a shared project, but destroying
        # one still requires having produced it.
        return False

    created_by = _normalize(owner.get("created_by"))
    if not created_by:
        return True  # automation-produced, owned by the workspace
    return created_by == _normalize((user or {}).get("username"))
