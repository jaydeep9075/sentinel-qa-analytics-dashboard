import json
import uuid
import logging
import re
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

def _ensure_chat_table():
    if not state.lance_db:
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
    if not state.lance_db:
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
    if not state.lance_db:
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
    if not state.lance_db or "chat_history" not in state.lance_db.table_names():
        return []
    try:
        table = state.lance_db.open_table("chat_history")
        df = table.to_pandas()
        if df.empty:
            return []

        if "user_id" in df.columns:
            df = df[df["user_id"] == _norm_user(user_id)]
        if "workspace_id" in df.columns:
            df = df[df["workspace_id"] == _norm_workspace(workspace_id)]
        if ingestion_id and "ingestion_id" in df.columns:
            df = df[df["ingestion_id"] == _norm_ingestion(ingestion_id)]

        sid = str(session_id or "").strip()
        if sid and sid not in {"all", "__all__", "*"}:
            df = df[df["session_id"] == sid]

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
    if not state.lance_db:
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
    if not state.lance_db:
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
    if not state.lance_db or "chart_history" not in state.lance_db.table_names():
        return []
    try:
        table = state.lance_db.open_table("chart_history")
        df = table.to_pandas()
        if df.empty:
            return []

        if "user_id" in df.columns:
            df = df[df["user_id"] == _norm_user(user_id)]
        if "workspace_id" in df.columns:
            df = df[df["workspace_id"] == _norm_workspace(workspace_id)]
        if ingestion_id and "ingestion_id" in df.columns:
            df = df[df["ingestion_id"] == _norm_ingestion(ingestion_id)]

        sid = str(session_id or "").strip()
        if sid and sid not in {"all", "__all__", "*"}:
            df = df[df["session_id"] == sid]

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
):
    if not state.lance_db:
        logger.error("store_chart: state.lance_db is None")
        return False
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
        return True
    except Exception as e:
        logger.error(f"Error storing chart: {e}")
        return False


def _upsert_learning_signal(
    workspace_id: str,
    user_id: str,
    ingestion_id: str,
    session_id: str,
    kind: str,
    prompt: str,
    response: str,
):
    if not state.lance_db:
        return

    _ensure_learning_signal_table()
    now = datetime.now(timezone.utc).isoformat()
    prompt_norm = str(prompt or "").strip().lower()
    keywords = _extract_keywords(prompt)

    table = state.lance_db.open_table("learning_signals")
    df = table.to_pandas()

    if not df.empty:
        mask = (
            (df["workspace_id"] == workspace_id)
            &
            (df["user_id"] == user_id)
            & (df["ingestion_id"] == ingestion_id)
            & (df["kind"] == kind)
            & (df["prompt"].fillna("").str.lower() == prompt_norm)
        )
        if mask.any():
            idx = df[mask].index[0]
            prev_freq = int(df.at[idx, "frequency"] or 0)
            prev_keywords = set(_safe_json_loads(df.at[idx, "keywords"] or "[]", []))
            merged_keywords = sorted(prev_keywords.union(set(keywords)))
            df.at[idx, "frequency"] = prev_freq + 1
            df.at[idx, "response"] = response
            df.at[idx, "keywords"] = json.dumps(merged_keywords)
            df.at[idx, "updated_at"] = now
            state.lance_db.drop_table("learning_signals")
            state.lance_db.create_table("learning_signals", df)
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
    if not state.lance_db:
        return

    _ensure_knowledge_graph_table()
    keywords = _extract_keywords(prompt, max_terms=10)
    if len(keywords) < 2:
        return

    table = state.lance_db.open_table("knowledge_graph_edges")
    df = table.to_pandas()
    now = datetime.now(timezone.utc).isoformat()

    for a, b in combinations(sorted(set(keywords)), 2):
        if df.empty:
            row = None
        else:
            edge_mask = (
                (df["workspace_id"] == workspace_id)
                &
                (df["user_id"] == user_id)
                & (df["ingestion_id"] == ingestion_id)
                & (df["source"] == a)
                & (df["target"] == b)
            )
            row = df[edge_mask]

        if row is not None and not row.empty:
            idx = row.index[0]
            df.at[idx, "weight"] = int(df.at[idx, "weight"] or 0) + 1
            df.at[idx, "updated_at"] = now
        else:
            new_row = pd.DataFrame([
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "ingestion_id": ingestion_id,
                    "source": a,
                    "target": b,
                    "weight": 1,
                    "edge_type": "cooccurrence",
                    "updated_at": now,
                }
            ])
            df = pd.concat([df, new_row], ignore_index=True)

    if "knowledge_graph_edges" in state.lance_db.table_names():
        state.lance_db.drop_table("knowledge_graph_edges")
    state.lance_db.create_table("knowledge_graph_edges", df)


def learn_from_interaction(
    user_id: Optional[str],
    ingestion_id: Optional[str],
    session_id: Optional[str],
    workspace_id: Optional[str],
    prompt: str,
    response: str,
    kind: str = "chat",
):
    if not state.lance_db:
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
    if not state.lance_db or "learning_signals" not in state.lance_db.table_names():
        return []
    try:
        uid = _norm_user(user_id)
        iid = _norm_ingestion(ingestion_id)
        wid = _norm_workspace(workspace_id)
        query_terms = set(_extract_keywords(query, max_terms=14))

        table = state.lance_db.open_table("learning_signals")
        df = table.to_pandas()
        if df.empty:
            return []

        if "workspace_id" in df.columns:
            df = df[df["workspace_id"] == wid]
        if "user_id" in df.columns:
            df = df[df["user_id"] == uid]
        if "ingestion_id" in df.columns:
            df = df[df["ingestion_id"] == iid]
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
    if not state.lance_db or "knowledge_graph_edges" not in state.lance_db.table_names():
        return []
    try:
        uid = _norm_user(user_id)
        iid = _norm_ingestion(ingestion_id)
        wid = _norm_workspace(workspace_id)
        q_terms = set(_extract_keywords(query, max_terms=8))
        if not q_terms:
            return []

        table = state.lance_db.open_table("knowledge_graph_edges")
        df = table.to_pandas()
        if df.empty:
            return []
        if "workspace_id" in df.columns:
            df = df[df["workspace_id"] == wid]
        if "user_id" in df.columns:
            df = df[df["user_id"] == uid]
        if "ingestion_id" in df.columns:
            df = df[df["ingestion_id"] == iid]
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