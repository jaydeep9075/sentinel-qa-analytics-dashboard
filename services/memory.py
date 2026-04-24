import json
import uuid
import logging
import pandas as pd
import pyarrow as pa
from datetime import datetime, timezone
from typing import Dict, Optional
from . import state, config

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Chat History Helpers
# ----------------------------------------------------------------------
def _ensure_chat_table():
    """Create chat_history table with correct schema if missing or invalid."""
    if not state.lance_db:
        return
    table_name = "chat_history"
    if table_name in state.lance_db.table_names():
        # Check schema – if id is null, drop and recreate
        tbl = state.lance_db.open_table(table_name)
        schema = tbl.schema
        id_field = schema.field("id")
        if str(id_field.type) == "null":
            logger.warning(f"{table_name} has null-type columns, dropping and recreating")
            state.lance_db.drop_table(table_name)
        else:
            return
    # Create fresh with correct schema
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("session_id", pa.string()),
        pa.field("type", pa.string()),
        pa.field("prompt", pa.string()),
        pa.field("response", pa.string()),
        pa.field("config", pa.string()),
        pa.field("created_at", pa.string()),
        pa.field("metadata", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)
    logger.info(f"Created {table_name} with correct schema")

def get_chat_history(session_id: str, limit: int = config.MAX_HISTORY_TURNS):
    if not state.lance_db or "chat_history" not in state.lance_db.table_names():
        return []
    try:
        table = state.lance_db.open_table("chat_history")
        df = table.to_pandas()
        if df.empty:
            return []
        session_df = df[df["session_id"] == session_id]
        if session_df.empty:
            return []
        session_df = session_df.sort_values("created_at", ascending=False).head(limit)
        return session_df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        return []

def store_chat_message(session_id: str, role: str, content: str, metadata: Dict = None):
    if not state.lance_db:
        return
    _ensure_chat_table()
    try:
        table = state.lance_db.open_table("chat_history")
        record = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "type": role,
            "prompt": content if role == "user" else "",
            "response": content if role == "assistant" else "",
            "config": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": json.dumps(metadata or {})
        }
        table.add([record])
    except Exception as e:
        logger.error(f"Error storing chat message: {e}")

# ----------------------------------------------------------------------
# Chart History Helpers
# ----------------------------------------------------------------------
def _ensure_chart_table():
    """Create chart_history table with correct schema if missing or invalid."""
    if not state.lance_db:
        return
    table_name = "chart_history"
    if table_name in state.lance_db.table_names():
        # Check schema – if id is null, drop and recreate
        tbl = state.lance_db.open_table(table_name)
        schema = tbl.schema
        id_field = schema.field("id")
        if str(id_field.type) == "null":
            logger.warning(f"{table_name} has null-type columns, dropping and recreating")
            state.lance_db.drop_table(table_name)
        else:
            return
    # Create fresh with correct schema
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("session_id", pa.string()),
        pa.field("type", pa.string()),
        pa.field("prompt", pa.string()),
        pa.field("response", pa.string()),
        pa.field("config", pa.string()),
        pa.field("created_at", pa.string()),
        pa.field("metadata", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)
    logger.info(f"Created {table_name} with correct schema")

def get_chart_history(session_id: str, limit: int = 10):
    if not state.lance_db or "chart_history" not in state.lance_db.table_names():
        return []
    try:
        table = state.lance_db.open_table("chart_history")
        df = table.to_pandas()
        if df.empty:
            return []
        session_df = df[df["session_id"] == session_id]
        if session_df.empty:
            return []
        session_df = session_df.sort_values("created_at", ascending=False).head(limit)
        return session_df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error retrieving chart history: {e}")
        return []

def store_chart(session_id: str, prompt: str, config_json: str, metadata: Dict = None):
    if not state.lance_db:
        logger.error("store_chart: state.lance_db is None")
        return False

    try:
        # Ensure chart_history exists with correct schema
        _ensure_chart_table()
        table = state.lance_db.open_table("chart_history")
        record = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "type": "chart",
            "prompt": prompt,
            "response": "",
            "config": config_json,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": json.dumps(metadata or {})
        }
        table.add([record])
        logger.info(f"✅ Stored chart for session {session_id} with ID {record['id']}")
        return True
    except Exception as e:
        logger.error(f"Error storing chart: {e}")
        import traceback
        traceback.print_exc()
        return False