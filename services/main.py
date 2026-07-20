import logging
import uuid
import json
import re
import shutil
import tempfile
import time
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
from typing import Optional
from datetime import datetime, timezone
from . import config, state, data_loader, handlers, memory, llm_client, ingestion_jobs
from . import token_usage_store
from .prompts import SUGGESTION_PROMPT
from .auth import authenticate_user, create_access_token, get_current_user, initialize_auth_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_STATUS_CACHE_TTL_SECONDS = 10.0
_QUALITY_CACHE_TTL_SECONDS = 20.0
_status_cache: dict[str, tuple[float, dict]] = {}
_quality_cache: dict[str, tuple[float, dict]] = {}
_PERF_PATH_PREFIXES = (
    "/dashboard/overview",
    "/data/status",
    "/data/quality",
    "/ingestions",
    "/chart/history/",
    "/usage/tokens",
)

def _get_test_results_table() -> str:
    """Get the actual table name for test results.
    Supports both old (flattened_tests) and new (structured_test_results) names."""
    try:
        tables = state.duck_conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory'").df()
        table_names = tables['table_name'].tolist() if not tables.empty else []

        # Try new name first, fallback to old name
        if "structured_test_results" in table_names:
            return "structured_test_results"
        elif "flattened_tests" in table_names:
            return "flattened_tests"
        else:
            # Neither exists - return default (will fail with clear error)
            return "flattened_tests"
    except Exception as e:
        logger.warning(f"Could not query table names: {e}, using default")
        return "flattened_tests"

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChartRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class IngestRequest(BaseModel):
    source_path: str
    source_type: Optional[str] = None
    workspace_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    target_kind: str
    feedback_type: str
    prompt: Optional[str] = None
    response: Optional[str] = None
    chart_id: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    session_id: Optional[str] = None


def _normalize_workspace(workspace_id: Optional[str], current_user: Optional[dict] = None) -> str:
    if workspace_id:
        return str(workspace_id).strip().lower()
    if current_user and current_user.get("workspace_id"):
        return str(current_user["workspace_id"]).strip().lower()
    return str(getattr(config, "DEFAULT_WORKSPACE_ID", "default") or "default").strip().lower()


def _is_admin_role(role: Optional[str]) -> bool:
    return str(role or "").strip().lower() in {"admin", "cto"}


def _infer_source_type(source_path: str, explicit: Optional[str]) -> str:
    if explicit:
        return str(explicit).strip().lower()
    p = str(source_path or "").strip().lower()
    if not p:
        return "file"
    if "allure" in p and ("result" in p or p.endswith("/") or p.endswith("\\")):
        return "allure"
    return "file"


_QA_SCHEMA_TABLES = {"flattened_tests", "module_metrics", "project_metrics"}
_NUMERIC_TYPE_HINTS = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC")


def _schema_driven_fallback_suggestions(schema_profile: Optional[dict]) -> Optional[dict]:
    """Generate simple suggestions directly from the real ingested schema,
    with no LLM call — the no-LLM safety net for non-QA datasets (CSV/PDF/
    JSON of any domain) so suggestions reflect the ACTUAL ingested data
    instead of hardcoded QA/test phrasing that wouldn't apply. Returns None
    if no usable schema profile is available."""
    tables = schema_profile.get("tables", {}) if isinstance(schema_profile, dict) else {}
    if not tables:
        return None

    chat: list = []
    chart: list = []
    for tbl, info in tables.items():
        if not isinstance(info, dict):
            continue
        cols = [c.get("name") for c in info.get("columns", []) if isinstance(c, dict) and c.get("name")]
        if not cols:
            continue
        numeric_cols = [
            c.get("name") for c in info.get("columns", [])
            if isinstance(c, dict) and any(h in str(c.get("type", "")).upper() for h in _NUMERIC_TYPE_HINTS)
        ]
        categorical_cols = [c for c in cols if c not in numeric_cols]

        chat.append(f"How many records are in {tbl}?")
        chat.append(f"Show the first 20 rows of {tbl}.")
        chart.append(f"Bar chart of record counts in {tbl}.")
        if categorical_cols:
            chat.append(f"Show a breakdown of {tbl} by {categorical_cols[0]}.")
            chart.append(f"Bar chart of {tbl} record counts by {categorical_cols[0]}.")
            chart.append(f"Pie chart of {tbl} distribution by {categorical_cols[0]}.")
        if len(categorical_cols) > 1:
            chat.append(f"Compare {tbl} across {categorical_cols[0]} and {categorical_cols[1]}.")
        if numeric_cols:
            chat.append(f"What is the average {numeric_cols[0]} in {tbl}?")
            chart.append(f"Line chart of {numeric_cols[0]} across {tbl}.")
        if categorical_cols and numeric_cols:
            chart.append(f"Grouped bar chart of {numeric_cols[0]} by {categorical_cols[0]} in {tbl}.")
        if len(numeric_cols) > 1:
            chat.append(f"Compare {numeric_cols[0]} and {numeric_cols[1]} in {tbl}.")
            chart.append(f"Scatter chart of {numeric_cols[0]} vs {numeric_cols[1]} in {tbl}.")

    chat = list(dict.fromkeys(chat))
    chart = list(dict.fromkeys(chart))
    if len(chat) < 4 or len(chart) < 4:
        return None

    while len(chat) < 8:
        chat.append(chat[len(chat) % len(chat)])
    while len(chart) < 8:
        chart.append(chart[len(chart) % len(chart)])
    return {"chat": chat[:8], "chart": chart[:8]}


def _fallback_suggestions(role_id: Optional[str], schema_profile: Optional[dict] = None) -> dict:
    tables = schema_profile.get("tables", {}) if isinstance(schema_profile, dict) else {}
    looks_like_qa_schema = bool(_QA_SCHEMA_TABLES & set(tables.keys()))
    if not looks_like_qa_schema:
        dynamic = _schema_driven_fallback_suggestions(schema_profile)
        if dynamic:
            return dynamic

    role_key = str(role_id or "").strip().lower().replace("_", "-")
    if role_key in {"cto", "chief-technology-officer"}:
        return {
            "chat": [
                "What is the overall pass rate and release readiness for this build?",
                "Which project has the highest failure impact right now?",
                "Show top 5 modules by failure count with risk notes.",
                "Compare mobile vs desktop pass rate by project.",
                "Which modules have the lowest pass rate and should be blocked?",
                "How does this build quality compare to previous ingestions?",
                "List high-risk areas with recommended executive action.",
                "Summarize build health in an executive-ready format.",
            ],
            "chart": [
                "Bar chart of pass rate by project and platform.",
                "Heatmap of failure density by project and module.",
                "Trend line of pass rate across recent builds.",
                "Bar chart of top failing modules by impact.",
                "Donut chart of release readiness status distribution.",
                "Stacked bar of passed/failed/skipped by project.",
                "Line chart comparing failure rate trend by platform.",
                "Executive risk matrix chart for project vs failure load.",
            ],
        }
    return {
        "chat": [
            "List failed tests with error messages and module names.",
            "Show the slowest tests and likely bottlenecks.",
            "Which modules have increasing failure trends?",
            "Compare mobile and desktop failures by module.",
            "Show flaky-risk candidates based on repeated failures.",
            "What is the pass rate and failed count by module?",
            "Which tests should QA prioritize for debugging first?",
            "Summarize top actionable defects for this build.",
        ],
        "chart": [
            "Bar chart of failed tests by module.",
            "Horizontal bar chart of slowest tests.",
            "Heatmap of failures by module and platform.",
            "Pie chart of passed vs failed vs skipped.",
            "Line chart of pass rate trend by module.",
            "Grouped bar chart of mobile vs desktop failures.",
            "Bar chart of top failing projects and modules.",
            "Scatter chart of test duration vs failure status.",
        ],
    }


def _normalize_suggestions(payload: dict, role_id: Optional[str], schema_profile: Optional[dict] = None) -> dict:
    fallback = _fallback_suggestions(role_id, schema_profile)
    if not isinstance(payload, dict):
        return fallback

    chat = payload.get("chat", [])
    chart = payload.get("chart", [])
    if not isinstance(chat, list) or not isinstance(chart, list):
        return fallback

    chat_clean = [str(x).strip() for x in chat if str(x).strip()][:8]
    chart_clean = [str(x).strip() for x in chart if str(x).strip()][:8]
    if len(chat_clean) < 4 or len(chart_clean) < 4:
        return fallback

    while len(chat_clean) < 8:
        chat_clean.append(fallback["chat"][len(chat_clean)])
    while len(chart_clean) < 8:
        chart_clean.append(fallback["chart"][len(chart_clean)])
    chat_clean = _repair_truncated_first_item(chat_clean, fallback["chat"])
    chart_clean = _repair_truncated_first_item(chart_clean, fallback["chart"])
    return {"chat": chat_clean[:8], "chart": chart_clean[:8]}


def _sanitize_suggestion_item(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = cleaned.strip("`\"' ")
    if cleaned and cleaned[-1] in {",", ":", "-", "/", "("}:
        cleaned = cleaned[:-1].strip()
    return cleaned


def _looks_truncated_item(text: str) -> bool:
    if not text:
        return True
    tail = text.lower().strip()
    dangling_endings = (
        " for",
        " for the",
        " and",
        " with",
        " to",
        " in",
        " in the",
        " of",
        " on",
        " by",
        " from",
        " where",
        " which",
    )
    if tail.endswith(dangling_endings):
        return True
    if tail.count("`") % 2 == 1:
        return True
    if len(tail) >= 65 and tail[-1] not in {".", "?", "!"}:
        return True
    return False


def _split_truncated_item(text: str) -> str:
    cleaned = _sanitize_suggestion_item(text)
    # Prefer the meaningful prefix before a likely cut-off conjunction/preposition.
    parts = re.split(
        r"\s+(?:for|with|to|in|of|on|by|from|and)\s+(?:the\s+)?$",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    if parts and len(parts[0].strip()) >= 18:
        return parts[0].strip()
    # Fallback to last major punctuation boundary if present.
    for sep in [";", ":", ","]:
        if sep in cleaned:
            head = cleaned.split(sep)[0].strip()
            if len(head) >= 18:
                return head
    return cleaned


def _repair_truncated_first_item(items: list[str], fallback_items: list[str]) -> list[str]:
    if not items:
        return list(fallback_items[:8])

    repaired = [_sanitize_suggestion_item(x) for x in items if _sanitize_suggestion_item(x)]
    if not repaired:
        return list(fallback_items[:8])

    if _looks_truncated_item(repaired[0]):
        split_head = _split_truncated_item(repaired[0])
        if _looks_truncated_item(split_head) or len(split_head) < 18:
            repaired[0] = fallback_items[0]
        else:
            repaired[0] = split_head

    while len(repaired) < 8:
        repaired.append(fallback_items[len(repaired)])
    return repaired[:8]


def _strip_code_fences(text: str) -> str:
    return re.sub(r"```json\s*|```", "", str(text or ""), flags=re.IGNORECASE).strip()


def _extract_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start = -1
    depth = 0
    in_string = False
    escaped = False

    for idx, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidates.append(text[start:idx + 1])
                    start = -1
    return candidates


def _extract_partial_items(raw_section: str) -> list[str]:
    items: list[str] = []
    for match in re.findall(r'"([^"\\\r\n]{4,220})"', raw_section or ""):
        candidate = _sanitize_suggestion_item(match)
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in {"chat", "chart", "role", "project", "source"}:
            continue
        items.append(candidate)
        if len(items) >= 8:
            break
    return items


def _salvage_suggestions_payload(
    raw_text: str, role_id: Optional[str], schema_profile: Optional[dict] = None
) -> Optional[dict]:
    text = _strip_code_fences(raw_text)
    if not text:
        return None

    chat_section = ""
    chart_section = ""

    chat_match = re.search(r'"chat"\s*:\s*\[(.*?)(?:\]\s*,\s*"chart"|\]\s*\}|$)', text, flags=re.IGNORECASE | re.DOTALL)
    if chat_match:
        chat_section = chat_match.group(1)
    chart_match = re.search(r'"chart"\s*:\s*\[(.*?)(?:\]\s*\}|$)', text, flags=re.IGNORECASE | re.DOTALL)
    if chart_match:
        chart_section = chart_match.group(1)

    chat = _extract_partial_items(chat_section)
    chart = _extract_partial_items(chart_section)
    if not chat and not chart:
        return None

    fallback = _fallback_suggestions(role_id, schema_profile)
    chat = _repair_truncated_first_item(chat, fallback["chat"])
    chart = _repair_truncated_first_item(chart, fallback["chart"])
    while len(chat) < 8:
        chat.append(fallback["chat"][len(chat)])
    while len(chart) < 8:
        chart.append(fallback["chart"][len(chart)])
    return {"chat": chat[:8], "chart": chart[:8]}


def _parse_suggestions_payload(
    raw_text: str, role_id: Optional[str], schema_profile: Optional[dict] = None
) -> Optional[dict]:
    cleaned = _strip_code_fences(raw_text)
    if not cleaned:
        return None

    for candidate in [cleaned, *_extract_json_candidates(cleaned)]:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return _normalize_suggestions(payload, role_id, schema_profile)

    return _salvage_suggestions_payload(cleaned, role_id, schema_profile)


def _build_retry_suggestion_prompt(
    role_id: str,
    project_id: str,
    role_instruction: str,
    schema_profile: dict,
    quality: dict,
) -> str:
    role_instruction_small = str(role_instruction or "").strip()[:350]
    schema_small = json.dumps(schema_profile or {}, ensure_ascii=False)[:700]
    quality_small = json.dumps(quality or {}, ensure_ascii=False)[:550]

    return (
        "Return ONLY valid minified JSON.\n"
        "Strict schema: {\"chat\":[8 strings],\"chart\":[8 strings]}.\n"
        "Do not output markdown, code fences, or extra keys.\n"
        "Each suggestion must be <= 16 words and actionable.\n"
        "No test IDs, no file paths, no stack traces.\n"
        f"ROLE_ID: {role_id}\n"
        f"PROJECT: {project_id}\n"
        f"ROLE_HINT: {role_instruction_small or 'Use role id semantics for audience and tone.'}\n"
        f"SCHEMA_SNAPSHOT: {schema_small}\n"
        f"QUALITY_SNAPSHOT: {quality_small}\n"
        "Output exactly: {\"chat\":[\"...\",\"...\",\"...\",\"...\",\"...\",\"...\",\"...\",\"...\"],\"chart\":[\"...\",\"...\",\"...\",\"...\",\"...\",\"...\",\"...\",\"...\"]}"
    )


def _cache_get(cache: dict[str, tuple[float, dict]], key: str, ttl_seconds: float) -> Optional[dict]:
    now = time.time()
    entry = cache.get(key)
    if not entry:
        return None
    ts, payload = entry
    if now - ts > ttl_seconds:
        cache.pop(key, None)
        return None
    return payload


def _cache_set(cache: dict[str, tuple[float, dict]], key: str, payload: dict) -> dict:
    cache[key] = (time.time(), payload)
    return payload


def _get_status_payload(normalized_ingestion_id: str) -> dict:
    cached = _cache_get(_status_cache, normalized_ingestion_id, _STATUS_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    if not state.duck_conn:
        payload = {"has_data": False, "total_rows": 0, "status_summary": {"passed": 0, "failed": 0}}
        return _cache_set(_status_cache, normalized_ingestion_id, payload)

    test_table = _get_test_results_table()
    row = state.duck_conn.execute(
        f"""
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS passed,
          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
        FROM {test_table}
        """
    ).fetchone()
    total_rows = int(row[0] or 0)
    passed = int(row[1] or 0)
    failed = int(row[2] or 0)

    payload = {
        "has_data": total_rows > 0,
        "total_rows": total_rows,
        "status_summary": {
            "passed": passed,
            "failed": failed,
        },
    }
    return _cache_set(_status_cache, normalized_ingestion_id, payload)


def _get_quality_payload(normalized_ingestion_id: str) -> dict:
    cached = _cache_get(_quality_cache, normalized_ingestion_id, _QUALITY_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    if not state.duck_conn:
        payload = {
            "score": 0,
            "quality": "unknown",
            "checks": [],
            "guidance": ["No active ingestion loaded"],
        }
        return _cache_set(_quality_cache, normalized_ingestion_id, payload)

    payload = data_loader.get_ingestion_quality_report()
    if isinstance(payload, dict):
        return _cache_set(_quality_cache, normalized_ingestion_id, payload)
    return _cache_set(
        _quality_cache,
        normalized_ingestion_id,
        {
            "score": 0,
            "quality": "poor",
            "checks": [],
            "guidance": ["Quality report returned invalid payload"],
        },
    )


def _get_cached_quality_payload(normalized_ingestion_id: str) -> dict:
    cached = _cache_get(_quality_cache, normalized_ingestion_id, _QUALITY_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached
    return {
        "score": 0,
        "quality": "warming",
        "checks": [],
        "guidance": ["Quality panel is warming up. Live metrics will appear shortly."],
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    config.validate_runtime_config()
    initialize_auth_store()
    yield
    logger.info("Shutting down...")
    if state.duck_conn:
        state.duck_conn.close()

app = FastAPI(title="Unified QA Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0

    path = request.url.path
    if any(path.startswith(prefix) for prefix in _PERF_PATH_PREFIXES):
        response.headers["x-server-timing-ms"] = f"{duration_ms:.2f}"
        logger.info(
            "perf method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
    return response

# -------------------- PUBLIC ENDPOINTS --------------------
@app.get("/health")
async def health():
    return {"status": "ok", "data_path": str(config.DATA_BASE_PATH)}

@app.post("/auth/login")
async def login(username: str, password: str, workspace_id: Optional[str] = None):
    user = authenticate_user(username, password, workspace_id=workspace_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ws = _normalize_workspace(user.get("workspace_id"), user)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"], "workspace_id": ws}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"],
        "workspace_id": ws,
    }

@app.post("/ingest/config2")
async def ingest_from_config2(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    source_path = str(request.source_path or "").strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")

    build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    source_type = _infer_source_type(source_path, request.source_type)
    workspace_id = _normalize_workspace(request.workspace_id, current_user)

    dynamic_cfg = {
        "ingestion_name": f"{workspace_id}_{source_type}",
        "sources": [
            {
                "type": source_type,
                "path": source_path,
                "params": {"path": source_path},
            }
        ],
        "output": {"base_path": str(config.DATA_BASE_PATH)},
    }

    # Ingestion runs in the background (thread-offloaded) so the request
    # returns immediately and doesn't block the server for other users
    # while a large import is in progress. Poll GET /ingest/status/{build_id}.
    background_tasks.add_task(ingestion_jobs.start_ingestion, build_id, dynamic_cfg, source_path)

    return {
        "success": True,
        "build_id": build_id,
        "source_path": source_path,
        "source_type": source_type,
        "workspace_id": workspace_id,
        "status": "pending",
    }


@app.get("/ingest/status/{build_id}")
async def ingest_status(build_id: str, current_user: dict = Depends(get_current_user)):
    status = ingestion_jobs.get_status(build_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"No ingestion job found for '{build_id}'")
    return status

# -------------------- PROTECTED ENDPOINTS (all require valid token) --------------------
@app.post("/chat")
async def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    try:
        response = await handlers.handle_chat(
            request.message, session_id, x_ingestion_id, 
            role=x_role,
            project_id=x_project,
            user_id=current_user["username"],
            workspace_id=_normalize_workspace(x_workspace_id, current_user),
        )
        return {"response": response, "session_id": session_id}
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        return {"response": f"An error occurred: {str(e)}", "session_id": session_id}

@app.post("/chart")
async def chart(
    request: ChartRequest,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    chart_json, error = await handlers.handle_chart(
        request.message, session_id, x_ingestion_id,
        role=x_role,
        project_id=x_project,
        user_id=current_user["username"],
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    if error:
        return {"error": error, "session_id": session_id}
    return {"chart": chart_json, "session_id": session_id}

@app.get("/chat/history/{session_id}")
async def get_chat_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    target_user: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    target = str(target_user or "").strip().lower()
    if target and target != str(current_user["username"]).strip().lower() and not _is_admin_role(current_user.get("role")):
        raise HTTPException(status_code=403, detail="Not allowed to access other users history")

    history = memory.get_chat_history(
        session_id,
        limit=100,
        user_id=target or current_user["username"],
        ingestion_id=normalized_ingestion_id,
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    return {"session_id": session_id, "history": history}

@app.get("/chart/history/{session_id}")
async def get_chart_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    target_user: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    target = str(target_user or "").strip().lower()
    if target and target != str(current_user["username"]).strip().lower() and not _is_admin_role(current_user.get("role")):
        raise HTTPException(status_code=403, detail="Not allowed to access other users history")

    history = memory.get_chart_history(
        session_id,
        limit=100,
        user_id=target or current_user["username"],
        ingestion_id=normalized_ingestion_id,
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    return {"session_id": session_id, "history": history}

@app.delete("/chart/{chart_id}")
async def delete_chart(
    chart_id: str,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    if not state.lance_db or "chart_history" not in state.lance_db.table_names():
        return {"error": "Chart history not available"}
    try:
        import pandas as pd

        table = state.lance_db.open_table("chart_history")
        all_df = table.to_pandas()
        if all_df.empty:
            return {"error": "Chart not found"}

        user_key = str(current_user["username"]).strip().lower()
        ws_key = _normalize_workspace(x_workspace_id, current_user)
        if "user_id" in all_df.columns:
            owned = all_df[(all_df["user_id"] == user_key) & (all_df["id"] == chart_id)]
            if "workspace_id" in all_df.columns:
                owned = owned[owned["workspace_id"] == ws_key]
        else:
            owned = all_df[all_df["id"] == chart_id]

        if owned.empty:
            return {"error": "Chart not found or not owned by current user"}

        updated_df = all_df[all_df["id"] != chart_id]
        if len(updated_df) == 0:
            state.lance_db.drop_table("chart_history")
            empty_df = pd.DataFrame(columns=[
                "id", "workspace_id", "user_id", "ingestion_id", "session_id", "type", "prompt", "response", "config",
                "created_at", "metadata"
            ])
            state.lance_db.create_table("chart_history", empty_df)
        else:
            state.lance_db.drop_table("chart_history")
            state.lance_db.create_table("chart_history", updated_df)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error deleting chart: {e}")
        return {"error": str(e)}

@app.get("/debug/data")
async def debug_data(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    data = {}
    if state.duck_conn:
        tables = state.duck_conn.execute("SHOW TABLES").fetchall()
        data["tables"] = [t[0] for t in tables]
        test_table = _get_test_results_table()
        # Check if test table exists
        if test_table in data["tables"]:
            sample = state.duck_conn.execute(f"SELECT * FROM {test_table} LIMIT 5").df()
            data["test_results_sample"] = sample.to_dict(orient="records")
            data["test_results_count"] = state.duck_conn.execute(f"SELECT COUNT(*) FROM {test_table}").fetchone()[0]
    return data

@app.get("/data/status")
async def data_status(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    try:
        return _get_status_payload(normalized_ingestion_id)
    except Exception as e:
        logger.error(f"Error in /data/status: {e}")
        return {"has_data": False, "total_rows": 0, "status_summary": {"passed": 0, "failed": 0}}


@app.get("/data/profile")
async def data_profile(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    if not state.duck_conn:
        return {"tables": {}}

    try:
        return data_loader.get_data_profile(sample_rows=5)
    except Exception as e:
        logger.error(f"Error in /data/profile: {e}")
        return {"tables": {}, "error": str(e)}


@app.get("/data/quality")
async def data_quality(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    try:
        return _get_quality_payload(normalized_ingestion_id)
    except Exception as e:
        logger.error(f"Error in /data/quality: {e}")
        return {
            "score": 0,
            "quality": "poor",
            "checks": [],
            "guidance": [f"Quality evaluation failed: {e}"],
        }


@app.get("/dashboard/overview")
async def dashboard_overview(
    x_ingestion_id: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    include_quality: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()

    status_payload = {"has_data": False, "total_rows": 0, "status_summary": {"passed": 0, "failed": 0}}
    quality_payload = {
        "score": 0,
        "quality": "unknown",
        "checks": [],
        "guidance": ["No ingestion selected"],
    }

    if normalized_ingestion_id:
        if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
            data_loader.init_data(normalized_ingestion_id)
        try:
            status_payload = _get_status_payload(normalized_ingestion_id)
        except Exception as e:
            logger.error(f"Error computing overview status: {e}")
        try:
            quality_payload = (
                _get_quality_payload(normalized_ingestion_id)
                if include_quality
                else _get_cached_quality_payload(normalized_ingestion_id)
            )
        except Exception as e:
            logger.error(f"Error computing overview quality: {e}")

    persistent = token_usage_store.get_usage(
        user_id=current_user.get("username"),
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )

    return {
        "connected": True,
        "ingestion_id": normalized_ingestion_id,
        "status": status_payload,
        "quality": quality_payload,
        "token_usage": {
            "totals": persistent.get("totals", {}),
            "by_model": persistent.get("by_model", {}),
            "scope": persistent.get("scope", {}),
            "updated_at": persistent.get("updated_at", ""),
        },
        "runtime_token_usage": {
            "totals": state.token_usage,
            "by_model": state.token_usage_by_model,
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ingestions")
async def list_ingestions(current_user: dict = Depends(get_current_user)):
    """Return list of available ingestion IDs with metadata (prefer JSON summary)."""
    ingestions = []
    for path in config.DATA_BASE_PATH.iterdir():
        if path.is_dir() and (path / "lancedb").exists():
            if ingestion_jobs.is_failed(path.name):
                # Ingestion started but failed partway — don't present a
                # half-written build as a usable one.
                continue
            summary_json = path / "summary.json"
            summary_text = ""
            if summary_json.exists():
                try:
                    with open(summary_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    summary_text = json.dumps(data.get("metrics", {}), indent=2)
                except Exception as e:
                    logger.warning(f"Could not read {summary_json}: {e}")
            else:
                summary_md = path / "summary.md"
                if summary_md.exists():
                    try:
                        summary_text = summary_md.read_text(encoding='utf-8')
                    except Exception:
                        summary_text = ""
            
            ingestions.append({
                "id": path.name,
                "summary": summary_text,
                "created": path.stat().st_mtime
            })
    
    sorted_ingestions = sorted(ingestions, key=lambda x: x["created"])
    for i, item in enumerate(sorted_ingestions):
        item["build_label"] = f"Build {i + 1}"
    
    return {"ingestions": sorted(sorted_ingestions, key=lambda x: x["created"], reverse=True)}


@app.get("/suggestions")
async def role_suggestions(
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    role_id = str(x_role or current_user.get("role") or "qa-engineer").strip()
    project_id = str(x_project or "all").strip()

    role_instruction = ""
    try:
        if state.role_manager is None:
            from .role_manager import RoleManager
            state.role_manager = RoleManager()
        role_instruction = state.role_manager.get_role_instruction(role_id) or ""
    except Exception:
        role_instruction = ""

    schema_profile = data_loader.get_data_profile(sample_rows=2)
    quality = data_loader.get_ingestion_quality_report()
    llm = llm_client.LLMClient()

    prompt = SUGGESTION_PROMPT.format(
        role_id=role_id,
        project_id=project_id,
        role_instruction=role_instruction or "No explicit role file found. Use role id semantics.",
        schema_profile=json.dumps(schema_profile, ensure_ascii=False)[:8000],
        quality_summary=json.dumps(quality, ensure_ascii=False)[:3000],
    )

    workspace_id = _normalize_workspace(x_workspace_id, current_user)
    raw_primary = await llm.agenerate(
        prompt,
        temperature=0.2,
        max_tokens=1000,
        user_id=current_user.get("username"),
        workspace_id=workspace_id,
    )
    parsed_primary = _parse_suggestions_payload(raw_primary, role_id, schema_profile)
    if parsed_primary:
        return {"role": role_id, "project": project_id, "source": "ai", **parsed_primary}

    retry_prompt = _build_retry_suggestion_prompt(
        role_id=role_id,
        project_id=project_id,
        role_instruction=role_instruction,
        schema_profile=schema_profile,
        quality=quality,
    )
    raw_retry = await llm.agenerate(
        retry_prompt,
        temperature=0.1,
        max_tokens=900,
        user_id=current_user.get("username"),
        workspace_id=workspace_id,
    )
    parsed_retry = _parse_suggestions_payload(raw_retry, role_id, schema_profile)
    if parsed_retry:
        return {"role": role_id, "project": project_id, "source": "ai-retry", **parsed_retry}

    parsed_partial = _salvage_suggestions_payload(
        f"{raw_primary or ''}\n{raw_retry or ''}",
        role_id,
        schema_profile,
    )
    if parsed_partial:
        return {"role": role_id, "project": project_id, "source": "ai-partial", **parsed_partial}

    data = _normalize_suggestions({}, role_id, schema_profile)
    return {"role": role_id, "project": project_id, "source": "fallback", **data}


@app.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    x_ingestion_id: str = Header(...),
    x_session_id: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    if not state.lance_db:
        raise HTTPException(status_code=500, detail="Data store not initialized")

    target_kind = str(request.target_kind or "chat").strip().lower()
    feedback_type = str(request.feedback_type or "improve").strip().lower()
    if target_kind not in {"chat", "chart", "ui"}:
        raise HTTPException(status_code=400, detail="target_kind must be chat, chart, or ui")
    if feedback_type not in {"up", "down", "improve", "positive", "negative"}:
        raise HTTPException(status_code=400, detail="feedback_type must be up, down, improve, positive, or negative")

    ok = memory.store_feedback(
        user_id=current_user["username"],
        ingestion_id=normalized_ingestion_id,
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
        session_id=x_session_id or request.session_id,
        target_kind=target_kind,
        feedback_type=feedback_type,
        prompt=request.prompt,
        response=request.response,
        chart_id=request.chart_id,
        notes=request.notes,
        tags=request.tags,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Could not store feedback")

    prefs = memory.get_feedback_preferences(
        current_user["username"],
        normalized_ingestion_id,
        _normalize_workspace(x_workspace_id, current_user),
        target_kind,
    )
    return {"success": True, "preferences": prefs}

@app.get("/projects")
async def list_projects(current_user: dict = Depends(get_current_user)):
    if state.project_manager is None:
        from .project_manager import ProjectManager
        state.project_manager = ProjectManager()
    return {"projects": state.project_manager.list_projects()}

@app.get("/roles")
async def list_roles(current_user: dict = Depends(get_current_user)):
    if state.role_manager is None:
        from .role_manager import RoleManager
        state.role_manager = RoleManager()
    return {"roles": state.role_manager.list_roles()}

@app.get("/test/llm")
async def test_llm(current_user: dict = Depends(get_current_user)):
    llm = llm_client.LLMClient()
    resp = await llm.agenerate(
        "Say hello in one word",
        user_id=current_user.get("username"),
        workspace_id=_normalize_workspace(None, current_user),
    )
    return {"llm_response": resp}

@app.get("/test/sql")
async def test_sql(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    if state.duck_conn:
        try:
            result = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()
            return {"count": result[0]}
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": "duck_conn not initialized"}


@app.get("/usage/tokens")
async def token_usage(current_user: dict = Depends(get_current_user)):
    persistent = token_usage_store.get_usage(
        user_id=current_user.get("username"),
        workspace_id=_normalize_workspace(None, current_user),
    )
    return {
        "totals": persistent.get("totals", {}),
        "by_model": persistent.get("by_model", {}),
        "scope": persistent.get("scope", {}),
        "updated_at": persistent.get("updated_at", ""),
        "runtime_totals": state.token_usage,
        "runtime_by_model": state.token_usage_by_model,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)