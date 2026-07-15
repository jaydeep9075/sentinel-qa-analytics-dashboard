"""
handlers.py — Chat and chart request handlers.

KEY FIX: Chart type is now deterministic (regex in detect_chart_type),
NOT decided by the LLM. The LLM only fills in column names for a
pre-written Plotly template — it cannot substitute a different chart type.
"""

import json
import re
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from . import config, data_loader, memory, llm_client, state
from .prompts import (
    CHAT_DECISION_PROMPT,
    CHAT_ANSWER_PROMPT,
    CHAT_VALIDATION_PROMPT,
    CHAT_RELEASE_VERDICT,
    CHART_SQL_PROMPT,
    CHART_CODE_PROMPT,
    FALLBACK_SQL_MAP,
    CHART_FALLBACK_SQL_MAP,
    detect_chart_type,
    get_chart_template,
)

logger = logging.getLogger(__name__)
_sql_cache: dict = {}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _apply_chart_layout(fig):
    PALETTE = ["#6C8BFF", "#22C55E", "#F59E0B", "#EF4444", "#A855F7", "#06B6D4", "#EC4899"]
    try:
        fig.update_xaxes(automargin=True, tickfont=dict(size=12, color="#CBD5E1"))
        fig.update_yaxes(automargin=True, tickfont=dict(size=12, color="#CBD5E1"))
        fig.update_traces(
            marker=dict(line=dict(width=1, color="rgba(15,23,42,0.4)")),
            selector=dict(type="bar"),
        )
    except Exception:
        pass
    fig.update_layout(
        template="plotly",
        autosize=True,
        paper_bgcolor="rgba(15,23,42,0)",
        plot_bgcolor="rgba(15,23,42,0)",
        font=dict(family="Inter, Segoe UI, Roboto, sans-serif", color="#E2E8F0", size=12),
        title=dict(font=dict(size=17, color="#F8FAFC"), x=0.5, xanchor="center", y=0.97),
        margin=dict(l=72, r=38, t=84, b=88),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            bgcolor="rgba(15,23,42,0.4)", bordercolor="rgba(148,163,184,0.3)",
            borderwidth=1, font=dict(color="#CBD5E1", size=11),
        ),
        xaxis=dict(
            showgrid=True, zeroline=False,
            gridcolor="rgba(148,163,184,0.15)", linecolor="rgba(148,163,184,0.3)",
            tickfont=dict(color="#CBD5E1", size=12), title_font=dict(color="#E2E8F0", size=13),
        ),
        yaxis=dict(
            showgrid=True, zeroline=False,
            gridcolor="rgba(148,163,184,0.15)", linecolor="rgba(148,163,184,0.3)",
            tickfont=dict(color="#CBD5E1", size=12), title_font=dict(color="#E2E8F0", size=13),
        ),
        hoverlabel=dict(bgcolor="rgba(15,23,42,0.95)", bordercolor="rgba(148,163,184,0.5)",
                        font=dict(size=12, color="#F8FAFC")),
        colorway=PALETTE,
    )
    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _convert_timestamp(obj):
    if isinstance(obj, dict):  return {k: _convert_timestamp(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_convert_timestamp(i) for i in obj]
    if isinstance(obj, (pd.Timestamp, datetime)): return obj.isoformat()
    return obj


def _sanitize_sql(sql: str) -> str:
    if not sql: return ""
    s = re.sub(r"```sql\s*|```", "", sql, flags=re.IGNORECASE).strip()
    s = re.sub(r"^\s*duckdb\s*:?", "", s, flags=re.IGNORECASE).strip()
    return s.rstrip(";").strip()


def _is_df_usable(df: pd.DataFrame) -> bool:
    return df is not None and not df.empty and not df.dropna(how="all").empty


def _fallback_sql(prompt: str, sql_map: dict) -> str:
    p = prompt.lower()
    for pattern, sql in sql_map.items():
        if re.search(pattern, p):
            return sql
    return ""


def _detect_structured_intent(prompt: str):
    p = (prompt or "").lower()
    if not p.strip():
        return None

    highest = any(k in p for k in ("highest", "best", "top", "max", "maximum"))
    lowest = any(k in p for k in ("lowest", "least", "worst", "bottom", "min", "minimum"))
    if not highest and not lowest:
        return None

    metric = None
    if any(k in p for k in ("pass rate", "passing rate", "success rate")):
        metric = "pass_rate"
    elif any(k in p for k in ("failed", "failure", "failures", "failed count")):
        metric = "failed"
    elif any(k in p for k in ("duration", "slow", "slowest", "fast", "fastest", "time")):
        metric = "duration"
    elif any(k in p for k in ("passed", "pass count")):
        metric = "passed"

    if not metric:
        return None

    if "project" in p:
        entity = "project"
    elif any(k in p for k in ("platform", "mobile", "desktop")):
        entity = "platform"
    else:
        entity = "module"

    direction = "both" if highest and lowest else ("highest" if highest else "lowest")
    return {"metric": metric, "entity": entity, "direction": direction}


def _build_structured_sql(intent: dict) -> str:
    metric = intent.get("metric")
    entity = intent.get("entity")
    direction = intent.get("direction")

    if entity == "project":
        base = (
            "SELECT project_name, platform_type, total_tests, passed, failed,"
            " ROUND(pass_rate, 2) AS pass_rate, ROUND(total_duration_seconds, 2) AS total_duration_seconds,"
            " ROUND(avg_duration_seconds, 2) AS avg_duration_seconds"
            " FROM project_metrics"
        )
    elif entity == "platform":
        base = (
            "SELECT platform_type,"
            " COUNT(*) AS total_tests,"
            " SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS passed,"
            " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,"
            " ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS pass_rate,"
            " ROUND(SUM(COALESCE(duration, 0)), 2) AS total_duration_seconds,"
            " ROUND(AVG(NULLIF(duration, 0)), 2) AS avg_duration_seconds"
            " FROM flattened_tests"
            " GROUP BY platform_type"
        )
    else:
        base = (
            "SELECT project_name, module_name, platform_type, total_tests, passed, failed,"
            " ROUND(pass_rate, 2) AS pass_rate, ROUND(total_duration_seconds, 2) AS total_duration_seconds,"
            " ROUND(avg_duration_seconds, 2) AS avg_duration_seconds"
            " FROM module_metrics"
        )

    metric_col = {
        "pass_rate": "pass_rate",
        "failed": "failed",
        "passed": "passed",
        "duration": "avg_duration_seconds",
    }.get(metric, "pass_rate")

    if direction == "both":
        return (
            "WITH base AS ("
            f"{base}"
            ") "
            "SELECT * FROM ("
            "SELECT 'highest' AS rank_type, * FROM base ORDER BY " + metric_col + " DESC NULLS LAST LIMIT 1"
            ") h "
            "UNION ALL "
            "SELECT * FROM ("
            "SELECT 'lowest' AS rank_type, * FROM base ORDER BY " + metric_col + " ASC NULLS LAST LIMIT 1"
            ") l"
        )

    order = "DESC" if direction == "highest" else "ASC"
    return (
        "WITH base AS ("
        f"{base}"
        ") "
        "SELECT * FROM base ORDER BY " + metric_col + f" {order} NULLS LAST LIMIT 1"
    )


def _looks_like_data_question(prompt: str) -> bool:
    p = (prompt or "").lower()
    if not p.strip():
        return False
    keywords = (
        "pass rate", "failed", "passed", "tests", "test count", "count", "how many",
        "module", "project", "platform", "mobile", "desktop", "release", "ship", "deploy",
        "duration", "slow", "trend", "status", "breakdown", "distribution", "build",
        "highest", "lowest", "top", "bottom", "least", "best", "worst",
    )
    return any(k in p for k in keywords)


def _prepare_df_for_prompt(df: pd.DataFrame) -> pd.DataFrame:
    df_safe = df.copy()
    for col in df_safe.select_dtypes(include=["datetime64", "datetimetz"]).columns:
        df_safe[col] = df_safe[col].astype(str)
    return df_safe.where(pd.notna(df_safe), other="")


def _fallback_tabular_response(df: pd.DataFrame) -> str:
    if len(df) == 1 and len(df.columns) == 1:
        return f"📊 **Result:** {df.iloc[0, 0]}"
    if len(df.columns) <= 3:
        rows_fmt = "\n".join(
            f"{i+1}. " + " | ".join(str(v) for v in r)
            for i, r in enumerate(df.head(25).itertuples(index=False))
        )
        return f"**Results ({len(df)} rows):**\n{rows_fmt}"
    return f"Found **{len(df)} rows**. Use the chart feature to visualize."


def _validate_grounded_response(
    llm,
    user_message: str,
    draft_answer: str,
    df_safe: pd.DataFrame,
    user_id: str = "anonymous",
    workspace_id: str = "default",
) -> str:
    raw = llm.generate(
        CHAT_VALIDATION_PROMPT.format(
            user_message=user_message,
            draft_answer=draft_answer or "",
            row_count=len(df_safe),
            data_json=df_safe.head(50).to_json(orient="records", force_ascii=False),
        ),
        temperature=0.0,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    if not raw:
        return draft_answer

    cleaned = re.sub(r"```json\s*|```", "", raw, flags=re.IGNORECASE).strip()
    m = re.search(r"\{[\s\S]*\}", cleaned)
    candidate = m.group(0) if m else cleaned

    try:
        payload = json.loads(candidate)
    except Exception:
        return draft_answer

    if payload.get("is_valid") is True:
        return draft_answer
    corrected = str(payload.get("corrected_answer", "")).strip()
    return corrected or draft_answer


def _format_structured_response(intent: dict, df: pd.DataFrame) -> str:
    metric = intent.get("metric")
    entity = intent.get("entity")

    metric_label = {
        "pass_rate": "pass rate",
        "failed": "failed tests",
        "passed": "passed tests",
        "duration": "average duration (sec)",
    }.get(metric, "metric")
    value_col = {
        "pass_rate": "pass_rate",
        "failed": "failed",
        "passed": "passed",
        "duration": "avg_duration_seconds",
    }.get(metric, "pass_rate")

    def _entity_name(row: pd.Series) -> str:
        if entity == "project":
            return f"project '{row.get('project_name', 'unknown')}' ({row.get('platform_type', 'all')})"
        if entity == "platform":
            return f"platform '{row.get('platform_type', 'unknown')}'"
        return (
            f"module '{row.get('module_name', 'unknown')}' in project "
            f"'{row.get('project_name', 'unknown')}' ({row.get('platform_type', 'all')})"
        )

    if "rank_type" in df.columns and len(df) >= 2:
        lines = ["📊 **Validated comparison result**"]
        for _, row in df.iterrows():
            direction = str(row.get("rank_type", "")).strip().lower() or "result"
            value = row.get(value_col, "N/A")
            lines.append(f"- **{direction.title()} {metric_label}:** {value} on {_entity_name(row)}")
        lines.append(f"Validation source: computed directly from {'project_metrics' if entity == 'project' else 'flattened_tests' if entity == 'platform' else 'module_metrics'}.")
        return "\n".join(lines)

    row = df.iloc[0]
    value = row.get(value_col, "N/A")
    return (
        "📊 **Validated result**\n"
        f"- **{metric_label.title()}:** {value}\n"
        f"- **Entity:** {_entity_name(row)}\n"
        f"- Validation source: computed directly from {'project_metrics' if entity == 'project' else 'flattened_tests' if entity == 'platform' else 'module_metrics'}."
    )


def _build_history(session_id: str, user_id: str, ingestion_id: str, limit: int = 20) -> str:
    history = memory.get_chat_history(
        session_id,
        limit=limit,
        user_id=user_id,
        ingestion_id=ingestion_id,
    )
    if not history:
        return "(no prior conversation)"
    lines = []
    for h in reversed(history):
        role = h.get("type", "")
        lines.append(f"{'User' if role == 'user' else 'Assistant'}: "
                     f"{h.get('prompt', '') if role == 'user' else h.get('response', '')}")
    return "\n".join(lines[-20:])


def _sanitize_code(code: str) -> str:
    s = re.sub(r"```python\s*|```", "", code or "", flags=re.IGNORECASE).strip()
    for bad in ("'Blues_d'", '"Blues_d"', "'Blues_r'", '"Blues_r"'):
        s = s.replace(bad, "'Blues'")
    for kw in ("piecolorway", "hovertemplate", "customdata"):
        s = re.sub(rf",?\s*{kw}\s*=\s*[^,)\n]+", "", s)
    s = re.sub(r",?\s*width\s*=\s*\d+\s*,?", "", s)
    s = re.sub(r",?\s*height\s*=\s*\d+\s*,?", "", s)
    s = re.sub(r",?\s*template\s*=\s*['\"][^'\"]+['\"]\s*,?", "", s)
    return s


def _make_title(prompt: str) -> str:
    t = prompt.strip().rstrip("?").strip()
    return (t[:52] + "…") if len(t) > 55 else t


def _build_schema_context(max_tables: int = 8, max_columns: int = 25) -> str:
    profile = data_loader.get_data_profile(sample_rows=2)
    tables = profile.get("tables", {}) if isinstance(profile, dict) else {}
    if not tables:
        return ""

    lines = ["[RUNTIME TABLE PROFILE]"]
    for i, (tbl, info) in enumerate(tables.items()):
        if i >= max_tables:
            break
        if not isinstance(info, dict):
            continue
        row_count = info.get("row_count", "?")
        cols = info.get("columns", [])
        col_names = ", ".join(c.get("name", "") for c in cols[:max_columns] if isinstance(c, dict))
        lines.append(f"- {tbl} ({row_count} rows): {col_names}")
    return "\n".join(lines)


def _is_chart_df_valid_for_type(df: pd.DataFrame, chart_type: str) -> bool:
    if not _is_df_usable(df):
        return False
    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category", "string"]).columns.tolist()

    if chart_type in ("pie", "donut"):
        return len(num_cols) >= 1 and len(cat_cols) >= 1
    if chart_type in ("bar", "horizontal_bar", "line", "scatter"):
        return len(num_cols) >= 1
    if chart_type == "heatmap":
        return len(num_cols) >= 1 and len(cat_cols) >= 2
    if chart_type == "platform_comparison":
        return "platform_type" in df.columns and len(num_cols) >= 1
    return len(num_cols) >= 1


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

async def handle_chat(user_message: str, session_id: str, ingestion_id: str,
                      role: str = None, project_id: str = None,
                      user_id: str = "anonymous", workspace_id: str = "default"):
    nid = str(ingestion_id or "").strip()
    if state.current_ingestion_id != nid or not state.duck_conn or not state.lance_db:
        if not data_loader.init_data(nid):
            return f"❌ Ingestion '{ingestion_id}' not found or data unavailable."

    # Layer 1: deterministic intent handler for critical analytical prompts.
    structured_intent = _detect_structured_intent(user_message)
    if structured_intent:
        sql = _build_structured_sql(structured_intent)
        df, err = data_loader.execute_sql(sql)
        if not err and _is_df_usable(df):
            response = _format_structured_response(structured_intent, df)
            memory.store_chat_message(
                session_id, "user", user_message,
                user_id=user_id, ingestion_id=nid, workspace_id=workspace_id,
            )
            memory.store_chat_message(
                session_id, "assistant", response,
                user_id=user_id, ingestion_id=nid, workspace_id=workspace_id,
            )
            memory.learn_from_interaction(
                user_id, nid, session_id, workspace_id, user_message, response, kind="chat"
            )
            return response

    llm = llm_client.LLMClient()

    learning_context = memory.get_learning_context(user_id, nid, workspace_id, user_message, limit=6)
    related_concepts = memory.get_related_concepts(user_id, nid, workspace_id, user_message, limit=8)
    feedback_hints = memory.get_feedback_prompt_hints(
        user_id,
        nid,
        workspace_id,
        target_kind="chat",
        current_prompt=user_message,
    )

    augmented_message = user_message
    if learning_context:
        snippets = []
        for item in learning_context[:4]:
            p = str(item.get("prompt", "")).strip()
            r = str(item.get("response", "")).strip()
            snippets.append(f"Q: {p}\nA: {r[:300]}")
        augmented_message += "\n\n[LEARNED USER CONTEXT]\n" + "\n\n".join(snippets)
    if related_concepts:
        concepts = ", ".join([c["concept"] for c in related_concepts])
        augmented_message += f"\n\n[RELATED CONCEPTS]\n{concepts}"
    if feedback_hints:
        augmented_message += f"\n\n[USER FEEDBACK PREFERENCES]\n{feedback_hints}"
    schema_context = _build_schema_context()
    if schema_context:
        augmented_message += f"\n\n{schema_context}"

    raw = llm.generate(
        CHAT_DECISION_PROMPT.format(
            history=_build_history(session_id, user_id, nid),
            user_message=augmented_message,
        ),
        temperature=0.05,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    if not raw:
        return "⚠️ AI service unavailable. Please try again."

    cleaned = re.sub(r"```json\s*|```", "", raw, flags=re.IGNORECASE).strip()
    m = re.search(r'\{[^{}]+\}', cleaned, re.DOTALL)
    try:
        decision = json.loads(m.group() if m else cleaned)
    except Exception:
        if "SELECT" in raw.upper():
            sm = re.search(r'SELECT.+', raw, re.IGNORECASE | re.DOTALL)
            decision = {"action": "sql", "data": sm.group() if sm else ""}
        else:
            decision = {"action": "answer", "data": raw.strip()}

    action = decision.get("action", "answer")
    data   = decision.get("data", "")
    if isinstance(data, str) and "SELECT" in data.upper():
        action = "sql"
    elif action != "sql" and _looks_like_data_question(user_message):
        action = "sql"
        data = _fallback_sql(user_message, FALLBACK_SQL_MAP)

    if action == "sql":
        sql = _sanitize_sql(data) if data else ""
        df, err = data_loader.execute_sql(sql) if sql else (pd.DataFrame(), "empty")
        if err or not _is_df_usable(df):
            fb = _fallback_sql(user_message, FALLBACK_SQL_MAP)
            if fb and fb != sql:
                df, err = data_loader.execute_sql(fb)
                sql = fb

        if err:
            response = f"⚠️ Could not retrieve that data. Details: {err}"
        elif not _is_df_usable(df):
            response = "📭 No data found for your query."
        else:
            is_release = any(kw in user_message.lower()
                             for kw in ("release", "good to go", "ready for", "ship", "deploy"))
            if is_release and "pass_rate" in df.columns:
                pr = float(df.iloc[0].get("pass_rate", 0))
                total = int(df.iloc[0].get("total", 0))
                failed = int(df.iloc[0].get("failed_count", 0))
                passed = total - failed
                if pr >= 95:   verdict, rec = "✅ GOOD FOR RELEASE", "Quality meets criteria. Proceed."
                elif pr >= 80: verdict, rec = "⚠️ CONSIDER WITH CAUTION", f"Pass rate {pr}% below target. Review failures."
                else:          verdict, rec = "❌ NOT READY FOR RELEASE", f"Pass rate {pr}% critically low. Fix failures first."
                response = CHAT_RELEASE_VERDICT.format(
                    pass_rate=pr, passed=passed, total=total,
                    failed_count=failed, verdict=verdict, recommendation=rec,
                )
            else:
                df_safe = _prepare_df_for_prompt(df)
                answer_prompt = CHAT_ANSWER_PROMPT.format(
                    user_message=augmented_message,
                    row_count=len(df),
                    data_json=df_safe.head(50).to_json(orient="records", force_ascii=False),
                )
                response = llm.generate(answer_prompt, temperature=0.15)
                response = response or _fallback_tabular_response(df)
                response = _validate_grounded_response(
                    llm,
                    user_message,
                    response,
                    df_safe,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )

    elif action == "vector":
        docs = data_loader.vector_search(data, top_k=5)
        ctx = "\n\n".join(d["text"][:400] for d in docs) if docs else ""
        response = (
            llm.generate(
                f"Context:\n{ctx}\n\nQuestion: {user_message}\n\nAnswer concisely:",
                temperature=0.2,
                user_id=user_id,
                workspace_id=workspace_id,
            )
            or "No relevant info found."
        ) if ctx else "No relevant information found."

    else:
        response = str(data) if data else "I'm not sure how to answer that. Try rephrasing."

    memory.store_chat_message(
        session_id, "user", user_message,
        user_id=user_id, ingestion_id=nid, workspace_id=workspace_id,
    )
    memory.store_chat_message(
        session_id, "assistant", response,
        user_id=user_id, ingestion_id=nid, workspace_id=workspace_id,
    )
    memory.learn_from_interaction(
        user_id, nid, session_id, workspace_id, user_message, response, kind="chat"
    )
    return response


# ---------------------------------------------------------------------------
# Chart handler
# ---------------------------------------------------------------------------

async def handle_chart(user_prompt: str, session_id: str, ingestion_id: str,
                       role: str = None, project_id: str = None,
                       user_id: str = "anonymous", workspace_id: str = "default"):
    nid = str(ingestion_id or "").strip()
    if state.current_ingestion_id != nid or not state.duck_conn or not state.lance_db:
        if not data_loader.init_data(nid):
            return None, f"❌ Ingestion '{ingestion_id}' not found."

    llm = llm_client.LLMClient()
    feedback_hints = memory.get_feedback_prompt_hints(
        user_id,
        nid,
        workspace_id,
        target_kind="chart",
        current_prompt=user_prompt,
    )
    prompt_for_llm = user_prompt
    if feedback_hints:
        prompt_for_llm += f"\n\n[USER FEEDBACK PREFERENCES]\n{feedback_hints}"
    schema_context = _build_schema_context()
    if schema_context:
        prompt_for_llm += f"\n\n{schema_context}"

    # STEP 1: Deterministic chart type (no LLM involved)
    chart_type = detect_chart_type(user_prompt)
    logger.info(f"Chart type='{chart_type}' for: '{user_prompt[:60]}'")

    # STEP 2: SQL
    structured_intent = _detect_structured_intent(user_prompt)
    cache_key = user_prompt.lower().strip()
    sql = _sql_cache.get(cache_key)
    if structured_intent:
        sql = _build_structured_sql(structured_intent)
    if not sql:
        raw_sql = llm.generate(
            CHART_SQL_PROMPT.format(user_prompt=prompt_for_llm, chart_type=chart_type),
            temperature=0.05,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        sql = _sanitize_sql(raw_sql or "")

    if not sql or sql.upper() == "N/A":
        sql = _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP)
        if not sql:
            return None, "Could not determine what data to chart."

    # STEP 3: Execute with retries
    df, err = data_loader.execute_sql(sql)
    for attempt in range(2):
        if err or not _is_df_usable(df):
            fb = _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP)
            if fb and fb != sql:
                df, err = data_loader.execute_sql(fb)
                sql = fb
                if not err and _is_df_usable(df):
                    break
            else:
                fixed_sql = llm.generate(
                    f"Fix this DuckDB SQL. Error: {err or 'empty'}\nSQL: {sql}\n"
                    f"Request: {user_prompt}\nReturn ONLY corrected SQL:",
                    temperature=0.1,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                if fixed_sql:
                    sql = _sanitize_sql(fixed_sql)
                    df, err = data_loader.execute_sql(sql)
                break

    if err:
        return None, f"SQL error: {err}"
    if not _is_df_usable(df):
        return None, "No data returned for this chart."

    # Validate chart fitness; retry once with deterministic fallback SQL if shape is incompatible.
    if not _is_chart_df_valid_for_type(df, chart_type):
        fb = _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP)
        if fb and fb != sql:
            df_fb, err_fb = data_loader.execute_sql(fb)
            if not err_fb and _is_chart_df_valid_for_type(df_fb, chart_type):
                df = df_fb
                sql = fb

    _sql_cache[cache_key] = sql
    if len(_sql_cache) > 100:
        for k in list(_sql_cache.keys())[:20]:
            del _sql_cache[k]

    return _generate_chart(
        df,
        user_prompt,
        prompt_for_llm,
        session_id,
        sql,
        chart_type,
        llm,
        user_id,
        nid,
        workspace_id,
    )


def _generate_chart(df, user_prompt, prompt_for_llm, session_id, sql, chart_type, llm, user_id, ingestion_id, workspace_id):
    if not _is_df_usable(df):
        return None, "No data available."
    df = df.dropna(how="all")
    if df.empty:
        return None, "Data is empty after cleaning."

    data_sample = _convert_timestamp(df.head(50).to_dict(orient="records"))
    data_sample = [
        {k: ("" if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()}
        for row in data_sample
    ]

    title    = _make_title(user_prompt)
    template = get_chart_template(chart_type, title)

    code = llm.generate(
        CHART_CODE_PROMPT.format(
            user_prompt=prompt_for_llm,
            chart_type=chart_type,
            data_sample=json.dumps(data_sample, indent=2, ensure_ascii=False),
            columns=list(df.columns),
            chart_template=template,
        ),
        temperature=0.1,
        user_id=user_id,
        workspace_id=workspace_id,
    )

    if not code:
        return None, "Chart code generation failed."

    code = _sanitize_code(code)

    try:
        import plotly.express as px
        import plotly.graph_objects as go
        ns = {"px": px, "go": go, "pd": pd, "np": np, "data": data_sample}
        exec(code, ns)  # noqa: S102
        fig = ns.get("fig")
        if fig is None:
            raise ValueError("No 'fig' variable produced.")
        fig = _apply_chart_layout(fig)
        if not getattr(getattr(fig, "layout", None), "title", None) or \
           not getattr(fig.layout.title, "text", None):
            fig.update_layout(title=dict(text=title))
        chart_json = fig.to_json()
        memory.store_chart(
            session_id,
            user_prompt,
            chart_json,
            {"sql": sql, "chart_type": chart_type},
            user_id=user_id,
            ingestion_id=ingestion_id,
            workspace_id=workspace_id,
        )
        memory.learn_from_interaction(
            user_id, ingestion_id, session_id, workspace_id, user_prompt, chart_json, kind="chart"
        )
        return chart_json, None
    except Exception as exc:
        logger.error(f"Chart exec error ({chart_type}): {exc}")
        try:
            return _safe_fallback_chart(
                df, title, chart_type, user_prompt, session_id, sql, user_id, ingestion_id, workspace_id
            )
        except Exception as fb:
            logger.error(f"Fallback chart failed: {fb}")
        return None, f"Chart generation failed: {exc}"


def _safe_fallback_chart(df, title, chart_type, user_prompt, session_id, sql, user_id, ingestion_id, workspace_id):
    """100% deterministic fallback — no LLM."""
    import plotly.express as px
    import plotly.graph_objects as go

    COLORS = ["#6C8BFF", "#22C55E", "#F59E0B", "#EF4444", "#A855F7", "#06B6D4"]
    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    if not num_cols:
        return None, "No numeric data for chart."

    x_col = cat_cols[0] if cat_cols else df.columns[0]
    y_col = num_cols[0]
    color_col = ("platform_type" if "platform_type" in df.columns
                 else "project_name" if "project_name" in df.columns else None)

    if chart_type in ("pie", "donut"):
        fig = px.pie(df, names=x_col, values=y_col, title=title,
                     hole=0.4 if chart_type == "donut" else 0,
                     color_discrete_sequence=["#22C55E","#EF4444","#F59E0B","#A855F7","#06B6D4","#6C8BFF"])
        fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=13)

    elif chart_type == "horizontal_bar":
        df_s = df.sort_values(y_col, ascending=True)
        fig = px.bar(df_s, x=y_col, y=x_col, orientation="h", title=title,
                     color=color_col, color_discrete_sequence=COLORS)
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_yaxes(automargin=True)

    elif chart_type == "line":
        fig = px.line(df, x=x_col, y=y_col, title=title, color=color_col,
                      markers=True, color_discrete_sequence=COLORS)
        fig.update_traces(line_width=2.5, marker_size=8)

    elif chart_type == "heatmap" and len(cat_cols) >= 2:
        pivot = df.pivot_table(index=cat_cols[0], columns=cat_cols[1],
                               values=num_cols[0], fill_value=0, aggfunc="sum")
        fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns.tolist(),
                                   y=pivot.index.tolist(), colorscale="Reds",
                                   text=pivot.values.astype(int).astype(str), texttemplate="%{text}"))
        fig.update_layout(title=title)

    elif chart_type == "scatter" and len(num_cols) >= 2:
        fig = px.scatter(df, x=num_cols[0], y=num_cols[1], title=title,
                         color=color_col or (cat_cols[0] if cat_cols else None),
                         color_discrete_sequence=COLORS)
        fig.update_traces(marker_size=10, marker_opacity=0.8)

    elif chart_type == "platform_comparison" and "platform_type" in df.columns:
        fig = px.bar(df, x="platform_type", y=y_col, title=title, color="platform_type",
                     barmode="group", text_auto=True,
                     color_discrete_map={"mobile": "#EF4444", "desktop": "#22C55E"})
        fig.update_traces(textfont_size=13, textposition="outside")

    else:
        fig = px.bar(df, x=x_col, y=y_col, title=title, color=color_col,
                     barmode="group", color_discrete_sequence=COLORS)
        fig.update_traces(textfont_size=11, textangle=0, textposition="outside", cliponaxis=False)
        fig.update_xaxes(tickangle=-35)

    fig = _apply_chart_layout(fig)
    chart_json = fig.to_json()
    memory.store_chart(
        session_id,
        user_prompt,
        chart_json,
        {"sql": sql, "fallback": True},
        user_id=user_id,
        ingestion_id=ingestion_id,
        workspace_id=workspace_id,
    )
    memory.learn_from_interaction(
        user_id, ingestion_id, session_id, workspace_id, user_prompt, chart_json, kind="chart"
    )
    return chart_json, None