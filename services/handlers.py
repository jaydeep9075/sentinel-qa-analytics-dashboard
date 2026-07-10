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

    llm = llm_client.LLMClient()

    learning_context = memory.get_learning_context(user_id, nid, workspace_id, user_message, limit=6)
    related_concepts = memory.get_related_concepts(user_id, nid, workspace_id, user_message, limit=8)

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

    raw = llm.generate(
        CHAT_DECISION_PROMPT.format(
            history=_build_history(session_id, user_id, nid),
            user_message=augmented_message,
        ),
        temperature=0.05,
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
                df_safe = df.copy()
                for col in df_safe.select_dtypes(include=["datetime64"]).columns:
                    df_safe[col] = df_safe[col].astype(str)
                df_safe = df_safe.where(pd.notna(df_safe), other="")
                answer_prompt = CHAT_ANSWER_PROMPT.format(
                    user_message=augmented_message,
                    row_count=len(df),
                    data_json=df_safe.head(50).to_json(orient="records", force_ascii=False),
                )
                response = llm.generate(answer_prompt, temperature=0.15)
                if not response:
                    if len(df) == 1 and len(df.columns) == 1:
                        response = f"📊 **Result:** {df.iloc[0, 0]}"
                    elif len(df.columns) <= 3:
                        rows_fmt = "\n".join(
                            f"{i+1}. " + " | ".join(str(v) for v in r)
                            for i, r in enumerate(df.head(25).itertuples(index=False))
                        )
                        response = f"**Results ({len(df)} rows):**\n{rows_fmt}"
                    else:
                        response = f"Found **{len(df)} rows**. Use the chart feature to visualize."

    elif action == "vector":
        docs = data_loader.vector_search(data, top_k=5)
        ctx = "\n\n".join(d["text"][:400] for d in docs) if docs else ""
        response = (llm.generate(f"Context:\n{ctx}\n\nQuestion: {user_message}\n\nAnswer concisely:",
                                 temperature=0.2) or "No relevant info found.") if ctx else "No relevant information found."

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

    # STEP 1: Deterministic chart type (no LLM involved)
    chart_type = detect_chart_type(user_prompt)
    logger.info(f"Chart type='{chart_type}' for: '{user_prompt[:60]}'")

    # STEP 2: SQL
    cache_key = user_prompt.lower().strip()
    sql = _sql_cache.get(cache_key)
    if not sql:
        raw_sql = llm.generate(
            CHART_SQL_PROMPT.format(user_prompt=user_prompt, chart_type=chart_type),
            temperature=0.05,
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
                )
                if fixed_sql:
                    sql = _sanitize_sql(fixed_sql)
                    df, err = data_loader.execute_sql(sql)
                break

    if err:    return None, f"SQL error: {err}"
    if not _is_df_usable(df): return None, "No data returned for this chart."

    _sql_cache[cache_key] = sql
    if len(_sql_cache) > 100:
        for k in list(_sql_cache.keys())[:20]:
            del _sql_cache[k]

    return _generate_chart(df, user_prompt, session_id, sql, chart_type, llm, user_id, nid, workspace_id)


def _generate_chart(df, user_prompt, session_id, sql, chart_type, llm, user_id, ingestion_id, workspace_id):
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
            user_prompt=user_prompt,
            chart_type=chart_type,
            data_sample=json.dumps(data_sample, indent=2, ensure_ascii=False),
            columns=list(df.columns),
            chart_template=template,
        ),
        temperature=0.1,
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