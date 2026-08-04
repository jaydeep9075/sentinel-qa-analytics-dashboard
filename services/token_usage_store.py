"""
token_usage_store.py — Persistent, shared token usage accounting.

Backed by the same SQLite database as user auth (config.AUTH_USER_STORE_URL),
so usage totals are consistent for a given user regardless of which machine
talks to that database — unlike the previous implementation, which wrote to
a JSON file under data/ that was tracked in git and diverged independently
per local checkout.

Only per-model rows are stored (the source of truth); aggregate "totals"
are computed on read by summing across models for the user, so there is
no second copy of the numbers that can drift out of sync.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


class Base(DeclarativeBase):
    pass


class TokenUsage(Base):
    __tablename__ = "token_usage"

    workspace_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    model: Mapped[str] = mapped_column(String(200), primary_key=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


_engine = create_engine(config.AUTH_USER_STORE_URL, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
Base.metadata.create_all(_engine)


def _norm_user(user_id: Optional[str]) -> str:
    return str(user_id or "").strip().lower() or "anonymous"


def _norm_workspace(workspace_id: Optional[str]) -> str:
    return (
        str(workspace_id or "").strip().lower()
        or str(getattr(config, "DEFAULT_WORKSPACE_ID", "default") or "default").strip().lower()
    )


def _empty_totals() -> Dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "calls": 0,
    }


def record_usage(
    user_id: Optional[str],
    workspace_id: Optional[str],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    uid = _norm_user(user_id)
    wid = _norm_workspace(workspace_id)
    model_key = str(model or "unknown").strip() or "unknown"

    with _LOCK:
        with _SessionLocal() as session:
            row = session.get(TokenUsage, (wid, uid, model_key))
            if row is None:
                row = TokenUsage(
                    workspace_id=wid,
                    user_id=uid,
                    model=model_key,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    calls=0,
                )
                session.add(row)

            row.prompt_tokens = int(row.prompt_tokens or 0) + int(prompt_tokens or 0)
            row.completion_tokens = int(row.completion_tokens or 0) + int(completion_tokens or 0)
            row.total_tokens = int(row.total_tokens or 0) + int(total_tokens or 0)
            row.calls = int(row.calls or 0) + 1
            row.updated_at = datetime.now(timezone.utc)

            session.commit()


def get_usage(user_id: Optional[str], workspace_id: Optional[str]) -> Dict:
    uid = _norm_user(user_id)
    wid = _norm_workspace(workspace_id)

    with _SessionLocal() as session:
        rows = (
            session.query(TokenUsage)
            .filter(TokenUsage.workspace_id == wid, TokenUsage.user_id == uid)
            .all()
        )

        if not rows:
            return {
                "totals": _empty_totals(),
                "by_model": {},
                "scope": {"workspace_id": wid, "user_id": uid},
            }

        totals = _empty_totals()
        by_model: Dict[str, Dict[str, int]] = {}
        latest_updated = ""
        for row in rows:
            model_totals = {
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
                "calls": int(row.calls or 0),
            }
            by_model[row.model] = model_totals
            for key in totals:
                totals[key] += model_totals[key]
            updated_iso = row.updated_at.isoformat() if row.updated_at else ""
            if updated_iso > latest_updated:
                latest_updated = updated_iso

        return {
            "totals": totals,
            "by_model": by_model,
            "scope": {"workspace_id": wid, "user_id": uid},
            "updated_at": latest_updated,
        }


def get_lifetime_total(user_id: Optional[str]) -> int:
    """This account's total tokens spent across every workspace and model.

    Quota enforcement is per-ACCOUNT, not per-workspace: a user who moves
    between workspaces (or whose account predates a workspace change)
    shouldn't get a fresh budget just by switching. This is the one number
    compared against users.token_limit - see llm_client._check_quota().
    """
    uid = _norm_user(user_id)
    with _SessionLocal() as session:
        total = (
            session.query(func.coalesce(func.sum(TokenUsage.total_tokens), 0))
            .filter(TokenUsage.user_id == uid)
            .scalar()
        )
        return int(total or 0)


def list_usage_by_user() -> List[Dict]:
    """One row per account, summed across workspaces and models.

    Backs the admin Usage tab - the accounting question there is "how much
    has this person spent", not "how much did this workspace spend on this
    model", which is what the per-scope rows in TokenUsage are shaped for.
    """
    with _SessionLocal() as session:
        rows = (
            session.query(
                TokenUsage.user_id,
                func.sum(TokenUsage.prompt_tokens),
                func.sum(TokenUsage.completion_tokens),
                func.sum(TokenUsage.total_tokens),
                func.sum(TokenUsage.calls),
                func.max(TokenUsage.updated_at),
            )
            .group_by(TokenUsage.user_id)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
            .all()
        )
        return [
            {
                "user_id": user_id,
                "prompt_tokens": int(prompt or 0),
                "completion_tokens": int(completion or 0),
                "total_tokens": int(total or 0),
                "calls": int(calls or 0),
                "updated_at": updated_at.isoformat() if updated_at else "",
            }
            for user_id, prompt, completion, total, calls, updated_at in rows
        ]


def reset_usage(user_id: str) -> int:
    """Delete every usage row for one account. Returns rows removed.

    Distinct from resetting a *quota* (users.token_limit stays whatever it
    was) - this clears the spend the quota is measured against, e.g. after
    raising a user's limit and wanting their counter to start clean.
    """
    uid = _norm_user(user_id)
    with _LOCK:
        with _SessionLocal() as session:
            deleted = (
                session.query(TokenUsage).filter(TokenUsage.user_id == uid).delete()
            )
            session.commit()
            return int(deleted)


def rename_user(old_user_id: str, new_user_id: str) -> None:
    """Re-key every usage row from old_user_id to new_user_id.

    Called by auth.rename_account() when an admin or the account owner
    changes a username. Merges into any row the new name already owns
    (workspace_id, model) rather than raising a primary-key conflict, since
    the new username could in theory already have usage of its own (e.g. it
    briefly existed before, or the rename is walking two accounts together).
    """
    old = _norm_user(old_user_id)
    new = _norm_user(new_user_id)
    if not old or not new or old == new:
        return

    with _LOCK:
        with _SessionLocal() as session:
            old_rows = session.query(TokenUsage).filter(TokenUsage.user_id == old).all()
            for row in old_rows:
                existing = session.get(TokenUsage, (row.workspace_id, new, row.model))
                if existing is None:
                    row.user_id = new
                else:
                    existing.prompt_tokens = int(existing.prompt_tokens or 0) + int(row.prompt_tokens or 0)
                    existing.completion_tokens = int(existing.completion_tokens or 0) + int(row.completion_tokens or 0)
                    existing.total_tokens = int(existing.total_tokens or 0) + int(row.total_tokens or 0)
                    existing.calls = int(existing.calls or 0) + int(row.calls or 0)
                    existing.updated_at = datetime.now(timezone.utc)
                    session.delete(row)
            session.commit()
