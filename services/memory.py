import json
import uuid
import logging
import re
from collections import Counter
from itertools import combinations
import pandas as pd
import pyarrow as pa
from datetime import datetime, timezone
from typing import Dict, Optional, List, Set
from . import state, config

logger = logging.getLogger(__name__)

_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "how", "i", "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "with", "show", "get", "give", "me",
    "my", "our", "we", "you", "please", "chart", "charts", "query", "data", "test", "tests",
}


def _norm_user(user_id: Optional[str]) -> str:
    u = str(user_id or "").strip().lower()
    return u or "anonymous"


def _norm_ingestion(ingestion_id: Optional[str]) -> str:
    return str(ingestion_id or "").strip()


def _norm_workspace(workspace_id: Optional[str]) -> str:
    ws = str(workspace_id or "").strip().lower()
    if not ws:
        ws = str(getattr(config, "DEFAULT_WORKSPACE_ID", "default") or "default").strip().lower()
    return ws or "default"


def _safe_json_loads(raw: str, fallback):
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _extract_keywords(text: str, max_terms: int = 12) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]{3,}", str(text or "").lower())
    terms = []
    seen = set()
    for token in tokens:
        if token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def _text_overlap_score(query_terms: Set[str], candidate_terms: Set[str]) -> float:
    if not query_terms or not candidate_terms:
        return 0.0
    intersection = len(query_terms.intersection(candidate_terms))
    if intersection == 0:
        return 0.0
    return intersection / max(len(query_terms), 1)


def _sql_escape(value: str) -> str:
    return str(value).replace("'", "''")


def _eq_clause(column: str, value: str) -> str:
    return f"{column} = '{_sql_escape(value)}'"


def _filtered_pandas(table, clauses: List[str]) -> pd.DataFrame:
    """Push row filtering down to LanceDB instead of loading the whole
    table into pandas and masking client-side. These tables only ever grow
    (no retention/pruning), so an unfiltered table.to_pandas() was pulling
    every user's/workspace's/ingestion's rows into memory on every single
    read - cost climbs with total usage, not with what any one caller
    actually needs. Sorting/limiting by created_at still happens
    client-side on the (much smaller) filtered result, since LanceDB's
    .limit() is a physical row-scan cap, not an ORDER BY pushdown - using
    it before sorting would silently return the wrong N rows."""
    if not clauses:
        return table.to_pandas()
    return table.search().where(" AND ".join(clauses)).to_pandas()

def _ensure_chat_table():
    if state.lance_db is None:
        return
    table_name = "chat_history"
    if table_name in state.lance_db.table_names():
        tbl = state.lance_db.open_table(table_name)
        schema = tbl.schema
        existing_cols = set(schema.names)
        required_cols = {
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "type",
            "prompt", "response", "config", "created_at", "metadata",
        }
        should_migrate = False
        if "id" in existing_cols and str(schema.field("id").type) == "null":
            should_migrate = True
        if not required_cols.issubset(existing_cols):
            should_migrate = True

        if not should_migrate:
            return

        logger.warning(f"{table_name} schema mismatch, migrating table")
        old_df = tbl.to_pandas()
        for col in required_cols:
            if col not in old_df.columns:
                if col in {"user_id"}:
                    old_df[col] = "anonymous"
                elif col in {"workspace_id"}:
                    old_df[col] = _norm_workspace(None)
                elif col in {"ingestion_id", "session_id", "type", "prompt", "response", "config", "metadata"}:
                    old_df[col] = ""
                elif col == "created_at":
                    old_df[col] = datetime.now(timezone.utc).isoformat()
                elif col == "id":
                    old_df[col] = [str(uuid.uuid4()) for _ in range(len(old_df))]

        old_df = old_df[[
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "type",
            "prompt", "response", "config", "created_at", "metadata",
        ]]
        state.lance_db.drop_table(table_name)
        state.lance_db.create_table(table_name, old_df)
        return
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("workspace_id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("ingestion_id", pa.string()),
        pa.field("session_id", pa.string()),
        pa.field("type", pa.string()),
        pa.field("prompt", pa.string()),
        pa.field("response", pa.string()),
        pa.field("config", pa.string()),
        pa.field("created_at", pa.string()),
        pa.field("metadata", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)

def _ensure_learning_signal_table():
    if state.lance_db is None:
        return
    table_name = "learning_signals"
    if table_name in state.lance_db.table_names():
        tbl = state.lance_db.open_table(table_name)
        existing_cols = set(tbl.schema.names)
        required_cols = {
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "kind",
            "prompt", "response", "keywords", "frequency", "created_at", "updated_at",
        }
        if required_cols.issubset(existing_cols):
            return
        old_df = tbl.to_pandas()
        for col in required_cols:
            if col not in old_df.columns:
                if col == "workspace_id":
                    old_df[col] = _norm_workspace(None)
                elif col in {"user_id"}:
                    old_df[col] = "anonymous"
                elif col in {"ingestion_id", "session_id", "kind", "prompt", "response", "keywords"}:
                    old_df[col] = ""
                elif col in {"frequency"}:
                    old_df[col] = 1
                elif col in {"created_at", "updated_at"}:
                    old_df[col] = datetime.now(timezone.utc).isoformat()
                elif col == "id":
                    old_df[col] = [str(uuid.uuid4()) for _ in range(len(old_df))]
        old_df = old_df[[
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "kind",
            "prompt", "response", "keywords", "frequency", "created_at", "updated_at",
        ]]
        state.lance_db.drop_table(table_name)
        state.lance_db.create_table(table_name, old_df)
        return
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("workspace_id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("ingestion_id", pa.string()),
        pa.field("session_id", pa.string()),
        pa.field("kind", pa.string()),
        pa.field("prompt", pa.string()),
        pa.field("response", pa.string()),
        pa.field("keywords", pa.string()),
        pa.field("frequency", pa.int32()),
        pa.field("created_at", pa.string()),
        pa.field("updated_at", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)


def _ensure_knowledge_graph_table():
    if state.lance_db is None:
        return
    table_name = "knowledge_graph_edges"
    if table_name in state.lance_db.table_names():
        tbl = state.lance_db.open_table(table_name)
        existing_cols = set(tbl.schema.names)
        required_cols = {
            "id", "workspace_id", "user_id", "ingestion_id", "source",
            "target", "weight", "edge_type", "updated_at",
        }
        if required_cols.issubset(existing_cols):
            return
        old_df = tbl.to_pandas()
        for col in required_cols:
            if col not in old_df.columns:
                if col == "workspace_id":
                    old_df[col] = _norm_workspace(None)
                elif col in {"user_id"}:
                    old_df[col] = "anonymous"
                elif col in {"ingestion_id", "source", "target", "edge_type"}:
                    old_df[col] = ""
                elif col == "weight":
                    old_df[col] = 1
                elif col == "updated_at":
                    old_df[col] = datetime.now(timezone.utc).isoformat()
                elif col == "id":
                    old_df[col] = [str(uuid.uuid4()) for _ in range(len(old_df))]
        old_df = old_df[[
            "id", "workspace_id", "user_id", "ingestion_id", "source",
            "target", "weight", "edge_type", "updated_at",
        ]]
        state.lance_db.drop_table(table_name)
        state.lance_db.create_table(table_name, old_df)
        return
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("workspace_id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("ingestion_id", pa.string()),
        pa.field("source", pa.string()),
        pa.field("target", pa.string()),
        pa.field("weight", pa.int32()),
        pa.field("edge_type", pa.string()),
        pa.field("updated_at", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)


def get_chat_history(
    session_id: Optional[str],
    limit: int = config.MAX_HISTORY_TURNS,
    user_id: Optional[str] = None,
    ingestion_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
):
    if state.lance_db is None or "chat_history" not in state.lance_db.table_names():
        return []
    try:
        _ensure_chat_table()
        table = state.lance_db.open_table("chat_history")
        clauses = [
            _eq_clause("user_id", _norm_user(user_id)),
            _eq_clause("workspace_id", _norm_workspace(workspace_id)),
        ]
        if ingestion_id:
            clauses.append(_eq_clause("ingestion_id", _norm_ingestion(ingestion_id)))
        sid = str(session_id or "").strip()
        if sid and sid not in {"all", "__all__", "*"}:
            clauses.append(_eq_clause("session_id", sid))

        df = _filtered_pandas(table, clauses)
        if df.empty:
            return []
        df = df.sort_values("created_at", ascending=False).head(limit)
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        return []


def store_chat_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Dict = None,
    user_id: Optional[str] = None,
    ingestion_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
):
    if state.lance_db is None:
        return
    _ensure_chat_table()
    try:
        table = state.lance_db.open_table("chat_history")
        record = {
            "id": str(uuid.uuid4()),
            "workspace_id": _norm_workspace(workspace_id),
            "user_id": _norm_user(user_id),
            "ingestion_id": _norm_ingestion(ingestion_id),
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

def _ensure_chart_table():
    if state.lance_db is None:
        return
    table_name = "chart_history"
    if table_name in state.lance_db.table_names():
        tbl = state.lance_db.open_table(table_name)
        schema = tbl.schema
        existing_cols = set(schema.names)
        required_cols = {
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "type",
            "prompt", "response", "config", "created_at", "metadata",
        }
        should_migrate = False
        if "id" in existing_cols and str(schema.field("id").type) == "null":
            should_migrate = True
        if not required_cols.issubset(existing_cols):
            should_migrate = True

        if not should_migrate:
            return

        logger.warning(f"{table_name} schema mismatch, migrating table")
        old_df = tbl.to_pandas()
        for col in required_cols:
            if col not in old_df.columns:
                if col in {"user_id"}:
                    old_df[col] = "anonymous"
                elif col in {"workspace_id"}:
                    old_df[col] = _norm_workspace(None)
                elif col in {"ingestion_id", "session_id", "type", "prompt", "response", "config", "metadata"}:
                    old_df[col] = ""
                elif col == "created_at":
                    old_df[col] = datetime.now(timezone.utc).isoformat()
                elif col == "id":
                    old_df[col] = [str(uuid.uuid4()) for _ in range(len(old_df))]

        old_df = old_df[[
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "type",
            "prompt", "response", "config", "created_at", "metadata",
        ]]
        state.lance_db.drop_table(table_name)
        state.lance_db.create_table(table_name, old_df)
        return
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("workspace_id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("ingestion_id", pa.string()),
        pa.field("session_id", pa.string()),
        pa.field("type", pa.string()),
        pa.field("prompt", pa.string()),
        pa.field("response", pa.string()),
        pa.field("config", pa.string()),
        pa.field("created_at", pa.string()),
        pa.field("metadata", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)


def get_chart_history(
    session_id: Optional[str],
    limit: int = 10,
    user_id: Optional[str] = None,
    ingestion_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
):
    if state.lance_db is None or "chart_history" not in state.lance_db.table_names():
        return []
    try:
        _ensure_chart_table()
        table = state.lance_db.open_table("chart_history")
        clauses = [
            _eq_clause("user_id", _norm_user(user_id)),
            _eq_clause("workspace_id", _norm_workspace(workspace_id)),
        ]
        if ingestion_id:
            clauses.append(_eq_clause("ingestion_id", _norm_ingestion(ingestion_id)))
        sid = str(session_id or "").strip()
        if sid and sid not in {"all", "__all__", "*"}:
            clauses.append(_eq_clause("session_id", sid))

        df = _filtered_pandas(table, clauses)
        if df.empty:
            return []
        df = df.sort_values("created_at", ascending=False).head(limit)
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error retrieving chart history: {e}")
        return []


def store_chart(
    session_id: str,
    prompt: str,
    config_json: str,
    metadata: Dict = None,
    user_id: Optional[str] = None,
    ingestion_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Optional[str]:
    """Persist a chart and return its new id (None if it could not be stored).

    The id matters to the caller: /chart hands it to the browser so the
    gallery can render the figure immediately and still recognise the same
    chart when the history list catches up, instead of showing it twice."""
    if state.lance_db is None:
        logger.error("store_chart: state.lance_db is None")
        return None
    try:
        _ensure_chart_table()
        table = state.lance_db.open_table("chart_history")
        record = {
            "id": str(uuid.uuid4()),
            "workspace_id": _norm_workspace(workspace_id),
            "user_id": _norm_user(user_id),
            "ingestion_id": _norm_ingestion(ingestion_id),
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
        return record["id"]
    except Exception as e:
        logger.error(f"Error storing chart: {e}")
        return None


def delete_chart(
    chart_id: str,
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    ingestion_id: Optional[str] = None,
    allow_any_owner: bool = False,
) -> bool:
    """Remove one chart, scoped to its owner. True if a row was removed.

    Uses LanceDB's native predicate delete rather than the old
    read-whole-table / drop_table / create_table dance. That rewrite was
    O(entire history) per click, and — worse — a failure between the drop
    and the create left the build with no chart_history table at all, so
    every previously saved chart vanished along with the one being deleted.
    """
    if state.lance_db is None or "chart_history" not in state.lance_db.table_names():
        return False

    cid = str(chart_id or "").strip()
    if not cid:
        return False

    _ensure_chart_table()
    table = state.lance_db.open_table("chart_history")

    clauses = [_eq_clause("id", cid)]
    if not allow_any_owner:
        clauses.append(_eq_clause("user_id", _norm_user(user_id)))
        clauses.append(_eq_clause("workspace_id", _norm_workspace(workspace_id)))
    if ingestion_id:
        clauses.append(_eq_clause("ingestion_id", _norm_ingestion(ingestion_id)))
    where = " AND ".join(clauses)

    # Confirm a row is actually in scope first, so "not found" and "not
    # yours" stay distinguishable to the caller instead of both looking
    # like a no-op delete.
    existing = table.search().where(where).limit(1).to_pandas()
    if existing.empty:
        return False

    table.delete(where)
    return True


def _upsert_learning_signal(
    workspace_id: str,
    user_id: str,
    ingestion_id: str,
    session_id: str,
    kind: str,
    prompt: str,
    response: str,
):
    if state.lance_db is None:
        return

    _ensure_learning_signal_table()
    now = datetime.now(timezone.utc).isoformat()
    prompt_norm = str(prompt or "").strip().lower()
    keywords = _extract_keywords(prompt)

    table = state.lance_db.open_table("learning_signals")
    # Composite key (workspace, user, ingestion, kind, prompt) is unique, so
    # at most one row can match - fetch just that row instead of the whole
    # table to read its current frequency/keywords before merging, then
    # update it in place. Previously this loaded the ENTIRE table into
    # pandas *and* rewrote it whole (drop_table + create_table) on every
    # single chat/chart interaction, regardless of table size - by far the
    # heaviest cost in this file, not just a read-side one.
    match_clause = " AND ".join([
        _eq_clause("workspace_id", workspace_id),
        _eq_clause("user_id", user_id),
        _eq_clause("ingestion_id", ingestion_id),
        _eq_clause("kind", kind),
        f"LOWER(prompt) = '{_sql_escape(prompt_norm)}'",
    ])
    existing = table.search().where(match_clause).limit(1).to_pandas()
    if not existing.empty:
        row = existing.iloc[0]
        prev_freq = int(row.get("frequency") or 0)
        prev_keywords = set(_safe_json_loads(row.get("keywords") or "[]", []))
        merged_keywords = sorted(prev_keywords.union(set(keywords)))
        table.update(
            where=match_clause,
            values={
                "frequency": prev_freq + 1,
                "response": response,
                "keywords": json.dumps(merged_keywords),
                "updated_at": now,
            },
        )
        return

    new_row = {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "user_id": user_id,
        "ingestion_id": ingestion_id,
        "session_id": session_id,
        "kind": kind,
        "prompt": prompt,
        "response": response,
        "keywords": json.dumps(keywords),
        "frequency": 1,
        "created_at": now,
        "updated_at": now,
    }
    table.add([new_row])


def _update_knowledge_graph(workspace_id: str, user_id: str, ingestion_id: str, prompt: str):
    if state.lance_db is None:
        return

    _ensure_knowledge_graph_table()
    keywords = _extract_keywords(prompt, max_terms=10)
    if len(keywords) < 2:
        return

    table = state.lance_db.open_table("knowledge_graph_edges")
    now = datetime.now(timezone.utc).isoformat()
    new_rows = []

    # One targeted update per co-occurring pair (at most C(10,2)=45) instead
    # of loading the entire edges table into pandas and rewriting it whole
    # (drop_table + create_table) on every interaction - that was O(table
    # size) work per chat message no matter how many pairs this call
    # touches. weight is incremented atomically via values_sql, so there's
    # no read-modify-write race either.
    for a, b in combinations(sorted(set(keywords)), 2):
        match_clause = " AND ".join([
            _eq_clause("workspace_id", workspace_id),
            _eq_clause("user_id", user_id),
            _eq_clause("ingestion_id", ingestion_id),
            _eq_clause("source", a),
            _eq_clause("target", b),
        ])
        result = table.update(
            where=match_clause,
            values_sql={"weight": "weight + 1", "updated_at": f"'{_sql_escape(now)}'"},
        )
        if result.rows_updated == 0:
            new_rows.append({
                "id": str(uuid.uuid4()),
                "workspace_id": workspace_id,
                "user_id": user_id,
                "ingestion_id": ingestion_id,
                "source": a,
                "target": b,
                "weight": 1,
                "edge_type": "cooccurrence",
                "updated_at": now,
            })

    if new_rows:
        table.add(new_rows)


def learn_from_interaction(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    session_id: Optional[str],
    workspace_id: Optional[str],
    prompt: str,
    response: str,
    kind: str = "chat",
):
    if state.lance_db is None:
        return
    uid = _norm_user(user_id)
    iid = _norm_ingestion(ingestion_id)
    wid = _norm_workspace(workspace_id)
    sid = str(session_id or "").strip() or "default"
    try:
        _upsert_learning_signal(wid, uid, iid, sid, kind, prompt, response)
        _update_knowledge_graph(wid, uid, iid, prompt)
    except Exception as exc:
        logger.error(f"Error updating learning memory: {exc}")


def get_learning_context(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    workspace_id: Optional[str],
    query: str,
    limit: int = 5,
) -> List[Dict]:
    _ensure_learning_signal_table()
    if state.lance_db is None or "learning_signals" not in state.lance_db.table_names():
        return []
    try:
        uid = _norm_user(user_id)
        iid = _norm_ingestion(ingestion_id)
        wid = _norm_workspace(workspace_id)
        query_terms = set(_extract_keywords(query, max_terms=14))

        table = state.lance_db.open_table("learning_signals")
        clauses = [
            _eq_clause("workspace_id", wid),
            _eq_clause("user_id", uid),
            _eq_clause("ingestion_id", iid),
        ]
        df = _filtered_pandas(table, clauses)
        if df.empty:
            return []

        def _row_score(row) -> float:
            kws = set(_safe_json_loads(row.get("keywords", "[]"), []))
            overlap = _text_overlap_score(query_terms, kws)
            freq = float(row.get("frequency", 1) or 1)
            recency_bonus = 0.25 if str(row.get("updated_at", "")).strip() else 0.0
            return overlap * 3.0 + min(freq, 6.0) * 0.15 + recency_bonus

        df = df.copy()
        df["score"] = df.apply(_row_score, axis=1)
        df = df[df["score"] > 0].sort_values(["score", "updated_at"], ascending=False).head(limit)
        if df.empty:
            return []
        return df[["kind", "prompt", "response", "keywords", "frequency", "score"]].to_dict(orient="records")
    except Exception as exc:
        logger.error(f"Error getting learning context: {exc}")
        return []


def get_related_concepts(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    workspace_id: Optional[str],
    query: str,
    limit: int = 8,
) -> List[Dict]:
    _ensure_knowledge_graph_table()
    if state.lance_db is None or "knowledge_graph_edges" not in state.lance_db.table_names():
        return []
    try:
        uid = _norm_user(user_id)
        iid = _norm_ingestion(ingestion_id)
        wid = _norm_workspace(workspace_id)
        q_terms = set(_extract_keywords(query, max_terms=8))
        if not q_terms:
            return []

        table = state.lance_db.open_table("knowledge_graph_edges")
        clauses = [
            _eq_clause("workspace_id", wid),
            _eq_clause("user_id", uid),
            _eq_clause("ingestion_id", iid),
        ]
        df = _filtered_pandas(table, clauses)
        if df.empty:
            return []

        candidates = []
        for _, row in df.iterrows():
            src = str(row.get("source", ""))
            tgt = str(row.get("target", ""))
            w = int(row.get("weight", 0) or 0)
            if src in q_terms and tgt not in q_terms:
                candidates.append({"concept": tgt, "weight": w, "source": src})
            elif tgt in q_terms and src not in q_terms:
                candidates.append({"concept": src, "weight": w, "source": tgt})

        candidates = sorted(candidates, key=lambda x: x["weight"], reverse=True)
        seen = set()
        result = []
        for c in candidates:
            key = c["concept"]
            if key in seen:
                continue
            seen.add(key)
            result.append(c)
            if len(result) >= limit:
                break
        return result
    except Exception as exc:
        logger.error(f"Error getting related concepts: {exc}")
        return []


def _ensure_feedback_table():
    if state.lance_db is None:
        return
    table_name = "feedback_signals"
    if table_name in state.lance_db.table_names():
        tbl = state.lance_db.open_table(table_name)
        existing_cols = set(tbl.schema.names)
        required_cols = {
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "target_kind",
            "feedback_type", "prompt", "response", "chart_id", "notes", "tags", "created_at",
        }
        if required_cols.issubset(existing_cols):
            return
        old_df = tbl.to_pandas()
        for col in required_cols:
            if col not in old_df.columns:
                if col == "workspace_id":
                    old_df[col] = _norm_workspace(None)
                elif col == "user_id":
                    old_df[col] = "anonymous"
                elif col in {"ingestion_id", "session_id", "target_kind", "feedback_type", "prompt", "response", "chart_id", "notes", "tags"}:
                    old_df[col] = ""
                elif col == "created_at":
                    old_df[col] = datetime.now(timezone.utc).isoformat()
                elif col == "id":
                    old_df[col] = [str(uuid.uuid4()) for _ in range(len(old_df))]
        old_df = old_df[[
            "id", "workspace_id", "user_id", "ingestion_id", "session_id", "target_kind",
            "feedback_type", "prompt", "response", "chart_id", "notes", "tags", "created_at",
        ]]
        state.lance_db.drop_table(table_name)
        state.lance_db.create_table(table_name, old_df)
        return

    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("workspace_id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("ingestion_id", pa.string()),
        pa.field("session_id", pa.string()),
        pa.field("target_kind", pa.string()),
        pa.field("feedback_type", pa.string()),
        pa.field("prompt", pa.string()),
        pa.field("response", pa.string()),
        pa.field("chart_id", pa.string()),
        pa.field("notes", pa.string()),
        pa.field("tags", pa.string()),
        pa.field("created_at", pa.string()),
    ])
    state.lance_db.create_table(table_name, schema=schema)


def store_feedback(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    workspace_id: Optional[str],
    session_id: Optional[str],
    target_kind: str,
    feedback_type: str,
    prompt: Optional[str] = None,
    response: Optional[str] = None,
    chart_id: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[List[str]] = None,
):
    if state.lance_db is None:
        return False
    try:
        _ensure_feedback_table()
        table = state.lance_db.open_table("feedback_signals")
        table.add([
            {
                "id": str(uuid.uuid4()),
                "workspace_id": _norm_workspace(workspace_id),
                "user_id": _norm_user(user_id),
                "ingestion_id": _norm_ingestion(ingestion_id),
                "session_id": str(session_id or "").strip() or "default",
                "target_kind": str(target_kind or "chat").strip().lower(),
                "feedback_type": str(feedback_type or "improve").strip().lower(),
                "prompt": str(prompt or "").strip(),
                "response": str(response or "").strip(),
                "chart_id": str(chart_id or "").strip(),
                "notes": str(notes or "").strip(),
                "tags": json.dumps([str(t).strip().lower() for t in (tags or []) if str(t).strip()]),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ])
        return True
    except Exception as exc:
        logger.error(f"Error storing feedback: {exc}")
        return False


def get_feedback_preferences(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    workspace_id: Optional[str],
    target_kind: str,
    limit: int = 120,
) -> Dict:
    _ensure_feedback_table()
    if state.lance_db is None or "feedback_signals" not in state.lance_db.table_names():
        return {"prefer": [], "avoid": [], "tags": []}

    try:
        uid = _norm_user(user_id)
        iid = _norm_ingestion(ingestion_id)
        wid = _norm_workspace(workspace_id)
        tkind = str(target_kind or "chat").strip().lower()

        table = state.lance_db.open_table("feedback_signals")
        clauses = [
            _eq_clause("workspace_id", wid),
            _eq_clause("user_id", uid),
            _eq_clause("ingestion_id", iid),
            _eq_clause("target_kind", tkind),
        ]
        df = _filtered_pandas(table, clauses)
        if df.empty:
            return {"prefer": [], "avoid": [], "tags": []}

        df = df.sort_values("created_at", ascending=False).head(limit)
        prefer_counter = Counter()
        avoid_counter = Counter()
        tags_counter = Counter()

        for _, row in df.iterrows():
            ftype = str(row.get("feedback_type", "")).strip().lower()
            notes = str(row.get("notes", "")).strip().lower()
            terms = _extract_keywords(notes, max_terms=10)
            if ftype in {"up", "positive"}:
                prefer_counter.update(terms)
            elif ftype in {"down", "negative"}:
                avoid_counter.update(terms)
            else:
                prefer_counter.update(terms)

            for tag in _safe_json_loads(row.get("tags", "[]"), []):
                if str(tag).strip():
                    tags_counter.update([str(tag).strip().lower()])

        prefer = [k for k, _ in prefer_counter.most_common(5)]
        avoid = [k for k, _ in avoid_counter.most_common(5)]
        tags = [k for k, _ in tags_counter.most_common(6)]
        return {"prefer": prefer, "avoid": avoid, "tags": tags}
    except Exception as exc:
        logger.error(f"Error getting feedback preferences: {exc}")
        return {"prefer": [], "avoid": [], "tags": []}


def get_feedback_prompt_hints(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    workspace_id: Optional[str],
    target_kind: str,
    current_prompt: Optional[str] = None,
) -> str:
    prefs = get_feedback_preferences(user_id, ingestion_id, workspace_id, target_kind)
    uid = _norm_user(user_id)
    iid = _norm_ingestion(ingestion_id)
    wid = _norm_workspace(workspace_id)
    tkind = str(target_kind or "chat").strip().lower()

    lines = []
    if prefs.get("prefer"):
        lines.append("Prefer: " + ", ".join(prefs["prefer"]))
    if prefs.get("avoid"):
        lines.append("Avoid: " + ", ".join(prefs["avoid"]))
    if prefs.get("tags"):
        lines.append("Style tags: " + ", ".join(prefs["tags"]))

    if state.lance_db is not None and "feedback_signals" in state.lance_db.table_names():
        try:
            table = state.lance_db.open_table("feedback_signals")
            clauses = [
                _eq_clause("workspace_id", wid),
                _eq_clause("user_id", uid),
                _eq_clause("ingestion_id", iid),
                _eq_clause("target_kind", tkind),
            ]
            df = _filtered_pandas(table, clauses)
            if not df.empty:
                recent = df.sort_values("created_at", ascending=False).head(80)
                down_all = int((recent["feedback_type"].astype(str).str.lower().isin(["down", "negative"])).sum())
                up_all = int((recent["feedback_type"].astype(str).str.lower().isin(["up", "positive"])).sum())
                improve_all = int((recent["feedback_type"].astype(str).str.lower() == "improve").sum())
                if down_all or up_all or improve_all:
                    lines.append(
                        f"Recent feedback mix: up={up_all}, down={down_all}, improve={improve_all}. "
                        "Use this to calibrate tone, structure, and depth."
                    )

                negative_notes = [
                    str(r.get("notes", "")).strip()
                    for _, r in recent.iterrows()
                    if str(r.get("feedback_type", "")).strip().lower() in {"down", "negative", "improve"}
                    and str(r.get("notes", "")).strip()
                ]
                if negative_notes:
                    lines.append("Latest improvement requests: " + "; ".join(negative_notes[:3]))

                positive_notes = [
                    str(r.get("notes", "")).strip()
                    for _, r in recent.iterrows()
                    if str(r.get("feedback_type", "")).strip().lower() in {"up", "positive"}
                    and str(r.get("notes", "")).strip()
                ]
                if positive_notes:
                    lines.append("Keep these approved traits: " + "; ".join(positive_notes[:2]))

                if current_prompt:
                    prompt_terms = set(_extract_keywords(current_prompt, max_terms=14))
                    similar_rows = []
                    for _, row in recent.iterrows():
                        src = " ".join([
                            str(row.get("prompt", "")),
                            str(row.get("notes", "")),
                        ])
                        overlap = _text_overlap_score(prompt_terms, set(_extract_keywords(src, max_terms=14)))
                        if overlap > 0.15:
                            similar_rows.append(row)

                    if similar_rows:
                        down = sum(1 for r in similar_rows if str(r.get("feedback_type", "")).lower() in {"down", "negative"})
                        up = sum(1 for r in similar_rows if str(r.get("feedback_type", "")).lower() in {"up", "positive"})
                        latest_notes = [str(r.get("notes", "")).strip() for r in similar_rows if str(r.get("notes", "")).strip()]
                        if down > 0:
                            lines.append("For similar requests, user marked prior outputs as weak. Change structure and provide a clearly improved version.")
                        if up > down and up > 0:
                            lines.append("For similar requests, user approved concise structure. Keep that style.")
                        if latest_notes:
                            lines.append("Specific feedback notes: " + "; ".join(latest_notes[:2]))
        except Exception as exc:
            logger.error(f"Error computing prompt-aware feedback hints: {exc}")

    return "\n".join(lines).strip()