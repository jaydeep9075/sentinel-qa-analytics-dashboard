import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List

from sqlalchemy import Boolean, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


logger = logging.getLogger(__name__)


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


class UserStore:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def init_db(self, seed_users: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        Base.metadata.create_all(self.engine)
        if seed_users:
            self.seed_if_empty(seed_users)

    def seed_if_empty(self, users: Dict[str, Dict[str, str]]) -> None:
        with self.SessionLocal() as session:
            existing = session.query(User).count()
            if existing > 0:
                return

            for data in users.values():
                user = User(
                    username=str(data["username"]).lower(),
                    password_hash=data["password_hash"],
                    role=data["role"],
                    is_active=True,
                )
                session.add(user)

            session.commit()
            logger.info("Seeded %s users into auth store", len(users))

    def get_user(self, username: str) -> Optional[Dict[str, str]]:
        uname = str(username or "").strip().lower()
        if not uname:
            return None

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if not row or not row.is_active:
                return None

            return {
                "username": row.username,
                "password_hash": row.password_hash,
                "role": row.role,
            }

    def upsert_user(self, username: str, password_hash: str, role: str, is_active: bool = True) -> Dict[str, str]:
        uname = str(username or "").strip().lower()
        if not uname:
            raise ValueError("username is required")

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                row = User(
                    username=uname,
                    password_hash=password_hash,
                    role=role,
                    is_active=is_active,
                )
                session.add(row)
            else:
                row.password_hash = password_hash
                row.role = role
                row.is_active = is_active

            session.commit()
            return {
                "username": row.username,
                "role": row.role,
                "is_active": bool(row.is_active),
            }

    def set_role(self, username: str, role: str) -> bool:
        uname = str(username or "").strip().lower()
        if not uname:
            return False

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                return False
            row.role = role
            session.commit()
            return True

    def set_password_hash(self, username: str, password_hash: str) -> bool:
        uname = str(username or "").strip().lower()
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
        uname = str(username or "").strip().lower()
        if not uname:
            return False

        with self.SessionLocal() as session:
            row = session.get(User, uname)
            if row is None:
                return False
            row.is_active = is_active
            session.commit()
            return True

    def list_users(self) -> List[Dict[str, object]]:
        with self.SessionLocal() as session:
            rows = session.query(User).order_by(User.username.asc()).all()
            return [
                {
                    "username": row.username,
                    "role": row.role,
                    "is_active": bool(row.is_active),
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
                for row in rows
            ]
