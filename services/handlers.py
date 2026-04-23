"""
handlers.py — Chat and chart request handlers.
- Uses centralized prompts from prompts.py
- No role-based logic in prompts
- Robust SQL validation and Plotly sanitization
- Persistent chat history context (last 20 turns)
"""

import json
import re
import logging
from datetime import datetime
import pandas as pd
import numpy as np
from . import config, data_loader, memory, llm_client, state
from .prompts import (
    CHAT_DECISION_PROMPT,
    CHAT_ANSWER_PROMPT,
    CHAT_RELEASE_VERDICT,
    CHART_SQL_PROMPT,
    CHART_CODE_PROMPT,
    FALLBACK_SQL_MAP,
    CHART_FALLBACK_SQL_MAP,
)

logger = logging.getLogger(__name__)

_sql_cache: dict = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _convert_timestamp(obj):
    if isinstance(obj, dict):
        return {k: _convert_timestamp(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_timestamp(i) for i in obj]
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _sanitize_sql(sql: str) -> str:
    if not sql:
        return ""
    s = re.sub(r"```sql\s*|```", "", sql, flags=re.IGNORECASE).strip()
    s = re.sub(r"^\s*duckdb\s*:?", "", s, flags=re.IGNORECASE).strip()
    return s.rstrip(";").strip()


def _is_df_usable(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    return not df.dropna(how="all").empty


def _fallback_sql(prompt: str, sql_map: dict) -> str:
    p = prompt.lower()
    for pattern, sql in sql_map.items():
        if re.search(pattern, p):
            return sql
    return ""


def _build_history_context(session_id: str, limit: int = 20) -> str:
    history = memory.get_chat_history(session_id, limit=limit)
    if not history:
        return "(no prior conversation)"
    lines = []
    for h in reversed(history):
        role = h.get("type", "")
        if role == "user":
            lines.append(f"User: {h.get('prompt', '')}")
        else:
            lines.append(f"Assistant: {h.get('response', '')}")
    return "\n".join(lines[-20:])  # last 20 exchanges


def _sanitize_plotly_code(code: str) -> str:
    s = re.sub(r"```python\s*|```", "", code or "", flags=re.IGNORECASE).strip()
    # Remove forbidden palette strings
    for bad in ("'Blues_d'", '"Blues_d"', "'Blues_r'", '"Blues_r"'):
        s = s.replace(bad, "'Blues'")
    # Strip forbidden kwargs
    for kw in ("piecolorway", "hovertemplate", "customdata"):
        s = re.sub(rf",?\s*{kw}\s*=\s*[^,)\n]+", "", s)
    # Strip explicit size (we control via update_layout)
    s = re.sub(r",?\s*width\s*=\s*\d+\s*,?", "", s)
    s = re.sub(r",?\s*height\s*=\s*\d+\s*,?", "", s)
    # Ensure template is always plotly_dark
    if "plotly_dark" not in s:
        s += "\nfig.update_layout(template='plotly_dark')"
    return s


def _detect_chart_type(prompt: str) -> str:
    p = prompt.lower()
    if any(k in p for k in ("line", "trend", "over time", "timeline")):
        return "line"
    if any(k in p for k in ("pie", "distribution", "percentage", "share")):
        return "pie"
    if any(k in p for k in ("heatmap", "matrix", "heat map")):
        return "heatmap"
    if any(k in p for k in ("horizontal", "slowest", "longest")):
        return "horizontal_bar"
    if any(k in p for k in ("bar", "count", "top", "most")):
        return "bar"
    return "bar"


def _apply_chart_layout(fig):
    """Apply consistent dark theme layout overrides."""
    fig.update_layout(
        template="plotly_dark",
        autosize=True,
        paper_bgcolor="rgba(15,15,15,0)",
        plot_bgcolor="rgba(15,15,15,0)",
        font=dict(family="monospace", color="#e2e8f0", size=12),
        title=dict(font=dict(size=15, color="#f1f5f9"), x=0.5, xanchor="center"),
        margin=dict(l=60, r=40, t=70, b=80),
        legend=dict(
            bgcolor="rgba(255,255,255,0.05)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
            font=dict(color="#cbd5e1"),
        ),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            linecolor="rgba(255,255,255,0.12)",
            tickfont=dict(color="#94a3b8", size=11),
            title_font=dict(color="#cbd5e1"),
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            linecolor="rgba(255,255,255,0.12)",
            tickfont=dict(color="#94a3b8", size=11),
            title_font=dict(color="#cbd5e1"),
        ),
        colorway=["#60a5fa", "#34d399", "#f59e0b", "#f87171", "#a78bfa", "#38bdf8"],
    )
    return fig


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

async def handle_chat(
    user_message: str,
    session_id: str,
    ingestion_id: str,
    role: str = None,
    project_id: str = None,
):
    # Load data if needed
    if state.current_ingestion_id != ingestion_id:
        if not data_loader.init_data(ingestion_id):
            return f"❌ Ingestion '{ingestion_id}' not found or data unavailable."

    llm = llm_client.LLMClient()

    # Build conversation history context (last 20 turns)
    history_context = _build_history_context(session_id, limit=20)

    # --- Decision phase ---
    decision_prompt = CHAT_DECISION_PROMPT.format(
        history=history_context,
        user_message=user_message,
    )

    raw_decision = llm.generate(decision_prompt, temperature=0.05)
    if not raw_decision:
        return "⚠️ AI service unavailable. Please try again."

    # Parse decision JSON
    cleaned = re.sub(r"```json\s*|```", "", raw_decision, flags=re.IGNORECASE).strip()
    # Extract just the JSON object if extra text surrounds it
    json_match = re.search(r'\{[^{}]+\}', cleaned, re.DOTALL)
    try:
        decision = json.loads(json_match.group() if json_match else cleaned)
    except Exception:
        # If there's a SELECT in the output, treat as SQL
        if "SELECT" in raw_decision.upper():
            sql_match = re.search(r'SELECT.+', raw_decision, re.IGNORECASE | re.DOTALL)
            decision = {"action": "sql", "data": sql_match.group() if sql_match else ""}
        else:
            decision = {"action": "answer", "data": raw_decision.strip()}

    action = decision.get("action", "answer")
    data = decision.get("data", "")

    # Force sql action if SELECT is in data
    if isinstance(data, str) and "SELECT" in data.upper():
        action = "sql"

    # --- SQL execution ---
    if action == "sql":
        sql = _sanitize_sql(data) if data else ""

        # Try LLM SQL first, then fallback
        df, err = data_loader.execute_sql(sql) if sql else (pd.DataFrame(), "empty")
        if err or not _is_df_usable(df):
            fallback = _fallback_sql(user_message, FALLBACK_SQL_MAP)
            if fallback and fallback != sql:
                logger.info(f"Chat: using fallback SQL for '{user_message}'")
                df, err = data_loader.execute_sql(fallback)
                sql = fallback

        if err:
            response = f"⚠️ I couldn't retrieve that data. Details: {err}"
        elif not _is_df_usable(df):
            response = "📭 No data found for your query."
        else:
            # Release readiness special handling
            is_release = any(
                kw in user_message.lower()
                for kw in ("release", "good to go", "ready for", "ship", "deploy")
            )
            if is_release and "pass_rate" in df.columns:
                row = df.iloc[0]
                pr = float(row.get("pass_rate", 0))
                total = int(row.get("total", 0))
                passed = int(row.get("passed", total * pr / 100)) if "passed" not in row else int(row.get("passed", 0))
                failed = int(row.get("failed_count", 0))
                if pr >= 95:
                    verdict = "✅ GOOD FOR RELEASE"
                    rec = "Quality meets release criteria. Proceed with deployment."
                elif pr >= 80:
                    verdict = "⚠️ CONSIDER WITH CAUTION"
                    rec = f"Pass rate {pr}% is below target. Review and fix failures before releasing."
                else:
                    verdict = "❌ NOT READY FOR RELEASE"
                    rec = f"Pass rate {pr}% is critically low. Fix failures before releasing."
                response = CHAT_RELEASE_VERDICT.format(
                    pass_rate=pr,
                    passed=passed,
                    total=total,
                    failed_count=failed,
                    verdict=verdict,
                    recommendation=rec,
                )
            else:
                # Serialize for LLM
                df_safe = df.copy()
                for col in df_safe.select_dtypes(include=["datetime64"]).columns:
                    df_safe[col] = df_safe[col].astype(str)
                # Replace NaN/None
                df_safe = df_safe.where(pd.notna(df_safe), other="")
                data_json = df_safe.head(50).to_json(orient="records", force_ascii=False)

                answer_prompt = CHAT_ANSWER_PROMPT.format(
                    user_message=user_message,
                    row_count=len(df),
                    data_json=data_json,
                )
                response = llm.generate(answer_prompt, temperature=0.15)
                if not response:
                    # Minimal fallback formatting
                    if len(df) == 1 and len(df.columns) == 1:
                        response = f"📊 **Result:** {df.iloc[0, 0]}"
                    elif len(df.columns) <= 2:
                        rows_fmt = "\n".join(
                            f"{i+1}. " + " | ".join(str(v) for v in row)
                            for i, row in enumerate(df.head(20).itertuples(index=False))
                        )
                        response = f"**Results ({len(df)} rows):**\n{rows_fmt}"
                    else:
                        response = f"Found **{len(df)} rows**. Use the chart feature to visualize."

    elif action == "vector":
        docs = data_loader.vector_search(data, top_k=5)
        if not docs:
            response = "No relevant information found."
        else:
            ctx = "\n\n".join(d["text"][:400] for d in docs)
            answer_prompt = f"Context:\n{ctx}\n\nQuestion: {user_message}\n\nAnswer concisely:"
            response = llm.generate(answer_prompt, temperature=0.2) or "Could not generate a response."

    else:
        # Pure answer
        response = str(data) if data else "I'm not sure how to answer that. Try rephrasing."

    # Persist both turns
    memory.store_chat_message(session_id, "user", user_message)
    memory.store_chat_message(session_id, "assistant", response)
    return response


# ---------------------------------------------------------------------------
# Chart handler
# ---------------------------------------------------------------------------

async def handle_chart(
    user_prompt: str,
    session_id: str,
    ingestion_id: str,
    role: str = None,
    project_id: str = None,
):
    if state.current_ingestion_id != ingestion_id:
        if not data_loader.init_data(ingestion_id):
            return None, f"❌ Ingestion '{ingestion_id}' not found."

    llm = llm_client.LLMClient()
    chart_type = _detect_chart_type(user_prompt)

    # --- SQL generation ---
    cache_key = user_prompt.lower().strip()
    sql = _sql_cache.get(cache_key)

    if not sql:
        sql_prompt = CHART_SQL_PROMPT.format(user_prompt=user_prompt)
        raw_sql = llm.generate(sql_prompt, temperature=0.05)
        sql = _sanitize_sql(raw_sql or "")

    if not sql or sql.upper() == "N/A":
        sql = _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP)
        if not sql:
            return None, "Could not determine what data to chart."

    # Execute SQL with retries
    df, err = data_loader.execute_sql(sql)

    for attempt in range(2):
        if err or not _is_df_usable(df):
            fb = _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP)
            if fb and fb != sql:
                logger.info(f"Chart SQL retry {attempt + 1}: using fallback")
                df, err = data_loader.execute_sql(fb)
                sql = fb
                if not err and _is_df_usable(df):
                    break
            else:
                # Ask LLM to correct
                fix_prompt = (
                    f"Fix this DuckDB SQL query. Error: {err or 'empty result'}\n"
                    f"Original SQL: {sql}\n"
                    f"Request: {user_prompt}\n"
                    "Tables: flattened_tests(test_name,status,duration,error,spec_file), "
                    "test_cases(module_name,priority,title). JOIN: test_cases.title=flattened_tests.test_name\n"
                    "Return ONLY corrected SQL:"
                )
                fixed = llm.generate(fix_prompt, temperature=0.1)
                if fixed:
                    sql = _sanitize_sql(fixed)
                    df, err = data_loader.execute_sql(sql)
                break

    if err:
        return None, f"SQL error: {err}"
    if not _is_df_usable(df):
        return None, "No data returned for this chart."

    # Cache working SQL
    _sql_cache[cache_key] = sql
    if len(_sql_cache) > 100:
        for k in list(_sql_cache.keys())[:20]:
            del _sql_cache[k]

    return _generate_chart_from_df(df, user_prompt, session_id, sql, chart_type, llm)


def _generate_chart_from_df(
    df: pd.DataFrame,
    user_prompt: str,
    session_id: str,
    sql: str,
    chart_type: str,
    llm,
):
    if not _is_df_usable(df):
        return None, "No data available."

    df = df.dropna(how="all")
    if df.empty:
        return None, "Data is empty after cleaning."

    # Serialize data sample for the prompt
    data_sample = _convert_timestamp(df.head(50).to_dict(orient="records"))
    # Replace NaN
    data_sample = [
        {k: ("" if (isinstance(v, float) and np.isnan(v)) else v) for k, v in row.items()}
        for row in data_sample
    ]

    code_prompt = CHART_CODE_PROMPT.format(
        user_prompt=user_prompt,
        chart_type=chart_type,
        data_sample=json.dumps(data_sample, indent=2, ensure_ascii=False),
        columns=list(df.columns),
    )

    code = llm.generate(code_prompt, temperature=0.2)
    if not code:
        return None, "Chart code generation failed."

    code = _sanitize_plotly_code(code)
    logger.debug(f"Chart code:\n{code}")

    try:
        import plotly.express as px
        import plotly.graph_objects as go

        # Build namespace — `data` is list of dicts (LLM uses it directly or converts to df)
        ns = {
            "px": px,
            "go": go,
            "pd": pd,
            "np": np,
            "data": data_sample,
        }
        exec(code, ns)  # noqa: S102
        fig = ns.get("fig")
        if fig is None:
            raise ValueError("No 'fig' variable produced by chart code.")

        # Apply consistent layout overrides
        fig = _apply_chart_layout(fig)

        # Ensure title
        if not getattr(fig.layout.title, "text", None):
            fig.update_layout(title=dict(text=user_prompt[:60]))

        chart_json = fig.to_json()
        memory.store_chart(session_id, user_prompt, chart_json, {"sql": sql})
        return chart_json, None

    except Exception as exc:
        logger.error(f"Chart exec error: {exc}")
        # Attempt minimal fallback chart
        try:
            import plotly.express as px

            fallback_fig = _minimal_fallback_chart(df, user_prompt, chart_type, px)
            if fallback_fig:
                fallback_fig = _apply_chart_layout(fallback_fig)
                chart_json = fallback_fig.to_json()
                memory.store_chart(session_id, user_prompt, chart_json, {"sql": sql, "fallback": True})
                return chart_json, None
        except Exception as fb_exc:
            logger.error(f"Fallback chart also failed: {fb_exc}")
        return None, f"Chart generation failed: {exc}"


def _minimal_fallback_chart(df: pd.DataFrame, prompt: str, chart_type: str, px):
    """Generate a guaranteed-safe minimal chart from any dataframe."""
    cols = list(df.columns)
    if len(cols) < 2:
        return None

    # Find a numeric column and a categorical column
    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    if not num_cols:
        return None

    x_col = cat_cols[0] if cat_cols else cols[0]
    y_col = num_cols[0]

    title = prompt[:60]

    if chart_type == "pie" and x_col and y_col:
        return px.pie(df, names=x_col, values=y_col, title=title)
    else:
        fig = px.bar(
            df,
            x=x_col,
            y=y_col,
            title=title,
            color_discrete_sequence=["#60a5fa"],
        )
        fig.update_traces(text=df[y_col], textposition="outside")
        return fig