"""
permissions.py — What each account ROLE is allowed to do.

Not to be confused with roles/*.md (role_manager.py), which are LLM chat
personas selected per-request via the `x-role` header and have nothing to do
with authorization. This module is about services.user_store.User.role: the
account-level role assigned by an admin, which decides what buttons the
frontend shows and what the backend actually permits.

Two things intentionally stay OUTSIDE this matrix because they are not
role questions:

  * Workspace visibility (build_owner.can_view / the ingestion-visibility
    middleware in main.py) - who can see which TENANT, not which ACTION.
  * Build deletion ownership (build_owner.can_delete) - "you may delete
    builds" is a role permission (PERM_DATA_DELETE below); "you may delete
    THIS build" additionally depends on who created it, which is a
    per-object check this module doesn't have the data for.

A role's entry is a set of permission strings, or the sentinel {"*"} meaning
"everything, including permissions added to this file later" - used for
admin/cto so a new permission doesn't have to be back-filled into their row
to keep working the way an admin naturally expects.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException

from .auth import ADMIN_ROLES, get_current_user

logger = logging.getLogger(__name__)

PERM_DATA_VIEW = "data.view"                 # dashboards, chat, chart, quality
PERM_DATA_INGEST = "data.ingest"             # trigger a new build
PERM_DATA_DELETE = "data.delete"             # delete a build (also needs ownership)
PERM_USAGE_VIEW_OWN = "usage.view_own"       # see your own token spend
PERM_USAGE_VIEW_ALL = "usage.view_all"       # admin usage tab, all accounts
PERM_USERS_MANAGE = "users.manage"           # create/approve/edit/delete accounts
PERM_SETTINGS_MANAGE = "settings.manage"     # LLM provider/model/key
PERM_AUDIT_VIEW = "audit.view"               # admin audit log

ALL_PERMISSIONS = (
    PERM_DATA_VIEW,
    PERM_DATA_INGEST,
    PERM_DATA_DELETE,
    PERM_USAGE_VIEW_OWN,
    PERM_USAGE_VIEW_ALL,
    PERM_USERS_MANAGE,
    PERM_SETTINGS_MANAGE,
    PERM_AUDIT_VIEW,
)

_WILDCARD = frozenset({"*"})

# Every role the system understands. Kept here (not just in the frontend's
# ROLES array) so admin_create_user / admin_update_user can reject a typo'd
# role at the API boundary instead of silently creating an account with a
# role string that matches nothing in this table and therefore has NO
# permissions - which would look like a bug, not a rejected request.
KNOWN_ROLES = ("admin", "cto", "qa-manager", "qa-engineer", "developer", "viewer")

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    # Full administrative control. cto is a second admin-equivalent role
    # rather than admin's synonym so an org can title the account "CTO" in
    # the UI while it behaves identically - see auth.ADMIN_ROLES, which this
    # mirrors on purpose.
    "admin": _WILDCARD,
    "cto": _WILDCARD,
    # Runs the QA process day to day: reads data, brings in new builds,
    # cleans up old ones. Not user administration or LLM configuration -
    # those are organizational decisions, not QA ones. Token spend visibility
    # is admin-only (see PERM_USAGE_VIEW_ALL) - non-admin roles have no usage
    # permission at all, not even their own, by design.
    "qa-manager": frozenset({PERM_DATA_VIEW, PERM_DATA_INGEST, PERM_DATA_DELETE}),
    "qa-engineer": frozenset({PERM_DATA_VIEW, PERM_DATA_INGEST, PERM_DATA_DELETE}),
    # Consumes the analysis; doesn't own the pipeline that produces it.
    "developer": frozenset({PERM_DATA_VIEW}),
    "viewer": frozenset({PERM_DATA_VIEW}),
}


def _normalize_role(role: Optional[str]) -> str:
    return str(role or "").strip().lower()


def permissions_for_role(role: Optional[str]) -> frozenset[str]:
    granted = ROLE_PERMISSIONS.get(_normalize_role(role))
    if granted is None:
        # An unrecognised role (a hand-edited DB row, a role removed from
        # this table after being assigned) gets nothing rather than crashing
        # a request - fail closed, and it's visible in /auth/permissions as
        # an empty list rather than a 500.
        logger.warning("Unknown role '%s' - granting no permissions", role)
        return frozenset()
    return granted


def has_permission(user: Optional[dict], permission: str) -> bool:
    granted = permissions_for_role((user or {}).get("role"))
    return granted is _WILDCARD or permission in granted


def require_permission(permission: str):
    """FastAPI dependency factory: `Depends(require_permission(PERM_X))`.

    A factory rather than a single dependency because each route needs a
    DIFFERENT permission checked - the returned closure is what actually runs
    as the dependency, with `permission` fixed by the call that created it.
    """

    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Your role does not have the '{permission}' permission",
            )
        return current_user

    return _check


def permissions_payload(user: Optional[dict]) -> dict:
    """Shape returned by GET /auth/permissions - what the frontend gates on
    instead of hardcoding role-name comparisons in components."""
    role = _normalize_role((user or {}).get("role"))
    granted = permissions_for_role(role)
    return {
        "role": role,
        "is_admin": role in ADMIN_ROLES,
        "permissions": sorted(ALL_PERMISSIONS) if granted is _WILDCARD else sorted(granted),
    }
