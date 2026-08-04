"""
audit_log.py — Append-only trail of security-relevant actions, for the admin
console's Audit tab.

Backed by the same SQLite database as auth (config.AUTH_USER_STORE_URL). Not
a replacement for the plain-text logger calls already scattered through
main.py/auth.py (those go to stdout/the container's log driver and answer
"what happened, for someone tailing logs right now"); this answers "who did
what to whom, queryable from the UI, without shelling into the container or
grepping `docker compose logs`" - which is the gap an admin console actually
needs filled.

Deliberately append-only: there is no update_event() or delete_event(). An
audit trail that can be edited after the fact isn't one.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import DateTime, Integer, String, Text, create_engine, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

logger = logging.getLogger(__name__)

# Rows beyond this are pruned on write (see _prune()). An unbounded audit
# table in the same SQLite file as auth is a slow, unbounded-disk-growth
# accident waiting to happen on a long-running deployment with no external
# log shipping configured - this keeps it self-maintaining without adding an
# operational dependency (a cron job, a retention policy someone has to set
# up) just to keep a demo/small-team install healthy indefinitely.
MAX_EVENTS = 20_000
_PRUNE_BATCH = 500


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


_engine = create_engine(config.AUTH_USER_STORE_URL, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
Base.metadata.create_all(_engine)


def record(
    action: str,
    actor: str,
    target: str = "",
    workspace_id: str = "",
    success: bool = True,
    details: Optional[Dict] = None,
) -> None:
    """Append one event. Never raises - a broken audit write must not break
    the request that triggered it (an approved user, a saved setting)."""
    try:
        with _SessionLocal() as session:
            session.add(
                AuditEvent(
                    action=str(action or "unknown"),
                    actor=str(actor or "system").strip().lower(),
                    target=str(target or "") or None,
                    workspace_id=str(workspace_id or "").strip().lower() or None,
                    success=bool(success),
                    details_json=json.dumps(details, ensure_ascii=False, default=str) if details else None,
                )
            )
            session.commit()
        _prune()
    except Exception:
        logger.warning("Could not write audit event action=%s actor=%s", action, actor, exc_info=True)


def _prune() -> None:
    """Delete the oldest rows once the table exceeds MAX_EVENTS.

    Checked (a COUNT) on every write rather than run as a background job,
    which trades a small per-write cost for not needing a scheduler - the
    count query is cheap relative to the write we just did, and this table
    sees at most a few events per admin action, never per request.
    """
    with _SessionLocal() as session:
        total = session.query(AuditEvent).count()
        if total <= MAX_EVENTS:
            return
        excess = total - MAX_EVENTS
        ids = [
            row.id
            for row in session.query(AuditEvent.id)
            .order_by(AuditEvent.created_at.asc())
            .limit(max(excess, _PRUNE_BATCH))
            .all()
        ]
        if ids:
            session.query(AuditEvent).filter(AuditEvent.id.in_(ids)).delete(synchronize_session=False)
            session.commit()


def _row_to_dict(row: AuditEvent) -> Dict:
    details = None
    if row.details_json:
        try:
            details = json.loads(row.details_json)
        except Exception:
            details = row.details_json
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "action": row.action,
        "actor": row.actor,
        "target": row.target or "",
        "workspace_id": row.workspace_id or "",
        "success": bool(row.success),
        "details": details,
    }


def list_events(
    limit: int = 200,
    action: Optional[str] = None,
    actor: Optional[str] = None,
) -> List[Dict]:
    limit = max(1, min(int(limit or 200), 1000))
    with _SessionLocal() as session:
        query = session.query(AuditEvent)
        if action:
            query = query.filter(AuditEvent.action == action)
        if actor:
            query = query.filter(AuditEvent.actor == str(actor).strip().lower())
        rows = query.order_by(desc(AuditEvent.created_at)).limit(limit).all()
        return [_row_to_dict(r) for r in rows]
