"""
user_store.py — Persistent account storage behind AUTH_BACKEND=db.

Beyond username/password/role, a row now carries the two fields that decide
what the account can actually see:

  workspace_id  The tenant boundary. Every build belongs to a workspace, and a
                non-admin only ever sees builds from theirs. It lives HERE, in
                the database, rather than being sent by the client at login -
                see the note on `status` below for why that matters.

  status        pending | active | disabled. `pending` is what self-service
                registration produces: the account exists and the password is
                set, but it cannot log in and has no workspace until an admin
                approves it. This is the whole reason registration is safe to
                expose - signing up gets you a queue entry, not access.

  must_change_password
                A session for this account is good for exactly one thing:
                setting new credentials. It is what makes the built-in
                first-run admin password safe to ship as a known default, and
                it is also how an admin hands out a reset password without
                that password remaining valid indefinitely.

  token_limit   Lifetime cap on LLM tokens this account may spend, 0 meaning
                unlimited. Enforced at the single point where tokens are
                actually spent (llm_client), so there is no route that can
                bypass it by calling the model another way.

`is_active` predates `status` and is kept in sync with it so the older CLI and
any existing queries keep working; `status` is authoritative.

Schema changes are applied in-place by _migrate() rather than through a
migration tool: this is a single-table SQLite file that lives in the
container's volume, and taking on Alembic to add four nullable columns would
cost more than it's worth. _migrate() is additive only and idempotent, so it
is safe to run on every startup.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List

from sqlalchemy import Boolean, DateTime, Integer, String, create_engine, func, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"
VALID_STATUSES = (STATUS_PENDING, STATUS_ACTIVE, STATUS_DISABLED)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(120), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # --- added after the original schema; see _migrate() ---
    workspace_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=STATUS_ACTIVE, nullable=False)
    # What the person typed on the signup form. Advisory only - it tells the
    # approving admin which team they claim to be on, it does not grant it.
    requested_workspace: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # --- added for the admin console; see _migrate() ---
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 0 = unlimited. Compared against the account's lifetime total in
    # token_usage, so it survives restarts and is not per-workspace.
    token_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


def _norm(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _row_to_dict(row: User) -> Dict[str, object]:
    return {
        "username": row.username,
        "role": row.role or "",
        "workspace_id": row.workspace_id or "",
        "email": row.email or "",
        "full_name": row.full_name or "",
        "status": row.status or STATUS_ACTIVE,
        "is_active": bool(row.is_active),
        "requested_workspace": row.requested_workspace or "",
        "must_change_password": bool(row.must_change_password),
        "token_limit": int(row.token_limit or 0),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else "",
    }


class UserStore:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    # ------------------------------------------------------------ lifecycle

    def init_db(self, seed_users: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        Base.metadata.create_all(self.engine)
        self._migrate()
        if seed_users:
            self.seed_if_empty(seed_users)

    def _migrate(self) -> None:
        """Add columns introduced after the first release, then backfill.

        create_all() only creates tables that don't exist - it will not alter
        an existing `users` table, so a database created before workspaces
        existed would otherwise raise "no such column" on the first query.
        """
        inspector = inspect(self.engine)
        if "users" not in inspector.get_table_names():
            return

        existing = {col["name"] for col in inspector.get_columns("users")}
        additions = {
            "workspace_id": "VARCHAR(120)",
            "email": "VARCHAR(255)",
            "status": "VARCHAR(32)",
            "requested_workspace": "VARCHAR(120)",
            "full_name": "VARCHAR(200)",
            # No NOT NULL / DEFAULT on the ALTER: SQLite backfills existing
            # rows with NULL either way, so the defaults are applied by the
            # UPDATEs below instead of relying on column-level defaults that
            # only affect future inserts.
            "must_change_password": "BOOLEAN",
            "token_limit": "INTEGER",
            "last_login_at": "DATETIME",
        }
        added = [name for name in additions if name not in existing]

        with self.engine.begin() as conn:
            for name in added:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {additions[name]}"))

            # Backfill runs on every startup, not only when the column is new:
            # a row can also arrive with a NULL status via a direct sqlite
            # INSERT, and a NULL status would silently block that login.
            conn.execute(
                text(
                    "UPDATE users SET status = CASE WHEN is_active THEN :active "
                    "ELSE :disabled END WHERE status IS NULL OR status = ''"
                ),
                {"active": STATUS_ACTIVE, "disabled": STATUS_DISABLED},
            )
            # Same reasoning for the two new flags, and the direction matters:
            # NULL must resolve to "no forced change, no quota". A NULL read as
            # true would lock every pre-existing account out of everything
            # except the change-password screen on the first restart after
            # upgrading, and a NULL read as a zero *limit* would be worse still
            # if 0 didn't already mean unlimited.
            conn.execute(
                text("UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL")
            )
            conn.execute(text("UPDATE users SET token_limit = 0 WHERE token_limit IS NULL"))

        if added:
            logger.info("Migrated users table: added %s", ", ".join(added))

    def seed_if_empty(self, users: Dict[str, Dict[str, str]]) -> None:
        with self.SessionLocal() as session:
            if session.query(User).count() > 0:
                return

            for data in users.values():
                session.add(
                    User(
                        username=_norm(data["username"]),
                        password_hash=data["password_hash"],
                        role=data["role"],
                        workspace_id=_norm(data.get("workspace_id")) or None,
                        email=str(data.get("email") or "").strip() or None,
                        is_active=True,
                        status=STATUS_ACTIVE,
                    )
                )

            session.commit()
            logger.info("Seeded %s users into auth store", len(users))

    def count_users(self) -> int:
        with self.SessionLocal() as session:
            return int(session.query(User).count())

    def count_by_status(self) -> Dict[str, int]:
        """Population by status, with every status present even at zero.

        The admin overview renders a fixed set of tiles; a missing key would
        make "no pending requests" render as a blank tile rather than a 0.
        """
        counts = {status: 0 for status in VALID_STATUSES}
        with self.SessionLocal() as session:
            for status_value, total in (
                session.query(User.status, func.count(User.username))
                .group_by(User.status)
                .all()
            ):
                counts[_norm(status_value) or STATUS_ACTIVE] = int(total)
        return counts

    # ---------------------------------------------------------------- reads

    def get_user(self, username: str) -> Optional[Dict[str, object]]:
        """Login path: only ever returns an account cleared to sign in.

        Pending and disabled accounts return None, so no caller can
        accidentally authenticate one by forgetting to check a flag.
        """
        uname = _norm(username)
        if not uname:
            return None

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if not row:
                return None
            if (row.status or STATUS_ACTIVE) != STATUS_ACTIVE or not row.is_active:
                return None

            return {
                "username": row.username,
                "password_hash": row.password_hash,
                "role": row.role,
                "workspace_id": row.workspace_id or "",
                "email": row.email or "",
                "status": row.status,
                "must_change_password": bool(row.must_change_password),
            }

    def get_login_status(self, username: str) -> Optional[str]:
        """Status of an account regardless of whether it can log in.

        Lets the login endpoint say "awaiting approval" instead of "invalid
        credentials" to someone who registered and typed the right password.
        Only consulted after the password has already been verified.
        """
        uname = _norm(username)
        if not uname:
            return None
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            return (row.status or STATUS_ACTIVE) if row else None

    def get_password_hash(self, username: str) -> Optional[str]:
        uname = _norm(username)
        if not uname:
            return None
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            return row.password_hash if row else None

    def get_user_record(self, username: str) -> Optional[Dict[str, object]]:
        """Admin path: returns the row whatever its status (no password hash)."""
        uname = _norm(username)
        if not uname:
            return None
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            return _row_to_dict(row) if row else None

    def list_users(
        self,
        status: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        with self.SessionLocal() as session:
            query = session.query(User)
            if status:
                query = query.filter(User.status == _norm(status))
            if workspace_id:
                query = query.filter(User.workspace_id == _norm(workspace_id))
            return [_row_to_dict(row) for row in query.order_by(User.username.asc()).all()]

    def list_workspaces(self) -> List[str]:
        """Workspaces that actually have members.

        There is no workspaces table on purpose: a workspace is just the label
        shared by a set of users and a set of builds. A table would add a
        second place for the name to live, and therefore to drift.
        """
        with self.SessionLocal() as session:
            rows = (
                session.query(User.workspace_id)
                .filter(User.workspace_id.isnot(None), User.workspace_id != "")
                .distinct()
                .all()
            )
            return sorted({_norm(r[0]) for r in rows if _norm(r[0])})

    # --------------------------------------------------------------- writes

    def create_pending_user(
        self,
        username: str,
        password_hash: str,
        email: str = "",
        requested_workspace: str = "",
    ) -> Dict[str, object]:
        """Self-service registration. Never overwrites an existing account.

        Deliberately not upsert_user(): if the public registration endpoint
        could overwrite, it would be a password-reset oracle for any username
        an attacker can guess.
        """
        uname = _norm(username)
        if not uname:
            raise ValueError("username is required")

        with self.SessionLocal() as session:
            if session.get(User, uname) is not None:
                raise ValueError("username already exists")

            row = User(
                username=uname,
                password_hash=password_hash,
                role="",              # assigned at approval
                workspace_id=None,    # assigned at approval
                email=str(email or "").strip() or None,
                requested_workspace=_norm(requested_workspace) or None,
                is_active=False,
                status=STATUS_PENDING,
            )
            session.add(row)
            session.commit()
            return _row_to_dict(row)

    def upsert_user(
        self,
        username: str,
        password_hash: str,
        role: str,
        is_active: bool = True,
        workspace_id: Optional[str] = None,
        email: Optional[str] = None,
        status: Optional[str] = None,
        full_name: Optional[str] = None,
        must_change_password: Optional[bool] = None,
        token_limit: Optional[int] = None,
    ) -> Dict[str, object]:
        uname = _norm(username)
        if not uname:
            raise ValueError("username is required")

        resolved_status = _norm(status) or (STATUS_ACTIVE if is_active else STATUS_DISABLED)
        if resolved_status not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                row = User(username=uname)
                session.add(row)

            row.password_hash = password_hash
            row.role = role
            row.status = resolved_status
            row.is_active = resolved_status == STATUS_ACTIVE
            if workspace_id is not None:
                row.workspace_id = _norm(workspace_id) or None
            if email is not None:
                row.email = str(email).strip() or None
            if full_name is not None:
                row.full_name = str(full_name).strip() or None
            if must_change_password is not None:
                row.must_change_password = bool(must_change_password)
            if token_limit is not None:
                row.token_limit = max(0, int(token_limit))

            session.commit()
            return _row_to_dict(row)

    def update_user(
        self,
        username: str,
        role: Optional[str] = None,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        token_limit: Optional[int] = None,
        must_change_password: Optional[bool] = None,
    ) -> Optional[Dict[str, object]]:
        """Partial update; None means "leave this field alone"."""
        uname = _norm(username)
        if not uname:
            return None

        if status is not None and _norm(status) not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                return None

            if role is not None:
                row.role = str(role).strip()
            if workspace_id is not None:
                row.workspace_id = _norm(workspace_id) or None
            if email is not None:
                row.email = str(email).strip() or None
            if full_name is not None:
                row.full_name = str(full_name).strip() or None
            if token_limit is not None:
                row.token_limit = max(0, int(token_limit))
            if must_change_password is not None:
                row.must_change_password = bool(must_change_password)
            if status is not None:
                row.status = _norm(status)
                row.is_active = row.status == STATUS_ACTIVE

            session.commit()
            return _row_to_dict(row)

    def rename_user(self, old_username: str, new_username: str) -> Optional[Dict[str, object]]:
        """Change the username, which is also the primary key.

        Done as an UPDATE of the key rather than insert-then-delete so the row
        is never briefly absent and nothing else about the account (created_at,
        quota, status) has to be copied field by field and risk being missed.
        Callers are responsible for re-pointing anything that stores the
        username elsewhere - see auth.rename_account(), which also moves
        token usage and build ownership so a rename doesn't orphan either.
        """
        old = _norm(old_username)
        new = _norm(new_username)
        if not old or not new:
            raise ValueError("both the current and the new username are required")
        if old == new:
            return self.get_user_record(old)

        with self.SessionLocal() as session:
            if session.get(User, old) is None:
                return None
            if session.get(User, new) is not None:
                raise ValueError("username already exists")

            session.execute(
                text("UPDATE users SET username = :new WHERE username = :old"),
                {"new": new, "old": old},
            )
            session.commit()
            return _row_to_dict(session.get(User, new))

    def set_must_change_password(self, username: str, required: bool) -> bool:
        return self.update_user(username, must_change_password=required) is not None

    def get_must_change_password(self, username: str) -> bool:
        """Single indexed lookup, deliberately not routed through
        get_user_record(). Read on every authenticated request by
        main.credential_change_middleware, so it fetches one column rather
        than the whole row.
        """
        uname = _norm(username)
        if not uname:
            return False
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            return bool(row.must_change_password) if row else False

    def set_token_limit(self, username: str, limit: int) -> bool:
        return self.update_user(username, token_limit=limit) is not None

    def get_token_limit(self, username: str) -> int:
        """0 when unlimited, or when the account no longer exists.

        Read on the LLM call path, so it stays a single indexed primary-key
        lookup rather than loading the whole row.
        """
        uname = _norm(username)
        if not uname:
            return 0
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            return int(row.token_limit or 0) if row else 0

    def record_login(self, username: str) -> None:
        """Stamp a successful sign-in. Never raises.

        This is bookkeeping for the admin console, not part of authentication:
        a failure here must not turn a valid login into an error.
        """
        uname = _norm(username)
        if not uname:
            return
        try:
            with self.SessionLocal() as session:
                row = session.get(User, uname)
                if row is None:
                    return
                row.last_login_at = datetime.now(timezone.utc)
                session.commit()
        except Exception:
            logger.warning("Could not record last login for %s", uname, exc_info=True)

    def delete_user(self, username: str) -> bool:
        uname = _norm(username)
        if not uname:
            return False
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def count_admins(self, exclude: Optional[str] = None) -> int:
        """Active admins, optionally ignoring one username.

        Used to refuse the two operations that would lock everyone out of the
        admin UI: deleting or demoting the last remaining admin.
        """
        with self.SessionLocal() as session:
            query = session.query(User).filter(
                User.status == STATUS_ACTIVE,
                User.role.in_(["admin", "cto"]),
            )
            if exclude:
                query = query.filter(User.username != _norm(exclude))
            return int(query.count())

    def set_role(self, username: str, role: str) -> bool:
        return self.update_user(username, role=role) is not None

    def set_password_hash(self, username: str, password_hash: str) -> bool:
        uname = _norm(username)
        if not uname:
            return False
        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                return False
            row.password_hash = password_hash
            session.commit()
            return True

    def set_active(self, username: str, is_active: bool) -> bool:
        status = STATUS_ACTIVE if is_active else STATUS_DISABLED
        return self.update_user(username, status=status) is not None
