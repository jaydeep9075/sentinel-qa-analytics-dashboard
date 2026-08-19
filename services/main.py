import logging
import os
import copy
import uuid
import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request, BackgroundTasks, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
import asyncio
import uvicorn
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse
from . import config, state, data_loader, handlers, memory, llm_client, ingestion_jobs, schema_context
from . import token_usage_store, auto_ingest, build_owner, app_settings, audit_log, ingestion_service
from jose import JWTError, jwt
from . import auth as auth_module
from .prompts import SUGGESTION_PROMPT
from .auth import (
    AuthError,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_user_store,
    hash_password,
    initialize_auth_store,
    is_admin,
    register_user,
    rename_account,
    require_admin,
)
from . import permissions
from .permissions import (
    PERM_DATA_DELETE,
    PERM_DATA_INGEST,
    require_permission,
)
from .live_exec import store as live_store
from .live_exec.router import router as live_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_STATUS_CACHE_TTL_SECONDS = 10.0
_QUALITY_CACHE_TTL_SECONDS = 20.0
_SUGGESTIONS_CACHE_TTL_SECONDS = 120.0
_INGESTIONS_CACHE_TTL_SECONDS = 15.0
_INSIGHTS_CACHE_TTL_SECONDS = 20.0
_status_cache: dict[str, tuple[float, dict]] = {}
_quality_cache: dict[str, tuple[float, dict]] = {}
_insights_cache: dict[str, tuple[float, dict]] = {}
_suggestions_cache: dict[str, tuple[float, dict]] = {}
_ingestions_cache: dict[str, tuple[float, dict]] = {}
# The ingestions list is cached per viewer scope ("admin" or "ws:<workspace>")
# rather than under one global key â€” see list_ingestions().
_PERF_PATH_PREFIXES = (
    "/dashboard/overview",
    "/data/status",
    "/data/quality",
    "/ingestions",
    "/chart/history/",
)

def _get_test_results_table() -> str:
    """Get the actual table name for test results.
    Supports both old (flattened_tests) and new (structured_test_results) names."""
    try:
        with state._duck_query_lock:
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


class ConnectorTestRequest(BaseModel):
    connector_type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class BuildIngestRequest(BaseModel):
    connector_type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    display_name: Optional[str] = None
    workspace_id: Optional[str] = None


_WIZARD_CONNECTOR_TYPES = {"allure", "csv", "excel", "database", "api"}
_UPLOAD_EXTENSIONS = {
    "allure": (".zip",),
    "csv": (".csv", ".tsv"),
    "excel": (".xlsx", ".xls"),
}


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    # Advisory: shown to the approving admin as "this is the team they say
    # they're on". It does not grant membership - the admin assigns the real
    # workspace at approval time.
    requested_workspace: Optional[str] = None


class AdminCreateUserRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = None
    workspace_id: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    token_limit: Optional[int] = None
    # An admin-created account skips the "you must change your password"
    # gate by default - unlike the bootstrap admin, whoever created it
    # presumably communicated the password out of band and the account is
    # usable immediately. Set true to force a change on first login instead
    # (e.g. handing someone a temporary password over chat).
    must_change_password: bool = False


class AdminUpdateUserRequest(BaseModel):
    role: Optional[str] = None
    workspace_id: Optional[str] = None
    status: Optional[str] = None  # pending | active | disabled
    email: Optional[str] = None
    full_name: Optional[str] = None
    token_limit: Optional[int] = None
    must_change_password: Optional[bool] = None


class AdminPasswordRequest(BaseModel):
    password: str
    # Defaults to true: an admin-issued password is, definitionally, known to
    # someone other than the account owner until they change it. Set false
    # only when that's an accepted risk (e.g. restoring a break-glass account
    # you control end-to-end).
    force_change: bool = True


class AccountPasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AccountUsernameRequest(BaseModel):
    current_password: str
    new_username: str


class AdminLLMSettingsRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    clear_api_key: bool = False


class AdminLLMTestRequest(BaseModel):
    # All optional: omitted fields fall back to whatever is currently
    # effective (env/DB/default), so "Test connection" works both for a
    # brand-new value not yet saved and for re-checking what's already live.
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None


class AdminEmbeddingSettingsRequest(BaseModel):
    model: str


class AdminSecretKeyRequest(BaseModel):
    # Both optional, mutually exclusive in practice: set `value` to pick your
    # own (must be 32+ chars), or `generate=true` to have the server mint a
    # random one. Either way this signs everyone out - see the confirm flag.
    value: Optional[str] = None
    generate: bool = False
    confirm: bool = False


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
    """The workspace this request operates in.

    The token wins. The `x-workspace-id` header used to take precedence over
    it, which meant any authenticated user could read and write another
    team's chat history, charts and token accounting just by setting a header
    - the header was effectively an unauthenticated tenant switch.

    It is still honoured for ADMINS, because "look at another workspace" is a
    real administrative need and an admin can already see everything. For
    everyone else it is ignored, not rejected: the frontend sends the header
    on most requests, and 400-ing a stale value from a client that simply
    hasn't refreshed would break the dashboard for no security gain.
    """
    token_workspace = str((current_user or {}).get("workspace_id") or "").strip().lower()
    requested = str(workspace_id or "").strip().lower()

    if requested and requested != token_workspace:
        if _is_admin_role((current_user or {}).get("role")):
            return requested
        if current_user is not None:
            logger.warning(
                "Ignoring x-workspace-id=%r from non-admin '%s' (token workspace=%r)",
                requested, (current_user or {}).get("username"), token_workspace,
            )
        elif requested:
            # No authenticated user in scope (internal callers). Nothing to
            # cross-check against, so the explicit value is all there is.
            return requested

    if token_workspace:
        return token_workspace
    if requested and current_user is None:
        return requested
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


# How many chat/chart suggestions an ingestion offers. Four, not eight: these
# are a starting nudge for someone who hasn't thought of a question yet, and a
# long list reads as a form to fill in - it pushes the answer area off the
# panel and costs LLM tokens generating chips nobody clicks. The frontend
# (lib/roleSuggestions.ts MAX_SUGGESTIONS) renders exactly this many.
SUGGESTION_COUNT = 4


def _trim_suggestions(payload: dict) -> dict:
    """Cap both lists at SUGGESTION_COUNT, keeping the shape callers expect."""
    return {
        "chat": list(payload.get("chat", []))[:SUGGESTION_COUNT],
        "chart": list(payload.get("chart", []))[:SUGGESTION_COUNT],
    }


def _schema_driven_fallback_suggestions(schema_profile: Optional[dict]) -> Optional[dict]:
    """Generate simple suggestions directly from the real ingested schema,
    with no LLM call â€” the no-LLM safety net for non-QA datasets (CSV/PDF/
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
    if len(chat) < SUGGESTION_COUNT or len(chart) < SUGGESTION_COUNT:
        return None

    return {"chat": chat[:SUGGESTION_COUNT], "chart": chart[:SUGGESTION_COUNT]}


def _fallback_suggestions(role_id: Optional[str], schema_profile: Optional[dict] = None) -> dict:
    return _trim_suggestions(_fallback_suggestions_full(role_id, schema_profile))


def _fallback_suggestions_full(role_id: Optional[str], schema_profile: Optional[dict] = None) -> dict:
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

    chat_clean = [str(x).strip() for x in chat if str(x).strip()][:SUGGESTION_COUNT]
    chart_clean = [str(x).strip() for x in chart if str(x).strip()][:SUGGESTION_COUNT]
    if len(chat_clean) < SUGGESTION_COUNT or len(chart_clean) < SUGGESTION_COUNT:
        return fallback

    chat_clean = _repair_truncated_first_item(chat_clean, fallback["chat"])
    chart_clean = _repair_truncated_first_item(chart_clean, fallback["chart"])
    return {"chat": chat_clean[:SUGGESTION_COUNT], "chart": chart_clean[:SUGGESTION_COUNT]}


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
        return list(fallback_items[:SUGGESTION_COUNT])

    if _looks_truncated_item(repaired[0]):
        split_head = _split_truncated_item(repaired[0])
        if _looks_truncated_item(split_head) or len(split_head) < 18:
            repaired[0] = fallback_items[0]
        else:
            repaired[0] = split_head

    # Top up from the fallback only while it still has an entry to give -
    # the fallback is now capped at SUGGESTION_COUNT, so indexing past its
    # end is a real possibility rather than a theoretical one.
    while len(repaired) < SUGGESTION_COUNT and len(repaired) < len(fallback_items):
        repaired.append(fallback_items[len(repaired)])
    return repaired[:SUGGESTION_COUNT]


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
    # _repair_truncated_first_item already tops both lists up from the
    # fallback and caps them at SUGGESTION_COUNT.
    chat = _repair_truncated_first_item(chat, fallback["chat"])
    chart = _repair_truncated_first_item(chart, fallback["chart"])
    return {"chat": chat, "chart": chart}


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
        f"Strict schema: {{\"chat\":[{SUGGESTION_COUNT} strings],\"chart\":[{SUGGESTION_COUNT} strings]}}.\n"
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
        payload = {"has_data": False, "total_rows": 0, "status_summary": {"passed": 0, "failed": 0, "skipped": 0}}
        return _cache_set(_status_cache, normalized_ingestion_id, payload)

    test_table = _get_test_results_table()
    with state._duck_query_lock:
        row = state.duck_conn.execute(
            f"""
            SELECT
              COUNT(*) AS total_rows,
              SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS passed,
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) AS skipped
            FROM {test_table}
            """
        ).fetchone()
    total_rows = int(row[0] or 0)
    passed = int(row[1] or 0)
    failed = int(row[2] or 0)
    skipped = int(row[3] or 0)

    payload = {
        "has_data": total_rows > 0,
        "total_rows": total_rows,
        "status_summary": {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
    }
    return _cache_set(_status_cache, normalized_ingestion_id, payload)


_EMPTY_INSIGHTS = {
    "has_data": False,
    "readiness": {"verdict": "unknown", "label": "No data", "detail": "Select a build to see release readiness."},
    "pass_rate": 0.0,
    "blast_radius": {"impacted": 0, "total": 0, "top_area": "", "top_area_failures": 0},
    "top_failure": {"signature": "", "count": 0, "share": 0.0},
    "runtime": {
        "wall_clock_seconds": 0.0,
        "wall_clock_estimated": False,
        "total_seconds": 0.0,
        "avg_seconds": 0.0,
        "failed_seconds": 0.0,
        "slowest_area": "",
        "workers": 0,
        "hosts": 0,
    },
    "coverage": {"skipped": 0, "skipped_rate": 0.0},
}


def _readiness_verdict(pass_rate: float, failed: int, total: int) -> dict:
    """Turn raw counts into the one thing a release call actually needs.

    The thresholds are deliberately blunt - this is a go/no-go signal for a
    stakeholder skimming the page, not a statistical model. Anything more
    nuanced belongs in the charts below it.
    """
    if total <= 0:
        return {"verdict": "unknown", "label": "No data", "detail": "This build has no test results yet."}
    if failed == 0:
        return {
            "verdict": "ready",
            "label": "Ready to ship",
            "detail": f"All {total:,} tests passed on this build.",
        }
    if pass_rate >= 98.0:
        return {
            "verdict": "ready",
            "label": "Ready to ship",
            "detail": f"{failed:,} of {total:,} tests failing - under the 2% release threshold.",
        }
    if pass_rate >= 90.0:
        return {
            "verdict": "at_risk",
            "label": "At risk",
            "detail": f"{failed:,} failures need triage before this build ships.",
        }
    return {
        "verdict": "blocked",
        "label": "Blocked",
        "detail": f"{failed:,} of {total:,} tests failing - not shippable as-is.",
    }


def _failure_signature(error: str) -> str:
    """Collapse a stack trace to the one line that identifies the fault.

    Grouping on the raw `error` string produces one "cluster" per test (every
    trace carries its own line numbers and selectors), which tells a reader
    nothing. The first line, minus its variable tail, is what actually
    repeats across tests hitting the same defect.
    """
    text = str(error or "").strip()
    if not text:
        return ""
    first_line = text.splitlines()[0].strip()
    # Drop the trailing detail after a colon when the head looks like an
    # exception/assertion name - that head is the part that repeats.
    head = first_line.split(":", 1)[0].strip() if ":" in first_line else first_line
    signature = head if 4 <= len(head) <= 80 else first_line
    return signature[:120]


def _wall_clock_runtime(
    test_table: str, duration_expr: str, columns: set, cumulative_seconds: float
) -> dict:
    """How long the suite actually took, as opposed to how much test time it burned.

    Summing every test's duration answers "how many machine-hours did this
    cost", which is a real number but not the one anyone means by "suite
    runtime" - a 610-test Playwright run spread over 46 CI machines reported
    38.5h that way while the pipeline finished in well under an hour.

    Tests on one worker are strictly sequential, and workers run concurrently,
    so the run cannot finish before the busiest worker does: max(sum(duration)
    per worker) is the critical path. It is a floor rather than the exact
    pipeline time - it excludes queueing, container startup and any worker
    idle time between tests - so it is reported as an estimate. Where the data
    carries no worker identity at all there is nothing to divide by, and the
    cumulative total is returned unchanged rather than invented.
    """
    worker_col = next((c for c in ("worker", "labels_thread", "thread") if c in columns), None)
    host_col = next((c for c in ("host", "labels_host") if c in columns), None)
    if not worker_col:
        return {}

    try:
        with state._duck_query_lock:
            row = state.duck_conn.execute(
                f"""
                SELECT
                  MAX(worker_seconds) AS critical_path,
                  COUNT(*)            AS workers
                FROM (
                  SELECT SUM({duration_expr}) AS worker_seconds
                  FROM {test_table}
                  WHERE {worker_col} IS NOT NULL
                    AND TRIM(CAST({worker_col} AS VARCHAR)) <> ''
                  GROUP BY CAST({worker_col} AS VARCHAR)
                )
                """
            ).fetchone()
    except Exception as e:
        logger.warning(f"Insights: wall-clock query failed: {e}")
        return {}

    critical_path = float(row[0] or 0) if row else 0.0
    workers = int(row[1] or 0) if row else 0
    if workers <= 0 or critical_path <= 0:
        return {}

    hosts = 0
    if host_col:
        try:
            with state._duck_query_lock:
                hosts = int(
                    state.duck_conn.execute(
                        f"""
                        SELECT COUNT(DISTINCT CAST({host_col} AS VARCHAR))
                        FROM {test_table}
                        WHERE {host_col} IS NOT NULL
                          AND TRIM(CAST({host_col} AS VARCHAR)) <> ''
                        """
                    ).fetchone()[0]
                    or 0
                )
        except Exception as e:
            logger.warning(f"Insights: host-count query failed: {e}")

    # A single worker means the suite ran serially - the cumulative sum IS the
    # wall clock, and calling that an estimate would be needlessly hedged.
    return {
        "wall_clock_seconds": round(critical_path, 2),
        "wall_clock_estimated": workers > 1,
        "workers": workers,
        "hosts": hosts,
    }


def _get_insights_payload(normalized_ingestion_id: str) -> dict:
    """Business-level read of one build: ship/no-ship, blast radius, the
    dominant failure driver, and what the suite costs in wall-clock time.

    Everything here is a DuckDB aggregate over tables that are already in
    memory - same cost class as /data/status, no LLM and no disk I/O - so it
    rides along on the dashboard overview instead of being its own request.
    """
    cached = _cache_get(_insights_cache, normalized_ingestion_id, _INSIGHTS_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    if not state.duck_conn:
        return _cache_set(_insights_cache, normalized_ingestion_id, copy.deepcopy(_EMPTY_INSIGHTS))

    test_table = _get_test_results_table()
    payload = copy.deepcopy(_EMPTY_INSIGHTS)

    try:
        with state._duck_query_lock:
            columns = {c[0] for c in state.duck_conn.execute(f"DESCRIBE {test_table}").fetchall()}
    except Exception as e:
        logger.warning(f"Insights: could not describe {test_table}: {e}")
        return _cache_set(_insights_cache, normalized_ingestion_id, payload)

    has_error = "error" in columns
    # module_name is the canonical "area of the product" column; project_name
    # is the next best thing when a dataset never carried modules.
    if "module_name" in columns:
        area_col = "module_name"
    elif "project_name" in columns:
        area_col = "project_name"
    else:
        area_col = None

    duration_expr = "COALESCE(TRY_CAST(duration AS DOUBLE), 0)" if "duration" in columns else "0"

    try:
        with state._duck_query_lock:
            totals = state.duck_conn.execute(
                f"""
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS passed,
                  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                  SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) AS skipped,
                  SUM({duration_expr}) AS total_duration,
                  AVG({duration_expr}) AS avg_duration,
                  SUM(CASE WHEN status='failed' THEN {duration_expr} ELSE 0 END) AS failed_duration
                FROM {test_table}
                """
            ).fetchone()
    except Exception as e:
        logger.warning(f"Insights: totals query failed: {e}")
        return _cache_set(_insights_cache, normalized_ingestion_id, payload)

    total = int(totals[0] or 0)
    if total <= 0:
        return _cache_set(_insights_cache, normalized_ingestion_id, payload)

    passed = int(totals[1] or 0)
    failed = int(totals[2] or 0)
    skipped = int(totals[3] or 0)
    pass_rate = round((passed / total) * 100, 1)

    payload["has_data"] = True
    payload["pass_rate"] = pass_rate
    payload["readiness"] = _readiness_verdict(pass_rate, failed, total)
    payload["coverage"] = {
        "skipped": skipped,
        "skipped_rate": round((skipped / total) * 100, 1),
    }
    cumulative_seconds = round(float(totals[4] or 0), 2)
    payload["runtime"] = {
        "wall_clock_seconds": cumulative_seconds,
        "wall_clock_estimated": False,
        "total_seconds": cumulative_seconds,
        "avg_seconds": round(float(totals[5] or 0), 3),
        "failed_seconds": round(float(totals[6] or 0), 2),
        "slowest_area": "",
        "workers": 0,
        "hosts": 0,
    }
    payload["runtime"].update(_wall_clock_runtime(test_table, duration_expr, columns, cumulative_seconds))

    if area_col:
        try:
            with state._duck_query_lock:
                areas = state.duck_conn.execute(
                    f"""
                    SELECT
                      COALESCE(NULLIF(TRIM(CAST({area_col} AS VARCHAR)), ''), 'unknown') AS area,
                      COUNT(*) AS area_total,
                      SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS area_failed,
                      SUM({duration_expr}) AS area_duration
                    FROM {test_table}
                    GROUP BY 1
                    """
                ).fetchall()
        except Exception as e:
            logger.warning(f"Insights: area query failed: {e}")
            areas = []

        if areas:
            impacted = [a for a in areas if int(a[2] or 0) > 0]
            top_area = max(impacted, key=lambda a: int(a[2] or 0)) if impacted else None
            slowest = max(areas, key=lambda a: float(a[3] or 0))
            payload["blast_radius"] = {
                "impacted": len(impacted),
                "total": len(areas),
                "top_area": str(top_area[0]) if top_area else "",
                "top_area_failures": int(top_area[2] or 0) if top_area else 0,
            }
            if float(slowest[3] or 0) > 0:
                payload["runtime"]["slowest_area"] = str(slowest[0])

    if has_error and failed > 0:
        try:
            with state._duck_query_lock:
                errors = state.duck_conn.execute(
                    f"""
                    SELECT CAST(error AS VARCHAR) AS err
                    FROM {test_table}
                    WHERE status='failed'
                      AND error IS NOT NULL
                      AND TRIM(CAST(error AS VARCHAR)) <> ''
                    """
                ).fetchall()
        except Exception as e:
            logger.warning(f"Insights: failure-signature query failed: {e}")
            errors = []

        buckets: dict[str, int] = {}
        for row in errors:
            sig = _failure_signature(row[0])
            if sig:
                buckets[sig] = buckets.get(sig, 0) + 1
        if buckets:
            sig, count = max(buckets.items(), key=lambda kv: kv[1])
            payload["top_failure"] = {
                "signature": sig,
                "count": count,
                "share": round((count / failed) * 100, 1),
            }

    return _cache_set(_insights_cache, normalized_ingestion_id, payload)


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

def _find_most_recent_ingestion_id() -> Optional[str]:
    """Newest ingestion folder under DATA_BASE_PATH, by mtime.

    Used only to decide what to pre-warm at startup, never for auth/
    visibility, so it doesn't need to account for workspace ownership.
    """
    try:
        candidates = [
            p for p in config.DATA_BASE_PATH.iterdir()
            if p.is_dir() and (p / "lancedb").exists()
        ]
    except FileNotFoundError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime).name


async def _prewarm_default_ingestion() -> None:
    """Load the most recently created ingestion into the warm pool right
    after boot, off the event loop, so the first real dashboard request
    after a restart doesn't pay for the LanceDB -> pandas -> DuckDB
    rebuild that ensure_ingestion_loaded does on a cold miss. Runs as a
    background task (not awaited by lifespan) so it never delays the app
    from accepting connections/health checks.
    """
    try:
        ingestion_id = await run_in_threadpool(_find_most_recent_ingestion_id)
        if not ingestion_id:
            return
        ok = await run_in_threadpool(data_loader.ensure_ingestion_loaded, ingestion_id)
        if ok:
            logger.info("Pre-warmed ingestion '%s' at startup", ingestion_id)
        else:
            logger.warning("Pre-warm failed for ingestion '%s'", ingestion_id)
    except Exception:
        logger.warning("Pre-warm of default ingestion failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    config.validate_runtime_config()
    # Seed anything the mounted state directory is missing before the stores
    # that depend on it are opened.
    config.ensure_state_files()
    initialize_auth_store()
    live_store.init_db()

    # LLM config is no longer a hard startup failure (see
    # validate_runtime_config's docstring) - it CAN be finished later from
    # the Settings tab. But a deployment that's missing it shouldn't have to
    # discover that from a silent None response the first time someone
    # chats - say so once, loudly, at boot.
    try:
        llm_settings = app_settings.get_llm_settings()
        if not llm_settings.get("model") or (
            not llm_settings.get("keyless") and not llm_settings.get("api_key_set")
        ):
            logger.warning(
                "LLM is not fully configured (provider=%s model=%s api_key_set=%s). "
                "Chat and chart generation will fail until an administrator finishes "
                "setup in the Settings tab or in .env.",
                llm_settings.get("provider"), llm_settings.get("model"),
                llm_settings.get("api_key_set"),
            )
    except Exception:
        logger.warning("Could not check LLM configuration at startup", exc_info=True)

    await auto_ingest.start()
    asyncio.create_task(_prewarm_default_ingestion())
    yield
    logger.info("Shutting down...")
    await auto_ingest.stop()
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
app.include_router(live_router)


# Build ids minted by every ingestion path (`ingestion_YYYYMMDD_HHMMSS`).
# Live-execution runs use `run_<hex>` and are deliberately not matched.
_BUILD_ID_RE = re.compile(r"^ingestion_\d{8}_\d{6}$")


def _user_from_request(request: Request) -> Optional[dict]:
    """Decode the bearer token off a raw Request, or None.

    Middleware runs before FastAPI resolves dependencies, so Depends() isn't
    available here. Returning None on any problem is safe: the route's own
    Depends(get_current_user) still rejects an absent or invalid token, so
    this can only ever be *additional* enforcement, never the only one.
    """
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        payload = jwt.decode(token.strip(), app_settings.get_secret_key(), algorithms=[auth_module.ALGORITHM])
    except JWTError:
        return None
    if not payload.get("sub"):
        return None
    return {
        "username": payload.get("sub"),
        "role": payload.get("role"),
        "workspace_id": str(payload.get("workspace_id") or "").strip().lower(),
    }


@app.middleware("http")
async def build_visibility_middleware(request: Request, call_next):
    """Refuse to serve a build the caller's workspace doesn't own.

    Roughly fourteen endpoints select their dataset with an `x-ingestion-id`
    header. Filtering only the /ingestions *list* would hide other teams'
    builds from the dropdown while leaving every one of those endpoints happy
    to answer for an id typed by hand - so the list would be cosmetic. One
    middleware covers all of them at once, and covers routes added later
    without anyone having to remember the check.

    An id that doesn't resolve to a build directory is passed through
    untouched: live-execution runs use the same header with their own id
    space, and there is nothing to protect on a path that holds no build.
    """
    ingestion_id = (request.headers.get("x-ingestion-id") or "").strip()
    if ingestion_id:
        user = _user_from_request(request)
        if user is not None:
            build_path = build_owner.resolve_build_path(ingestion_id)
            if build_path is None:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid ingestion id"}
                )
            if build_path.is_dir() and (build_path / "lancedb").exists():
                if not build_owner.can_view(build_owner.read_owner(build_path), user):
                    logger.warning(
                        "Blocked cross-workspace access: user=%s workspace=%s build=%s",
                        user.get("username"), user.get("workspace_id"), ingestion_id,
                    )
                    # 404, not 403: confirming a build exists in another
                    # workspace is itself a small leak, and the caller has no
                    # legitimate way to know the id.
                    return JSONResponse(
                        status_code=404, content={"detail": "Ingestion not found"}
                    )
            elif not build_path.exists() and _BUILD_ID_RE.match(ingestion_id):
                # A deleted build. Without this the handlers happily answer
                # with an empty dataset (has_data: false, 0 rows), so the
                # dashboard renders a blank-but-working build instead of
                # saying it's gone - which reads as "the delete broke
                # something" rather than "the delete worked".
                #
                # Restricted to the ingestion_* id shape on purpose: live
                # runs share this header with their own id space and may
                # legitimately have no directory yet, and a build mid-ingest
                # has a directory but not yet a lancedb, so neither is caught.
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Ingestion '{ingestion_id}' no longer exists"},
                )
    return await call_next(request)


# Reachable with a valid token even while must_change_password is set. Kept
# short and explicit rather than "everything under /auth" - /auth/register
# and /auth/registration-policy don't need a token at all and are excluded on
# purpose so this list only has to reason about the credential-change flow
# itself, not registration.
_CREDENTIAL_CHANGE_ALLOWED_PATHS = frozenset({
    "/health",
    "/auth/login",
    "/auth/me",
    "/auth/permissions",
    "/auth/account/password",
    "/auth/account/username",
})


@app.middleware("http")
async def credential_change_middleware(request: Request, call_next):
    """Lock a must-change-password session to exactly the change-credential
    screen.

    This is what makes shipping a well-known default admin password (see
    config.BOOTSTRAP_ADMIN_PASSWORD) safe: the token issued for that account
    is valid, but every route except the handful above refuses it until the
    password (and, if still the default username, the username) has been
    replaced. Also fires for an admin-issued reset with force_change=true.

    Reads the flag fresh from the store rather than trusting the JWT: the JWT
    is a snapshot from login time, and an admin can flip this flag for an
    ALREADY-LOGGED-IN user (a password reset mid-session), which a stale
    claim in the token would never see until re-login.
    """
    path = request.url.path
    if path not in _CREDENTIAL_CHANGE_ALLOWED_PATHS and not path.startswith("/docs") \
            and not path.startswith("/openapi") and not path.startswith("/redoc"):
        user = _user_from_request(request)
        if user is not None and config.AUTH_BACKEND == "db":
            try:
                # Same rule the login response reports, so a session is never
                # waved past the login screen only to be 403'd by every panel
                # it lands on - see auth.credential_change_is_forced().
                must_change = auth_module.credential_change_is_forced(
                    user.get("username")
                )
            except Exception:
                # Fail open on a store error: this is a UX guardrail, not the
                # authorization boundary itself (require_admin/require_permission
                # still gate every sensitive route independently). Refusing
                # every request because of a transient DB hiccup would be a
                # worse failure mode than letting one slip through.
                must_change = False
            if must_change:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "You must set a new username and password before continuing.",
                        "must_change_password": True,
                    },
                )
    return await call_next(request)


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
    """Sign in. `workspace_id` is accepted for backwards compatibility and
    ignored â€” the workspace comes from the account, not from the client."""
    uname_for_audit = str(username or "").strip().lower()
    try:
        user = authenticate_user(username, password)
    except AuthError as exc:
        # AuthError is only raised AFTER the password already matched (see
        # auth._raise_if_blocked_and_password_matches) - "pending" and
        # "disabled" are worth a distinct audit trail from a wrong password.
        audit_log.record("login_blocked", uname_for_audit, success=False, details={"reason": exc.detail})
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not user:
        audit_log.record("login_failed", uname_for_audit, success=False)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Signing in with the shipped default is a soft prompt (Change now /
    # Remind later), not a hard lock - but it stays a prompt for as long as
    # the password is still the default, which means deciding it fresh on
    # every login instead of consuming a flag on the first one. This used to
    # clear must_change_password here, which is a write on the login path:
    # it discarded policy an admin may have set on purpose, and it made the
    # answer depend on how many times the account had signed in before.
    # Nothing about the credential is mutated by signing in any more.
    default_password_prompt = (
        auth_module.is_default_password_value(password)
        and auth_module.user_has_default_password(user["username"])
    )
    must_change_password = auth_module.credential_change_is_forced(
        user["username"], bool(user.get("must_change_password"))
    )

    audit_log.record("login", user["username"], workspace_id=user.get("workspace_id", ""))
    ws = str(user.get("workspace_id") or config.DEFAULT_WORKSPACE_ID).strip().lower()
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"], "workspace_id": ws}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"],
        "username": user["username"],
        "workspace_id": ws,
        # Read fresh at login rather than trusted from the JWT: the flag can
        # flip after a token is issued (an admin resets a password with
        # force_change), and the JWT is not re-decoded on every request just
        # to check it - see credential_change_middleware, which re-reads it
        # from the store on each protected request instead of relying on
        # this snapshot.
        "must_change_password": must_change_password,
        "default_password_prompt": bool(default_password_prompt),
        "default_password_message": (
            "You are signed in with the default password. "
            "Change it now to secure your account."
            if default_password_prompt
            else ""
        ),
    }


@app.post("/auth/register")
async def register(payload: RegisterRequest):
    """Request an account. Creates a PENDING user that cannot log in until an
    admin approves it (unless AUTH_AUTO_APPROVE_REGISTRATION is on)."""
    try:
        result = register_user(
            username=payload.username,
            password=payload.password,
            email=payload.email or "",
            requested_workspace=payload.requested_workspace or "",
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    audit_log.record("register", result["user"]["username"], details={"status": result["status"]})
    if result["status"] == "active":
        return {
            "status": "active",
            "message": "Account created. You can sign in now.",
            "username": result["user"]["username"],
        }
    return {
        "status": "pending",
        "message": "Registration received. An administrator must approve your "
                   "account before you can sign in.",
        "username": result["user"]["username"],
    }


@app.get("/auth/registration-policy")
async def registration_policy():
    """Lets the login page decide whether to show a "Create account" link
    instead of hardcoding an assumption the deployment may have turned off."""
    return {
        "self_registration_enabled": config.AUTH_ALLOW_SELF_REGISTRATION,
        "auto_approve": config.AUTH_AUTO_APPROVE_REGISTRATION,
    }


@app.get("/auth/me")
async def whoami(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user.get("username"),
        "role": current_user.get("role"),
        "workspace_id": current_user.get("workspace_id"),
        "is_admin": is_admin(current_user),
        # The hard-lock rule, not the raw column: the dashboard and the admin
        # layout bounce to /account?forced=1 on this, and an account that is
        # merely still on the shipped default gets the login-screen prompt
        # instead. Reporting the raw flag here would redirect it away from
        # every page it is in fact allowed to use. The admin console reads
        # the raw column via /admin/users, which is where seeing the flag an
        # admin actually set is the point.
        "must_change_password": auth_module.credential_change_is_forced(
            current_user.get("username")
        ),
    }


@app.get("/auth/permissions")
async def auth_permissions(current_user: dict = Depends(get_current_user)):
    """What THIS account's role may do, plus who it belongs to. The frontend
    gates buttons and nav links on the permission list instead of hardcoding
    role-name comparisons in components, so a new role only has to be added
    in permissions.py to work everywhere.

    The identity fields ride along because the header's account menu needs a
    name and a workspace to show next to the role, and this is a call the
    frontend already makes on every page - a second round trip to /auth/me
    just to label an avatar would be one request per navigation for three
    strings that are already in hand here."""
    payload = permissions.permissions_payload(current_user)
    username = str(current_user.get("username") or "")
    full_name = ""
    try:
        # Only the db backend stores a display name; the token never carries
        # one. A failure here must not take down permission resolution - the
        # menu falls back to the username, which is always present.
        stored = auth_module.get_user_store().get_user(username) or {}
        full_name = str(stored.get("full_name") or "")
    except Exception:
        logger.debug("Could not read full_name for '%s'", username, exc_info=True)
    return {
        **payload,
        "username": username,
        "full_name": full_name,
        "workspace_id": current_user.get("workspace_id") or "",
    }


@app.post("/auth/account/password")
async def change_own_password(
    payload: AccountPasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """Every account's own escape hatch - including a must-change-password
    session, which credential_change_middleware allows to reach exactly this
    route and nothing else."""
    try:
        auth_module.change_own_password(
            current_user.get("username"), payload.current_password, payload.new_password
        )
    except AuthError as exc:
        audit_log.record("password_change", current_user.get("username"), success=False)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    logger.info("User '%s' changed their own password", current_user.get("username"))
    audit_log.record("password_change", current_user.get("username"))
    return {"success": True}


@app.post("/auth/account/username")
async def change_own_username(
    payload: AccountUsernameRequest,
    current_user: dict = Depends(get_current_user),
):
    """Renames the account and re-issues a token under the new name.

    A new token is not optional here: get_current_user trusts the JWT's
    `sub` claim without checking the store, so the OLD token would keep
    authenticating as a username that no longer has a row - every
    subsequent request would 401 until the browser somehow obtained a fresh
    token, which without this response it never would.
    """
    old_username = current_user.get("username")
    try:
        updated = auth_module.change_own_username(
            old_username, payload.current_password, payload.new_username
        )
    except AuthError as exc:
        audit_log.record("username_change", old_username, success=False, details={"error": exc.detail})
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    new_username = str(updated.get("username") or "")
    ws = str(updated.get("workspace_id") or config.DEFAULT_WORKSPACE_ID).strip().lower()
    access_token = create_access_token(
        data={"sub": new_username, "role": updated.get("role"), "workspace_id": ws}
    )
    logger.info("User '%s' renamed their account to '%s'", old_username, new_username)
    audit_log.record("username_change", new_username, target=old_username)
    return {
        "success": True,
        "username": new_username,
        "access_token": access_token,
        "token_type": "bearer",
        "role": updated.get("role"),
        "workspace_id": ws,
    }


# -------------------- ADMIN: USER MANAGEMENT --------------------
# Every route here is gated by require_admin, so the dashboard can offer user
# administration without anyone needing shell access to the container.

@app.get("/admin/users")
async def admin_list_users(
    status_filter: Optional[str] = Query(None, alias="status"),
    _admin: dict = Depends(require_admin),
):
    store = get_user_store()
    users = store.list_users(status=status_filter)
    return {
        "users": users,
        "workspaces": store.list_workspaces(),
        "pending_count": sum(1 for u in users if u["status"] == "pending")
        if not status_filter
        else len(store.list_users(status="pending")),
    }


def _validate_role(role: Optional[str]) -> Optional[str]:
    """Normalize and reject anything not in the known-role table.

    Without this, a typo'd role from the admin UI creates an account that
    silently has NO permissions (permissions.permissions_for_role() fails
    closed on an unknown role) - which looks like a bug report, not a
    rejected request.
    """
    if role is None:
        return None
    normalized = str(role).strip().lower()
    if normalized not in permissions.KNOWN_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role '{role}'. Valid roles: {', '.join(permissions.KNOWN_ROLES)}",
        )
    return normalized


@app.post("/admin/users")
async def admin_create_user(
    payload: AdminCreateUserRequest,
    admin: dict = Depends(require_admin),
):
    username = str(payload.username or "").strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    if len(payload.password or "") < config.MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters",
        )

    role = _validate_role(payload.role) or config.AUTH_DEFAULT_ROLE

    store = get_user_store()
    if store.get_user_record(username) is not None:
        raise HTTPException(status_code=409, detail="That username already exists")

    record = store.upsert_user(
        username=username,
        password_hash=hash_password(payload.password),
        role=role,
        workspace_id=(payload.workspace_id or config.AUTH_DEFAULT_WORKSPACE),
        email=payload.email or "",
        full_name=payload.full_name or "",
        status="active",
        must_change_password=bool(payload.must_change_password),
        token_limit=payload.token_limit,
    )
    logger.info("Admin '%s' created user '%s' (role=%s)", admin.get("username"), username, role)
    audit_log.record(
        "user_create", admin.get("username"), target=username,
        workspace_id=record.get("workspace_id", ""),
        details={"role": role},
    )
    return {"user": record}


@app.patch("/admin/users/{username}")
async def admin_update_user(
    username: str,
    payload: AdminUpdateUserRequest,
    admin: dict = Depends(require_admin),
):
    """Change role, workspace or status. Also the approval path: setting
    status=active on a pending user is what lets them log in."""
    store = get_user_store()
    target = str(username or "").strip().lower()
    record = store.get_user_record(target)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")

    new_role = _validate_role(payload.role)
    new_status = (payload.status or "").strip().lower() or None

    # Refuse the two edits that can leave the install with no way back in.
    _guard_last_admin(store, record, target, new_role, new_status)

    # Approving without a workspace would produce an active account with no
    # tenant, which would then fall through to the default workspace - i.e.
    # silently grant access to whatever lives there.
    resolved_workspace = payload.workspace_id
    if new_status == "active" and not (resolved_workspace or record.get("workspace_id")):
        resolved_workspace = record.get("requested_workspace") or config.AUTH_DEFAULT_WORKSPACE
    if new_status == "active" and not (new_role or record.get("role")):
        new_role = config.AUTH_DEFAULT_ROLE

    try:
        updated = store.update_user(
            username=target,
            role=new_role,
            workspace_id=resolved_workspace,
            status=new_status,
            email=payload.email,
            full_name=payload.full_name,
            token_limit=payload.token_limit,
            must_change_password=payload.must_change_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "Admin '%s' updated user '%s': role=%s workspace=%s status=%s",
        admin.get("username"), target, new_role, resolved_workspace, new_status,
    )
    # Approving a pending registration is the same PATCH call as any other
    # edit (status: "active"), so it's given its own action name here rather
    # than a generic "user_update" - the admin console's audit tab should be
    # able to answer "who approved this account" without diffing role/status
    # out of a details blob.
    action = "user_approve" if record.get("status") == "pending" and new_status == "active" else "user_update"
    audit_log.record(
        action, admin.get("username"), target=target,
        workspace_id=resolved_workspace or "",
        details={"role": new_role, "workspace_id": resolved_workspace, "status": new_status},
    )
    return {"user": updated}


@app.post("/admin/users/{username}/password")
async def admin_reset_password(
    username: str,
    payload: AdminPasswordRequest,
    admin: dict = Depends(require_admin),
):
    if len(payload.password or "") < config.MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters",
        )
    store = get_user_store()
    if not store.set_password_hash(username, hash_password(payload.password)):
        raise HTTPException(status_code=404, detail="User not found")
    if payload.force_change:
        store.set_must_change_password(username, True)
    logger.info(
        "Admin '%s' reset the password for '%s' (force_change=%s)",
        admin.get("username"), username, payload.force_change,
    )
    audit_log.record(
        "password_reset", admin.get("username"), target=username,
        details={"force_change": payload.force_change},
    )
    return {"success": True}


@app.delete("/admin/users/{username}")
async def admin_delete_user(username: str, admin: dict = Depends(require_admin)):
    store = get_user_store()
    target = str(username or "").strip().lower()
    record = store.get_user_record(target)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")

    if target == str(admin.get("username") or "").strip().lower():
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    _guard_last_admin(store, record, target, new_role=None, new_status="disabled")

    store.delete_user(target)
    logger.info("Admin '%s' deleted user '%s'", admin.get("username"), target)
    audit_log.record(
        "user_delete", admin.get("username"), target=target,
        workspace_id=record.get("workspace_id", ""),
    )
    return {"success": True}


def _guard_last_admin(store, record: dict, target: str, new_role, new_status) -> None:
    """Block an edit that would remove the final active admin.

    Without this, demoting or disabling yourself when you're the only admin
    leaves the deployment with no one able to reach /admin/users â€” recoverable
    only by exec-ing into the container. Cheap to prevent, tedious to undo.
    """
    was_admin = str(record.get("role") or "").lower() in {"admin", "cto"} and record.get("status") == "active"
    if not was_admin:
        return

    loses_admin = (new_role is not None and new_role not in {"admin", "cto"}) or (
        new_status is not None and new_status != "active"
    )
    if loses_admin and store.count_admins(exclude=target) == 0:
        raise HTTPException(
            status_code=400,
            detail="This is the only active administrator. Promote another user first.",
        )

@app.post("/ingest/config2")
async def ingest_from_config2(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_permission(PERM_DATA_INGEST)),
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
    background_tasks.add_task(
        ingestion_jobs.start_ingestion,
        build_id,
        dynamic_cfg,
        source_path,
        workspace_id=workspace_id,
        created_by=str(current_user.get("username") or ""),
        source="api",
    )
    _ingestions_cache.clear()

    return {
        "success": True,
        "build_id": build_id,
        "source_path": source_path,
        "source_type": source_type,
        "workspace_id": workspace_id,
        "status": "pending",
    }


@app.get("/ingest/connectors")
async def ingest_connectors(current_user: dict = Depends(require_permission(PERM_DATA_INGEST))):
    """Declarative schema (id/name/fields/formats) for the Add Build wizard's
    connector picker + dynamic config form. Every field returned here is
    genuinely honored by the corresponding connector - see
    services/ingestion_service.py for the source of truth."""
    return ingestion_service.IngestionService().get_connector_options()


@app.post("/ingest/upload-file")
async def ingest_upload_file(
    connector_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(PERM_DATA_INGEST)),
):
    """Stage a file (Allure .zip, CSV, Excel) uploaded from the wizard so a
    subsequent POST /ingest/build can reference it by path. Staged under a
    private per-upload directory rather than the auto-ingest drop-box
    (config.AUTO_INGEST_DIR) so the watcher never picks it up and
    double-ingests it - this endpoint's caller triggers ingestion explicitly.
    """
    ctype = str(connector_type or "").strip().lower()
    allowed_ext = _UPLOAD_EXTENSIONS.get(ctype)
    if not allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"File upload is not supported for connector type '{connector_type}'",
        )

    filename = Path(str(file.filename or "")).name
    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="A named file is required")
    if any(ch in filename for ch in ("/", "\\")) or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.lower().endswith(allowed_ext):
        raise HTTPException(
            status_code=400,
            detail=f"File must have one of these extensions: {', '.join(allowed_ext)}",
        )

    target_dir = config.DATA_BASE_PATH / "_uploads" / uuid.uuid4().hex
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not stage upload: {exc}") from exc

    final_path = target_dir / filename
    staging_path = target_dir / f"{filename}.part"
    written = 0
    try:
        with open(staging_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > config.INGEST_UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds the "
                               f"{config.INGEST_UPLOAD_MAX_BYTES // (1024 * 1024)}MB limit",
                    )
                out.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        os.replace(staging_path, final_path)
    except HTTPException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        logger.exception("Upload failed for %s", filename)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {"success": True, "staged_path": str(final_path), "filename": filename, "bytes": written}


def _redact_db_summary(connection_string: str) -> str:
    """Host/db only, never username or password - safe to log/audit."""
    try:
        parsed = urlparse(connection_string)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        db = (parsed.path or "").lstrip("/")
        return f"{parsed.scheme}://{host}{port}/{db}".rstrip("/")
    except Exception:
        return "(unparseable connection string)"


@app.post("/ingest/test-connection")
async def ingest_test_connection(
    request: ConnectorTestRequest,
    current_user: dict = Depends(require_permission(PERM_DATA_INGEST)),
):
    """A quick connectivity probe for Database/API connectors, run before
    committing to a full background ingestion. Never persists the tested
    config - it exists only for the duration of this request."""
    connector_type = str(request.connector_type or "").strip().lower()
    cfg = request.config or {}

    if connector_type == "database":
        def _run():
            from universal_ingester.connectors.db_connector import DBConnector
            raw_tables = cfg.get("tables")
            tables = None
            if raw_tables:
                if isinstance(raw_tables, list):
                    tables = [str(t).strip() for t in raw_tables if str(t).strip()]
                else:
                    tables = [t.strip() for t in str(raw_tables).split(",") if t.strip()]
            connector = DBConnector(
                connection_string=str(cfg.get("connection_string") or ""),
                tables=tables,
                connect_args=cfg.get("connect_args") or {},
            )
            try:
                return connector.test_connection()
            finally:
                connector.close()

        try:
            result = await run_in_threadpool(_run)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"success": True, **result}

    if connector_type == "api":
        def _run():
            from universal_ingester.connectors.api_connector import APIConnector
            headers = cfg.get("headers")
            if isinstance(headers, str):
                headers = json.loads(headers) if headers.strip() else {}
            connector = APIConnector(
                url=str(cfg.get("url") or ""),
                method=str(cfg.get("method") or "GET").upper(),
                headers=headers,
            )
            return connector.test_connection()

        try:
            result = await run_in_threadpool(_run)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"API test failed: {exc}") from exc
        return {"success": True, **result}

    raise HTTPException(
        status_code=400,
        detail="Test connection is only supported for 'database' and 'api' connectors",
    )


@app.post("/ingest/build")
async def ingest_build(
    request: BuildIngestRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_permission(PERM_DATA_INGEST)),
):
    """Connector-driven build creation for the Add Build wizard - the
    successor to /ingest/config2 for anything beyond a bare filesystem path
    (Database/API/CSV/Excel with real per-connector config). /ingest/config2
    is left untouched for backward compatibility."""
    connector_type = str(request.connector_type or "").strip().lower()
    if connector_type not in _WIZARD_CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown connector type: {request.connector_type}")

    cfg = dict(request.config or {})
    is_valid, message = ingestion_service.IngestionValidator.validate(connector_type, cfg)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    workspace_id = _normalize_workspace(request.workspace_id, current_user)
    display_name = str(request.display_name or "").strip()[:200]
    source_path_for_guard = ""  # only meaningful for file-based connectors' size pre-check

    cleanup_dir: Optional[str] = None
    if connector_type in ("allure", "csv", "excel"):
        path = str(cfg.get("path") or "").strip()
        source_path_for_guard = path
        # A path staged by POST /ingest/upload-file lives under a private
        # per-upload folder - remove that folder once ingestion finishes
        # (success or failure) so wizard uploads don't leak disk forever.
        try:
            uploads_root = (config.DATA_BASE_PATH / "_uploads").resolve()
            resolved = Path(path).resolve()
            if uploads_root in resolved.parents:
                cleanup_dir = str(resolved.parent)
        except Exception:
            pass
        engine_type = "allure" if connector_type == "allure" else "file"
        params: Dict[str, Any] = {"path": path}
        if connector_type == "csv":
            if cfg.get("delimiter"):
                params["delimiter"] = cfg["delimiter"]
            if cfg.get("has_header") is not None:
                params["has_header"] = bool(cfg["has_header"])
            if cfg.get("encoding"):
                params["encoding"] = cfg["encoding"]
        if connector_type == "excel" and cfg.get("sheet_name"):
            params["sheet_name"] = cfg["sheet_name"]
        source_summary = Path(path).name or path

    elif connector_type == "database":
        engine_type = "db"
        conn_str = str(cfg.get("connection_string") or "")
        raw_tables = cfg.get("tables")
        tables = None
        if raw_tables:
            if isinstance(raw_tables, list):
                tables = [str(t).strip() for t in raw_tables if str(t).strip()]
            else:
                tables = [t.strip() for t in str(raw_tables).split(",") if t.strip()]
        params = {
            "connection_string": conn_str,
            "tables": tables,
            "connect_args": cfg.get("connect_args") or {},
        }
        if cfg.get("batch_size"):
            try:
                params["batch_size"] = int(cfg["batch_size"])
            except (TypeError, ValueError):
                pass
        source_summary = _redact_db_summary(conn_str)

    else:  # api
        engine_type = "api"
        url = str(cfg.get("url") or "")
        headers = cfg.get("headers")
        if isinstance(headers, str):
            try:
                headers = json.loads(headers) if headers.strip() else {}
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Headers must be valid JSON")
        body = cfg.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body) if body.strip() else None
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Request body must be valid JSON")
        params = {
            "url": url,
            "method": str(cfg.get("method") or "GET").upper(),
            "headers": headers or {},
            "json_body": body,
        }
        source_summary = url

    dynamic_cfg = {
        "ingestion_name": f"{workspace_id}_{connector_type}",
        "sources": [{"type": engine_type, "params": params}],
        "output": {"base_path": str(config.DATA_BASE_PATH)},
    }

    background_tasks.add_task(
        ingestion_jobs.start_ingestion,
        build_id,
        dynamic_cfg,
        source_path_for_guard,
        workspace_id=workspace_id,
        created_by=str(current_user.get("username") or ""),
        source="wizard",
        display_name=display_name,
        cleanup_dir=cleanup_dir,
    )
    _ingestions_cache.clear()

    audit_log.record(
        "build_ingest_start",
        str(current_user.get("username") or ""),
        target=build_id,
        workspace_id=workspace_id,
        details={"connector_type": connector_type, "source_summary": source_summary},
    )

    return {
        "success": True,
        "build_id": build_id,
        "connector_type": connector_type,
        "workspace_id": workspace_id,
        "status": "pending",
    }


@app.post("/ingest/upload")
async def ingest_upload(
    request: Request,
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
):
    """Push an artifact over HTTP instead of onto a shared filesystem.

    The drop-box watcher needs the producer to be able to WRITE to the data
    volume. A GitHub Actions runner, a Lambda, or a build agent in another
    network usually can't â€” mounting the analytics volume into every CI
    environment is exactly the coupling you don't want. This endpoint is the
    same trigger reached over the network instead.

    Two ways to authenticate, because CI has no interactive login:
      * a normal bearer token (a human uploading through the dashboard), or
      * `x-api-key` matched against INGEST_API_KEYS, where the KEY determines
        the workspace. A pipeline token that leaks can only write into the
        team it was issued for.

    The upload lands in that workspace's drop-box directory and the watcher
    ingests it on its next pass, so uploads, mounted buckets and manual copies
    all converge on one code path rather than three that drift apart.
    """
    workspace_id, actor, actor_user = _resolve_ingest_identity(request, x_api_key, x_workspace_id)
    # A machine key (actor_user is None) is scoped to one workspace by
    # configuration already - INGEST_API_KEYS itself IS the authorization
    # decision for that path. A human caller still needs the role permission,
    # same as the dashboard's "Add Build" button (POST /ingest/config2).
    if actor_user is not None and not permissions.has_permission(actor_user, PERM_DATA_INGEST):
        raise HTTPException(status_code=403, detail="Your role does not have the 'data.ingest' permission")

    filename = Path(str(file.filename or "")).name
    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="A named file is required")
    # The filename becomes a path segment under a directory we control.
    if any(ch in filename for ch in ("/", "\\")) or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")

    target_dir = config.AUTO_INGEST_DIR / workspace_id
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drop-box is not writable: {exc}") from exc

    # Written under a .part suffix and renamed on completion. The watcher
    # skips in-flight suffixes, so a slow upload can't be picked up half
    # written even if it spans several scan intervals.
    final_path = target_dir / filename
    staging_path = target_dir / f"{filename}.part"
    written = 0
    try:
        with open(staging_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > config.INGEST_UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds the "
                               f"{config.INGEST_UPLOAD_MAX_BYTES // (1024 * 1024)}MB limit",
                    )
                out.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        os.replace(staging_path, final_path)
    except HTTPException:
        staging_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        staging_path.unlink(missing_ok=True)
        logger.exception("Upload failed for %s", filename)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    logger.info(
        "Accepted upload '%s' (%.1fMB) into workspace '%s' from %s",
        filename, written / (1024 * 1024), workspace_id, actor,
    )
    if not config.AUTO_INGEST_ENABLED:
        # Say so rather than letting the caller wait for an ingestion that is
        # never going to start.
        return {
            "success": True,
            "queued": False,
            "workspace_id": workspace_id,
            "path": str(final_path),
            "message": "File stored, but AUTO_INGEST_ENABLED is false so it "
                       "will not be ingested automatically.",
        }

    return {
        "success": True,
        "queued": True,
        "workspace_id": workspace_id,
        "filename": filename,
        "bytes": written,
        "message": f"Queued. The watcher ingests it within "
                   f"~{int(config.AUTO_INGEST_INTERVAL_SECONDS + config.AUTO_INGEST_STABLE_SECONDS)}s.",
    }


def _resolve_ingest_identity(
    request: Request,
    x_api_key: Optional[str],
    x_workspace_id: Optional[str],
) -> tuple[str, str, Optional[dict]]:
    """(workspace, actor-description, user-or-None) for an upload, or 401.

    API key first: it is the unambiguous machine path, and its workspace is
    fixed by configuration rather than by anything the caller sends. The
    third element is None for that path (there is no role to check) and the
    decoded user for a bearer-token upload (there is).
    """
    key = (x_api_key or "").strip()
    if key:
        workspace = config.INGEST_API_KEYS.get(key)
        if not workspace:
            raise HTTPException(status_code=401, detail="Invalid ingest API key")
        return workspace, "api-key", None

    user = _user_from_request(request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Provide a bearer token or an x-api-key from INGEST_API_KEYS",
        )
    return _normalize_workspace(x_workspace_id, user), f"user:{user.get('username')}", user


@app.get("/ingest/status/{build_id}")
async def ingest_status(build_id: str, current_user: dict = Depends(get_current_user)):
    build_path = build_owner.resolve_build_path(build_id)
    if build_path is None:
        raise HTTPException(status_code=400, detail="Invalid build id")
    # Status is polled while the build directory is still being created, so a
    # missing owner.json here means "not started yet", not "unowned" â€” check
    # visibility only once there is something to check.
    if (build_path / build_owner.OWNER_FILENAME).exists():
        if not build_owner.can_view(build_owner.read_owner(build_path), current_user):
            raise HTTPException(status_code=404, detail=f"No ingestion job found for '{build_id}'")

    status = ingestion_jobs.get_status(build_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"No ingestion job found for '{build_id}'")
    return status

# -------------------- PROTECTED ENDPOINTS (all require valid token) --------------------
def _enforce_token_quota(current_user: dict) -> None:
    """Refuse a new LLM-backed request once an account has spent its lifetime
    quota. Raises HTTPException(429).

    Checked here - once, at the top of the two routes that actually spend
    tokens - rather than inside llm_client, which is called many times per
    request (a chat turn can retry a SQL fix, regenerate chart code, etc.).
    Catching it before ANY of those calls also avoids burning further tokens
    on a request that's going to be refused anyway. 0 means unlimited, which
    is also what an account with no explicit limit reads as.
    """
    username = current_user.get("username")
    limit = get_user_store().get_token_limit(username)
    if limit <= 0:
        return
    spent = token_usage_store.get_lifetime_total(username)
    if spent >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Token quota exhausted ({spent:,}/{limit:,}). "
                   f"Ask an administrator to raise your limit.",
        )


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
    _enforce_token_quota(current_user)
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
    _enforce_token_quota(current_user)
    chart_json, error, chart_id = await handlers.handle_chart(
        request.message, session_id, x_ingestion_id,
        role=x_role,
        project_id=x_project,
        user_id=current_user["username"],
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    if error:
        return {"error": error, "session_id": session_id}
    # chart_id lets the browser render this figure straight away and still
    # match it against the history list on the next fetch, instead of waiting
    # for that fetch to find out what it just generated.
    return {"chart": chart_json, "chart_id": chart_id, "session_id": session_id}

@app.get("/chat/history/{session_id}")
async def get_chat_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    target_user: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])
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
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])
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
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

    if state.lance_db is None:
        raise HTTPException(status_code=404, detail="Chart history not available for this build")

    def _remove() -> bool:
        return memory.delete_chart(
            chart_id,
            user_id=current_user["username"],
            workspace_id=_normalize_workspace(x_workspace_id, current_user),
            ingestion_id=normalized_ingestion_id,
            # An admin deleting from the admin surface still needs to reach
            # charts they do not personally own; everyone else is scoped to
            # their own (workspace, user) pair.
            allow_any_owner=_is_admin_role(current_user.get("role")),
        )

    try:
        removed = await run_in_threadpool(_remove)
    except Exception as e:
        # Answering a failed delete with 200 + {"error": ...} is why this
        # looked like "delete does nothing" in the UI: the browser saw a
        # success, kept the card on screen, and nothing said why.
        logger.error(f"Error deleting chart {chart_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete chart")

    if not removed:
        raise HTTPException(status_code=404, detail="Chart not found, or not owned by the current user")

    return {"success": True, "id": chart_id}

@app.get("/debug/data")
async def debug_data(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])
    data = {}
    if state.duck_conn:
        with state._duck_query_lock:
            tables = state.duck_conn.execute("SHOW TABLES").fetchall()
        data["tables"] = [t[0] for t in tables]
        test_table = _get_test_results_table()  # locks internally - must stay outside any `with` block here
        # Check if test table exists
        if test_table in data["tables"]:
            with state._duck_query_lock:
                sample = state.duck_conn.execute(f"SELECT * FROM {test_table} LIMIT 5").df()
                data["test_results_count"] = state.duck_conn.execute(f"SELECT COUNT(*) FROM {test_table}").fetchone()[0]
            data["test_results_sample"] = sample.to_dict(orient="records")
    return data

@app.get("/data/status")
async def data_status(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

    try:
        return _get_status_payload(normalized_ingestion_id)
    except Exception as e:
        logger.error(f"Error in /data/status: {e}")
        return {"has_data": False, "total_rows": 0, "status_summary": {"passed": 0, "failed": 0, "skipped": 0}}


@app.get("/data/profile")
async def data_profile(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

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
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

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
    include_quality: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()

    status_payload = {"has_data": False, "total_rows": 0, "status_summary": {"passed": 0, "failed": 0, "skipped": 0}}
    quality_payload = {
        "score": 0,
        "quality": "unknown",
        "checks": [],
        "guidance": ["No ingestion selected"],
    }
    insights_payload = copy.deepcopy(_EMPTY_INSIGHTS)

    if normalized_ingestion_id:
        _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
        if _entry is not None:
            state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])
        if _entry is None:
            # Don't fall through to computing status/quality against
            # state.duck_conn - this request's context never got activated,
            # so it would just read the ContextVar default (None). Surfacing
            # a clear error beats silently caching empty/wrong numbers under
            # this ingestion_id's cache key.
            logger.error(f"Failed to load ingestion '{normalized_ingestion_id}' for overview")
            quality_payload = {
                "score": 0,
                "quality": "unknown",
                "checks": [],
                "guidance": [f"Ingestion '{normalized_ingestion_id}' could not be loaded. It may still be finalizing - retry shortly."],
            }
        else:
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
            try:
                # Same in-memory aggregates the status block already touched,
                # so this adds a handful of DuckDB scans rather than a round
                # trip - the dashboard's business band would otherwise need
                # its own request on every refresh.
                insights_payload = _get_insights_payload(normalized_ingestion_id)
            except Exception as e:
                logger.error(f"Error computing overview insights: {e}")

    # Token usage is intentionally NOT included here anymore - it used to be
    # embedded in every caller's dashboard overview regardless of role, which
    # is what made it visible on the home dashboard to every account. Spend
    # visibility is admin-only now: see PERM_USAGE_VIEW_ALL and
    # GET /admin/usage, which is the only place it's still exposed.
    return {
        "connected": True,
        "ingestion_id": normalized_ingestion_id,
        "status": status_payload,
        "quality": quality_payload,
        "insights": insights_payload,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ingestions")
async def list_ingestions(current_user: dict = Depends(get_current_user)):
    """Available builds, filtered to what this caller is allowed to see.

    Admins get every workspace (each row carries its workspace_id so the UI
    can label them); everyone else gets only their own. The cache key includes
    the viewer's scope â€” a single global key would serve one workspace's build
    list to the next caller for the whole TTL.
    """
    viewer_scope = (
        "admin"
        if _is_admin_role(current_user.get("role"))
        else f"ws:{_normalize_workspace(None, current_user)}"
    )
    cached = _cache_get(_ingestions_cache, viewer_scope, _INGESTIONS_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    ingestions = []
    for path in config.DATA_BASE_PATH.iterdir():
        if path.is_dir() and (path / "lancedb").exists():
            if ingestion_jobs.is_failed(path.name):
                # Ingestion started but failed partway â€” don't present a
                # half-written build as a usable one.
                continue
            owner = build_owner.read_owner(path)
            if not build_owner.can_view(owner, current_user):
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
                "created": path.stat().st_mtime,
                "workspace_id": owner.get("workspace_id", ""),
                "created_by": owner.get("created_by", ""),
                "source": owner.get("source", ""),
                "display_name": owner.get("display_name", ""),
                "can_delete": build_owner.can_delete(owner, current_user),
            })

    sorted_ingestions = sorted(ingestions, key=lambda x: x["created"])
    for i, item in enumerate(sorted_ingestions):
        item["build_label"] = f"Build {i + 1}"

    payload = {"ingestions": sorted(sorted_ingestions, key=lambda x: x["created"], reverse=True)}
    return _cache_set(_ingestions_cache, viewer_scope, payload)


def _purge_build_state(ingestion_id: str) -> None:
    """Drop every in-process trace of a build before its folder is removed.

    Deleting a build has to be complete, not just "the directory is gone".
    Everything that build produced â€” its chat history, saved charts, feedback,
    schema profile, summary and job status â€” lives in
    data/<build>/{lancedb,duckdb} and goes with the directory. What does NOT
    go with it, and is what this function handles:

      * The warm connection pool. DuckDB/LanceDB handles held open here keep
        file locks; on Windows rmtree then fails partway and leaves a
        half-deleted directory that still shows up in the build list. Closing
        first is what makes deletion reliable, not just tidy.
      * Four caches keyed by ingestion id (status, quality, suggestions,
        ingestions). Without clearing these, a deleted build keeps serving
        its old dashboard panels for the rest of the TTL.
      * The ingestion_jobs status cache, which would otherwise report the
        build as `completed` forever.
      * schema_context's per-ingestion summary cache, which is valid for the
        process lifetime by design (see schema_context.py) and so would
        otherwise keep answering chat/chart requests for this ingestion_id
        with a schema summary for data that no longer exists, for as long
        as the backend process stays up.

    Note on the drop-box: the file that produced this build stays marked as
    processed in auto_ingest_state.json. That is deliberate â€” clearing it
    while the source file is still sitting in the drop-box would have the
    watcher immediately re-ingest what you just deleted. Re-drop the file to
    import it again.
    """
    # Closing the pool's own connection is enough to release the file lock
    # for shutil.rmtree below - "active ingestion" is now per-request
    # (ContextVar-backed, see state.py), not a single process-wide pointer,
    # so there's no separate global "current" handle to close/reset here.
    # Any other request whose own context still points at this build's
    # (now-closed) connection object will get a clear "connection closed"
    # error on its next query - correct: better than silently continuing to
    # look like it's serving a build that no longer exists on disk.
    entry = state._ingestion_pool.pop(ingestion_id, None)
    if entry is not None:
        try:
            entry["duck_conn"].close()
        except Exception:
            logger.debug("Could not close pooled DuckDB connection for %s", ingestion_id, exc_info=True)

    for cache in (_status_cache, _quality_cache, _suggestions_cache, _insights_cache):
        cache.pop(ingestion_id, None)
    # Cleared wholesale, not by key: the list is cached per viewer scope
    # ("admin", "ws:platform", ...) and a deleted build has to disappear from
    # every one of them, not just the caller's.
    _ingestions_cache.clear()

    ingestion_jobs.forget(ingestion_id)
    schema_context.invalidate_cache(ingestion_id)


@app.delete("/ingestions/{ingestion_id}")
async def delete_ingestion(
    ingestion_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete an ingestion and all its associated data.

    This calls shutil.rmtree, so it is guarded twice. First the id is
    validated as a path segment before being joined onto DATA_BASE_PATH â€”
    previously `..%2F..%2Fsomething` was concatenated straight in. Second,
    authorization: any authenticated user could previously delete any build,
    including another team's.
    """
    # The authorization checks sit OUTSIDE the try block on purpose. They
    # raise HTTPException, and the `except Exception` below would otherwise
    # catch a 403 and turn it into a 200 carrying {"error": ...} â€” a refusal
    # the client would have no reason to treat as one.
    ingestion_path = build_owner.resolve_build_path(ingestion_id)
    if ingestion_path is None:
        raise HTTPException(status_code=400, detail="Invalid ingestion id")
    if not ingestion_path.exists():
        raise HTTPException(status_code=404, detail=f"Ingestion {ingestion_id} not found")

    owner = build_owner.read_owner(ingestion_path)
    if not build_owner.can_view(owner, current_user):
        # Same reasoning as the middleware: don't confirm it exists.
        raise HTTPException(status_code=404, detail=f"Ingestion {ingestion_id} not found")
    # Role gate first, ownership second: a viewer/developer role has no
    # data.delete permission at all regardless of who created the build, so
    # this can reject before even asking build_owner who's allowed to.
    if not permissions.has_permission(current_user, PERM_DATA_DELETE):
        raise HTTPException(status_code=403, detail="Your role does not have the 'data.delete' permission")
    if not build_owner.can_delete(owner, current_user):
        raise HTTPException(
            status_code=403,
            detail="Only an administrator or the user who created this build can delete it",
        )

    try:
        _purge_build_state(ingestion_id)
        shutil.rmtree(ingestion_path)
        logger.info(
            "User '%s' deleted ingestion %s (workspace=%s)",
            current_user.get("username"), ingestion_id, owner.get("workspace_id"),
        )
        audit_log.record(
            "build_delete", current_user.get("username"), target=ingestion_id,
            workspace_id=owner.get("workspace_id", ""),
        )
        return {"success": True, "message": f"Ingestion {ingestion_id} deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting ingestion {ingestion_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not delete ingestion: {e}") from e


@app.get("/suggestions")
async def role_suggestions(
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

    role_id = str(x_role or current_user.get("role") or "sdet").strip()
    project_id = str(x_project or "all").strip()

    suggestions_cache_key = f"{normalized_ingestion_id}:{role_id}:{project_id}"
    cached_suggestions = _cache_get(_suggestions_cache, suggestions_cache_key, _SUGGESTIONS_CACHE_TTL_SECONDS)
    if cached_suggestions is not None:
        return cached_suggestions

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
        return _cache_set(
            _suggestions_cache, suggestions_cache_key,
            {"role": role_id, "project": project_id, "source": "ai", **parsed_primary},
        )

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
        return _cache_set(
            _suggestions_cache, suggestions_cache_key,
            {"role": role_id, "project": project_id, "source": "ai-retry", **parsed_retry},
        )

    parsed_partial = _salvage_suggestions_payload(
        f"{raw_primary or ''}\n{raw_retry or ''}",
        role_id,
        schema_profile,
    )
    if parsed_partial:
        return _cache_set(
            _suggestions_cache, suggestions_cache_key,
            {"role": role_id, "project": project_id, "source": "ai-partial", **parsed_partial},
        )

    data = _normalize_suggestions({}, role_id, schema_profile)
    return _cache_set(
        _suggestions_cache, suggestions_cache_key,
        {"role": role_id, "project": project_id, "source": "fallback", **data},
    )


@app.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    x_ingestion_id: str = Header(...),
    x_session_id: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

    if state.lance_db is None:
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
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, normalized_ingestion_id)
    if _entry is not None:
        state.set_active_ingestion(normalized_ingestion_id, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])
    if state.duck_conn:
        try:
            with state._duck_query_lock:
                result = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()
            return {"count": result[0]}
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": "duck_conn not initialized"}


@app.get("/admin/usage")
async def admin_usage(_admin: dict = Depends(require_permission(permissions.PERM_USAGE_VIEW_ALL))):
    """Per-account lifetime spend and quota for the admin Usage tab.

    Joins token_usage_store's per-account totals with each account's
    configured limit from the user store - the two live in different tables
    (see token_usage_store.py's module docstring for why usage isn't a column
    on `users`), so an admin view of "who's spending what against what limit"
    has to bring them together at read time rather than at write time.
    """
    store = get_user_store()
    usage_by_user = {row["user_id"]: row for row in token_usage_store.list_usage_by_user()}
    limits_by_user = {u["username"]: u for u in store.list_users()}

    rows = []
    for username in sorted(set(usage_by_user) | set(limits_by_user)):
        usage = usage_by_user.get(username, {})
        account = limits_by_user.get(username, {})
        limit = int(account.get("token_limit") or 0)
        total = int(usage.get("total_tokens") or 0)
        rows.append({
            "username": username,
            "role": account.get("role", ""),
            "status": account.get("status", ""),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": total,
            "calls": int(usage.get("calls") or 0),
            "updated_at": usage.get("updated_at", ""),
            "token_limit": limit,
            "unlimited": limit <= 0,
            "remaining": max(0, limit - total) if limit > 0 else None,
            "over_limit": limit > 0 and total >= limit,
        })

    return {
        "users": rows,
        "totals": {
            "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "completion_tokens": sum(r["completion_tokens"] for r in rows),
            "total_tokens": sum(r["total_tokens"] for r in rows),
            "calls": sum(r["calls"] for r in rows),
        },
    }


@app.get("/admin/settings/llm")
async def admin_get_llm_settings(
    _admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    """Effective provider/model/key/base plus which fields env locks. The
    real api_key never leaves the process - only api_key_masked does."""
    return app_settings.get_llm_settings(include_secret=False)


@app.put("/admin/settings/llm")
async def admin_update_llm_settings(
    payload: AdminLLMSettingsRequest,
    admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    try:
        updated = app_settings.update_llm_settings(
            provider=payload.provider,
            model=payload.model,
            api_key=payload.api_key,
            api_base=payload.api_base,
            clear_api_key=payload.clear_api_key,
            updated_by=str(admin.get("username") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_log.record(
        "llm_settings_update", admin.get("username"),
        details={"provider": updated.get("provider"), "model": updated.get("model")},
    )
    return updated


@app.post("/admin/settings/llm/test")
async def admin_test_llm_settings(
    payload: AdminLLMTestRequest,
    _admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    """Fires one real, minimal completion against the given (or currently
    effective) config. Does not persist anything - see app_settings.py's
    test_llm_settings() docstring for why validate_llm_config() alone isn't
    enough to catch a wrong-but-well-formed key."""
    current = app_settings.get_llm_settings(include_secret=True)
    provider = (payload.provider or current["provider"]).strip().lower()
    model = (payload.model or current["model"]).strip()
    api_key = payload.api_key if payload.api_key is not None else current.get("api_key", "")
    api_base = payload.api_base if payload.api_base is not None else current.get("api_base", "")

    try:
        result = app_settings.test_llm_settings(
            provider=provider, model=model, api_key=api_key, api_base=api_base,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.get("/admin/settings/embedding")
async def admin_get_embedding_settings(
    _admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    """Effective embedding model (database > env > default) - the local
    sentence-transformers model used to embed ingested documents for
    semantic/vector search. Independent of the LLM provider/model above."""
    return app_settings.get_embedding_model_settings()


@app.put("/admin/settings/embedding")
async def admin_update_embedding_settings(
    payload: AdminEmbeddingSettingsRequest,
    admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    """Takes effect immediately for new ingestions and the next vector-search
    call - no restart needed (see data_loader._get_shared_embedder()). Note:
    builds already ingested under a DIFFERENT model keep their old
    embeddings: their vector search will degrade to 'no results' rather than
    error if the new model's dimensionality doesn't match (see
    data_loader.vector_search) - re-ingest a build to embed it under the new
    model."""
    try:
        updated = app_settings.update_embedding_model(
            model=payload.model,
            updated_by=str(admin.get("username") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_log.record(
        "embedding_settings_update", admin.get("username"),
        details={"model": updated.get("model")},
    )
    return updated


@app.get("/admin/settings/secret-key")
async def admin_get_secret_key(
    _admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    """Masked info only - the real signing secret never leaves the process."""
    return app_settings.get_secret_key_info()


@app.put("/admin/settings/secret-key")
async def admin_set_secret_key(
    payload: AdminSecretKeyRequest,
    admin: dict = Depends(require_permission(permissions.PERM_SETTINGS_MANAGE)),
):
    """Rotate the JWT signing secret. Requires `confirm: true` - this is not
    an ordinary settings save: it invalidates every currently-issued token,
    including the caller's own, the instant it's written. The frontend must
    show that consequence and get an explicit click before setting confirm.
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to proceed - changing this signs out every "
            "logged-in user immediately, including you.",
        )
    if not payload.generate and not (payload.value or "").strip():
        raise HTTPException(status_code=400, detail="Provide `value` or set `generate: true`")

    username = str(admin.get("username") or "")
    try:
        if payload.generate:
            app_settings.generate_secret_key(updated_by=username)
        else:
            app_settings.set_secret_key(payload.value, updated_by=username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_log.record("secret_key_rotate", username)
    return app_settings.get_secret_key_info()


@app.post("/admin/usage/{username}/reset")
async def admin_reset_usage(
    username: str,
    admin: dict = Depends(require_permission(permissions.PERM_USAGE_VIEW_ALL)),
):
    """Zero out an account's recorded spend (not its limit - see
    admin_update_user for changing token_limit). Used after raising someone's
    quota and wanting their counter to start clean, or to clear test/noise
    usage recorded before a limit was configured."""
    deleted = token_usage_store.reset_usage(username)
    logger.info("Admin '%s' reset token usage for '%s' (%d rows)", admin.get("username"), username, deleted)
    audit_log.record("usage_reset", admin.get("username"), target=username, details={"rows_cleared": deleted})
    return {"success": True, "rows_cleared": deleted}


@app.get("/admin/audit")
async def admin_audit_log(
    limit: int = Query(200, ge=1, le=1000),
    action: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    _admin: dict = Depends(require_permission(permissions.PERM_AUDIT_VIEW)),
):
    return {"events": audit_log.list_events(limit=limit, action=action, actor=actor)}


@app.get("/admin/notifications")
async def admin_notifications(admin: dict = Depends(require_admin)):
    """Live-computed feed for the admin bell icon: pending registrations
    waiting on approval, and recent ingestion failures. Not a persisted/
    read-tracked notification system (no "mark as read" state) - each item
    is just a current fact pulled from its own source of truth (user store,
    ingestion_jobs), the same pattern /admin/overview already uses. Spans
    Users + ingestion, both admin-only concerns, so gated by require_admin
    rather than one specific permission.
    """
    store = get_user_store()
    pending_users = store.list_users(status="pending")
    failed_jobs = ingestion_jobs.list_failed(limit=20)

    items = []
    for u in pending_users:
        items.append({
            "type": "pending_registration",
            "id": f"user:{u.get('username')}",
            "message": f"'{u.get('username')}' is awaiting approval to join {u.get('workspace_id') or 'default'}",
            "timestamp": u.get("created_at") or "",
            "link": "/admin/users",
        })
    for j in failed_jobs:
        items.append({
            "type": "ingestion_failed",
            "id": f"job:{j.get('build_id')}",
            "message": f"Ingestion '{j.get('build_id')}' failed: {j.get('error') or 'unknown error'}",
            "timestamp": j.get("finished_at") or "",
            "link": "/dashboard",
        })

    items.sort(key=lambda i: i["timestamp"], reverse=True)
    return {
        "count": len(items),
        "items": items,
    }


@app.get("/admin/overview")
async def admin_overview(_admin: dict = Depends(require_permission(permissions.PERM_USERS_MANAGE))):
    """One screen answering "what does this deployment look like right now" -
    population by status, workspaces, build counts, token spend, and whether
    the LLM is actually configured. Composes existing per-domain reads rather
    than introducing a new aggregate table, so it can never drift from
    the numbers each dedicated tab (Users/Usage/Settings) shows on its own.
    """
    store = get_user_store()
    status_counts = store.count_by_status()
    workspaces = store.list_workspaces()

    build_count = 0
    if config.DATA_BASE_PATH.exists():
        build_count = sum(
            1 for entry in config.DATA_BASE_PATH.iterdir()
            if entry.is_dir() and (entry / "lancedb").exists()
        )

    usage_rows = token_usage_store.list_usage_by_user()
    total_tokens = sum(int(r.get("total_tokens") or 0) for r in usage_rows)

    llm_settings = app_settings.get_llm_settings(include_secret=False)
    llm_ready = bool(llm_settings.get("model")) and (
        llm_settings.get("keyless") or llm_settings.get("api_key_set")
    )

    return {
        "users": {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
        },
        "workspaces": {"count": len(workspaces), "names": workspaces},
        "builds": {"count": build_count},
        "token_usage": {"lifetime_total": total_tokens, "accounts_with_usage": len(usage_rows)},
        "llm": {
            "ready": llm_ready,
            "provider": llm_settings.get("provider"),
            "model": llm_settings.get("model"),
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
