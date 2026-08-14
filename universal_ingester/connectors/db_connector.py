# connectors/db_connector.py
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import List, Dict, Any, Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .base import BaseConnector

logger = logging.getLogger(__name__)

# Tables stream in chunks so a huge table never loads fully in memory.
DB_CHUNK_ROWS = int(os.getenv("INGEST_DB_CHUNK_ROWS", "50000"))
# Dialect-agnostic bound on the initial connection attempt. SQLAlchemy's
# per-driver connect_args (connect_timeout, etc.) differ by dialect and
# guessing the wrong one raises "unexpected keyword argument" on drivers that
# don't accept it - a thread-level timeout works the same way for every
# dialect without needing to know which one is in play.
DB_CONNECT_TIMEOUT_SECONDS = int(os.getenv("INGEST_DB_CONNECT_TIMEOUT_SECONDS", "15"))

_PASSWORD_IN_URL = re.compile(r"(://[^:/?#]+:)[^@]+(@)")


def _redact(connection_string: str) -> str:
    """Strip a password out of a SQLAlchemy URL before it can end up in a
    raised exception, a log line, or an audit record."""
    return _PASSWORD_IN_URL.sub(r"\1***\2", str(connection_string or ""))


class DBConnectionError(RuntimeError):
    """Raised for anything that stops a database connector from reaching or
    reading its target - never carries a raw, unredacted connection string."""


class DBConnector(BaseConnector):
    def __init__(
        self,
        connection_string: str,
        tables: Optional[List[str]] = None,
        connect_args: Optional[Dict] = None,
        batch_size: Optional[int] = None,
    ):
        """
        connection_string: SQLAlchemy connection string
        tables: optional list of tables to fetch; if None, fetch all tables.
        connect_args: additional arguments to pass to create_engine (e.g., for SSL)
        batch_size: rows fetched per streamed chunk (default DB_CHUNK_ROWS)
        """
        self.connection_string = connection_string
        self.redacted = _redact(connection_string)
        self.tables = tables
        self.batch_size = int(batch_size) if batch_size else DB_CHUNK_ROWS

        try:
            self.engine = create_engine(connection_string, connect_args=connect_args or {})
        except Exception as exc:
            raise DBConnectionError(
                f"Could not build a database engine for {self.redacted}: {exc}"
            ) from exc

        self._verify_connectable()

        try:
            self.inspector = inspect(self.engine)
        except SQLAlchemyError as exc:
            raise DBConnectionError(f"Could not inspect schema for {self.redacted}: {exc}") from exc

    def _verify_connectable(self) -> None:
        """A bounded, dialect-agnostic connectivity probe. Runs in a worker
        thread so a hung TCP handshake can't block the caller forever - the
        underlying connection attempt has no cooperative cancellation, so the
        thread itself may keep trying in the background, but the caller gets
        a clear timeout error instead of hanging."""

        def _connect():
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(_connect).result(timeout=DB_CONNECT_TIMEOUT_SECONDS)
        except FutureTimeoutError as exc:
            raise DBConnectionError(
                f"Timed out after {DB_CONNECT_TIMEOUT_SECONDS}s connecting to {self.redacted} "
                f"- check host/port and network reachability"
            ) from exc
        except SQLAlchemyError as exc:
            raise DBConnectionError(self._classify(exc)) from exc
        except ModuleNotFoundError as exc:
            raise DBConnectionError(
                f"Database driver not installed for {self.redacted}: {exc}"
            ) from exc

    def _classify(self, exc: Exception) -> str:
        """A short, actionable message instead of a raw driver traceback -
        the raw exception text is still appended (redacted) since drivers
        often put the real cause (bad password, unknown host, etc.) there."""
        text_lower = str(exc).lower()
        if any(k in text_lower for k in ("password", "authentication", "access denied", "login failed")):
            reason = "Authentication failed - check username/password"
        elif any(k in text_lower for k in ("could not translate host", "name or service not known", "getaddrinfo", "unknown host")):
            reason = "Could not resolve host - check the hostname"
        elif any(k in text_lower for k in ("connection refused", "timed out", "could not connect")):
            reason = "Could not reach the database - check host/port and firewall rules"
        elif "does not exist" in text_lower and "database" in text_lower:
            reason = "Database does not exist"
        else:
            reason = "Could not connect to the database"
        return f"{reason} ({self.redacted}): {_redact(str(exc))}"

    def test_connection(self) -> Dict[str, Any]:
        """Connect + list tables, no data fetch. Used both as a UI-facing
        'Test Connection' probe and as a cheap sanity check before a full
        ingestion run."""
        table_names = self.inspector.get_table_names()
        return {
            "success": True,
            "tables": table_names[:50],
            "table_count": len(table_names),
        }

    def _resolve_tables(self) -> List[str]:
        available = self.inspector.get_table_names()
        if self.tables is None:
            if not available:
                raise DBConnectionError(
                    f"Connected to {self.redacted}, but the database has no tables to ingest"
                )
            return available

        requested = [t.strip() for t in self.tables if str(t).strip()]
        missing = [t for t in requested if t not in available]
        if missing:
            preview = ", ".join(available[:20]) or "(none)"
            raise DBConnectionError(
                f"Requested table(s) not found: {', '.join(missing)}. "
                f"Available tables include: {preview}"
            )
        if not requested:
            raise DBConnectionError("No valid table names were provided")
        return requested

    def _stream_table(self, table: str):
        for chunk in pd.read_sql_table(table, self.engine, chunksize=self.batch_size):
            yield chunk

    def fetch(self) -> List[Dict[str, Any]]:
        """Expose each table as a streamed structured dataset; the engine
        writes batches as they arrive."""
        table_names = self._resolve_tables()

        datasets = []
        for table in table_names:
            datasets.append({
                'name': table,
                'data': None,
                'data_iter': self._stream_table(table),
                'type': 'structured',
                'metadata': {'table': table, 'streamed': True},
            })
        return datasets

    def close(self) -> None:
        """Release the pooled engine (open file handle for SQLite, open
        sockets for network databases). Called by the ingester once every
        streamed dataset from fetch() has been fully consumed."""
        try:
            self.engine.dispose()
        except Exception:
            logger.warning("Error disposing engine for %s", self.redacted, exc_info=True)
