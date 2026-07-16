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
from typing import Dict, Optional

from sqlalchemy import DateTime, Integer, String, create_engine
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
