"""
handlers.py — Chat and chart request handlers.

CHART PIPELINE
    prompt -> chart_spec.parse()   (deterministic intent: type, measure,
                                    dimension, breakdown, top-N, filters)
           -> SQL                  (LLM writes it, spec constrains it; a
                                    deterministic builder covers the misses)
           -> chart_spec.reconcile (does the returned data actually support
                                    the requested form? downgrade if not)
           -> chart_builder        (themed figure + insight + table view)

The LLM used to write the Plotly code, which was then exec()'d. It no longer
does: the code it produced was generic (it can't know a pass-rate chart wants a
95% target line or that 40 categories should lie down), it was the slowest and
priciest step in the request, and it failed at runtime in ways nothing caught
until a user saw a broken chart. `chart_builder` covers every case
deterministically. The LLM keeps SQL, which it is genuinely good at.
"""

import asyncio
import json
import re
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi.concurrency import run_in_threadpool

from . import (
    config, data_loader, memory, llm_client, state, schema_context,
    chart_spec as chart_spec_mod, chart_builder,
)
from .prompts import (
    CHAT_DECISION_PROMPT,
    CHAT_ANSWER_PROMPT,
    CHAT_MULTI_ANSWER_PROMPT,
    CHAT_VALIDATION_PROMPT,
    CHAT_RELEASE_VERDICT,
    CHART_SQL_PROMPT,
    FALLBACK_SQL_MAP,
    CHART_FALLBACK_SQL_MAP,
)

def _get_test_results_table() -> str:
    """Get the actual table name for test results.
    Supports both old (flattened_tests) and new (structured_test_results) names."""
    try:
        with state._duck_query_lock:
            tables = state.duck_conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory'").df()
        table_names = tables['table_name'].tolist() if not tables.empty else []

        if "structured_test_results" in table_names:
            return "structured_test_results"
        elif "flattened_tests" in table_names:
            return "flattened_tests"
        else:
            return "flattened_tests"
    except Exception as e:
        logging.warning(f"Could not query table names: {e}, using default")
        return "flattened_tests"

logger = logging.getLogger(__name__)
_sql_cache: dict = {}


# Tasks kept alive for their lifetime: asyncio only holds a weak reference to
# a bare create_task() result, so a task nobody keeps can be garbage-collected
# mid-flight and silently never run.
_background_tasks: set = set()


def _persist_in_background(fn, *args, **kwargs) -> None:
    """Run a persistence write without making the user wait for it.

    Storing the message, updating the learning signals and rebuilding the
    knowledge graph are all LanceDB writes that the answer does not depend
    on — but they were being awaited inline, so every chat paid for them
    before a single word reached the browser (and, being synchronous calls
    inside an `async def`, they blocked the event loop for every other
    request while they ran).

    create_task copies the current context, so the ingestion ContextVars set
    for this request (see state.py) are still correct inside the task.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (a direct synchronous call, e.g. from a test or a
        # script). Deferring is a latency optimisation, never a licence to
        # drop the write — so do it inline instead.
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("Inline persistence failed: %s", exc)
        return

    async def _runner():
        try:
            await run_in_threadpool(fn, *args, **kwargs)
        except Exception as exc:  # never let a bookkeeping write surface as a chat error
            logger.warning(
                "Background persistence failed (%s): %s", getattr(fn, "__name__", fn), exc
            )

    task = asyncio.create_task(_runner())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _feedback_hints(user_id, nid, workspace_id, target_kind, prompt):
    """Positional-argument wrapper so this can be handed to run_in_threadpool."""
    return memory.get_feedback_prompt_hints(
        user_id, nid, workspace_id, target_kind=target_kind, current_prompt=prompt,
    )


def _record_interaction(session_id, user_message, response, user_id, nid,
                        workspace_id, kind: str = "chat") -> None:
    """Persist one Q&A turn plus its learning signals, off the critical path."""
    def _write():
        memory.store_chat_message(
            session_id, "user", user_message,
            user_id=user_id, ingestion_id=nid, workspace_id=workspace_id,
        )
        memory.store_chat_message(
            session_id, "assistant", response,
            user_id=user_id, ingestion_id=nid, workspace_id=workspace_id,
        )
        memory.learn_from_interaction(
            user_id, nid, session_id, workspace_id, user_message, response, kind=kind
        )

    _persist_in_background(_write)


def _enhance_response_formatting(response: str) -> str:
    """Improve response readability and quality through post-processing."""
    if not response or not isinstance(response, str):
        return response

    # Ensure proper spacing around key formatting
    response = re.sub(r'\*\*(\d+%)\*\*', r'**\1**', response)

    # Fix broken bullet lists
    response = re.sub(r'(?<!-)\n(\d+\.)', r'\n\1', response)

    # Ensure newlines around numbered lists for readability
    response = re.sub(r'(\w)\n(\d+\.)', r'\1\n\n\2', response)

    # Add spacing after emojis for clarity
    response = re.sub(r'(📊|✅|❌|⚠️|🎯|📭|💡|🔥|⏱️)([A-Z])', r'\1 \2', response)

    # Remove excessive whitespace while preserving intentional line breaks
    lines = response.split('\n')
    lines = [line.strip() for line in lines]
    response = '\n'.join(lines)

    # Ensure no more than 2 consecutive blank lines
    response = re.sub(r'\n\n\n+', r'\n\n', response)

    return response.strip()


def _improve_numeric_formatting(response: str, df: pd.DataFrame) -> str:
    """Enhance response by adding better numeric formatting when data is available."""
    if df.empty or response.count("**") < 2:
        return response

    # Add summary statistics if multiple numeric columns exist
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 1 and "pass_rate" in df.columns:
        try:
            pass_rate = float(df.iloc[0].get("pass_rate", 0))
            if "READY" not in response and "RELEASE" not in response:
                if pass_rate >= 95:
                    summary = "\n\n✅ **Quality is excellent** — ready for confidence decisions."
                elif pass_rate >= 80:
                    summary = "\n\n⚠️ **Quality is acceptable** but review critical failures before release."
                else:
                    summary = "\n\n❌ **Quality needs attention** — fix failures before proceeding."
                response += summary
        except Exception:
            pass

    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_sql(sql: str) -> str:
    if not sql: return ""
    s = re.sub(r"```sql\s*|```", "", sql, flags=re.IGNORECASE).strip()
    s = re.sub(r"^\s*duckdb\s*:?", "", s, flags=re.IGNORECASE).strip()
    return s.rstrip(";").strip()


def _is_df_usable(df: pd.DataFrame) -> bool:
    return df is not None and not df.empty and not df.dropna(how="all").empty


def _extract_json_object(text: str):
    """Pull the first complete JSON object out of an LLM response.

    The old version used `\\{[^{}]+\\}`, which by construction cannot match any
    object containing a nested object or array-of-objects — so the moment the
    model returned a multi-query decision or embedded metadata, parsing fell
    through to the "does the string contain SELECT?" heuristic and threw the
    structure away. This scans for balanced braces instead, skipping over
    braces that appear inside string literals."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*|```", "", text, flags=re.IGNORECASE).strip()

    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
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
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except Exception:
                        break
        start = cleaned.find("{", start + 1)
    return None


def _fallback_sql(prompt: str, sql_map: dict) -> str:
    p = prompt.lower()
    for pattern, sql in sql_map.items():
        if re.search(pattern, p):
            return sql
    # Schema-aware dynamic fallback: match whatever real project/module/
    # platform value is actually mentioned in the prompt, for THIS ingested
    # dataset — not a fixed hardcoded set of project codes.
    return schema_context.build_entity_filter_sql(prompt) or ""


# ---------------------------------------------------------------------------
# Correctness guards: entity existence, fallback scope-drift, contradictions
# ---------------------------------------------------------------------------

_ENTITY_REFERENCE_PATTERNS = {
    "project": r"\bproject\s+([A-Za-z][\w\-]{0,24})\b",
    "platform": r"\bplatform\s+([A-Za-z][\w\-]{0,24})\b",
}

_CONTRADICTION_JOINERS = (" that ", " which ", " but ", " and also ", " yet ")


def _find_unknown_entity_reference(user_message: str, schema_summary: dict):
    """Detect phrasing like 'project ZZZ' or 'platform XYZ' naming a value
    that does not exist anywhere in the ingested data. Returns
    (column_hint, referenced_value) or None."""
    p = user_message or ""
    for col_hint, pattern in _ENTITY_REFERENCE_PATTERNS.items():
        m = re.search(pattern, p, re.IGNORECASE)
        if not m:
            continue
        candidate = m.group(1).strip()
        if not candidate:
            continue
        known = {v.lower() for v in schema_context.all_known_values(schema_summary, column_hint=col_hint)}
        if candidate.lower() not in known:
            return (col_hint, candidate)
    return None


def _fallback_would_drop_entity(original_sql: str, fallback_sql: str, mentions: dict) -> bool:
    """True if the user named a specific known entity value, the originally
    attempted SQL referenced it, but the fallback SQL doesn't — i.e. the
    fallback would silently broaden scope past what was asked."""
    orig_lower = (original_sql or "").lower()
    fb_lower = (fallback_sql or "").lower()
    for value in mentions.values():
        v = str(value).lower()
        if v in orig_lower and v not in fb_lower:
            return True
    return False


def _detect_contradiction(user_message: str, schema_summary: dict):
    """Detect prompts that logically AND together two mutually-exclusive
    known status values (e.g. 'failed tests that passed'). Returns the
    list of conflicting values, or None."""
    p = (user_message or "").lower()
    status_values = [v.lower() for v in schema_context.all_known_values(schema_summary, column_hint="status")]
    mentioned = [v for v in status_values if re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", p)]
    distinct_mentioned = list(dict.fromkeys(mentioned))
    if len(distinct_mentioned) < 2:
        return None
    if any(j in p for j in _CONTRADICTION_JOINERS):
        return distinct_mentioned
    return None


_MAX_STRUCTURED_LIMIT = 50


def _parse_requested_limit(p: str) -> int:
    """Extract N from phrasing like 'top 5', 'bottom 10', '3 highest'. Defaults to 1."""
    m = re.search(r"\btop\s+(\d+)\b", p) or re.search(r"\bbottom\s+(\d+)\b", p)
    if not m:
        m = re.search(r"\b(\d+)\s+(?:highest|lowest|best|worst)\b", p)
    if not m:
        return 1
    return max(1, min(_MAX_STRUCTURED_LIMIT, int(m.group(1))))


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
    limit = _parse_requested_limit(p)
    return {"metric": metric, "entity": entity, "direction": direction, "limit": limit}


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
            f" FROM {_get_test_results_table()}"
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

    limit = max(1, min(_MAX_STRUCTURED_LIMIT, int(intent.get("limit", 1))))

    if direction == "both":
        return (
            "WITH base AS ("
            f"{base}"
            ") "
            "SELECT * FROM ("
            "SELECT 'highest' AS rank_type, * FROM base ORDER BY " + metric_col + f" DESC NULLS LAST LIMIT {limit}"
            ") h "
            "UNION ALL "
            "SELECT * FROM ("
            "SELECT 'lowest' AS rank_type, * FROM base ORDER BY " + metric_col + f" ASC NULLS LAST LIMIT {limit}"
            ") l"
        )

    order = "DESC" if direction == "highest" else "ASC"
    return (
        "WITH base AS ("
        f"{base}"
        ") "
        "SELECT * FROM base ORDER BY " + metric_col + f" {order} NULLS LAST LIMIT {limit}"
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


_ANSWER_ROW_CAP = 50


def _dataset_facts(df: pd.DataFrame, cap: int = _ANSWER_ROW_CAP) -> str:
    """Whole-result statistics for the answer prompt.

    Only the first `cap` rows of a result are sent to the LLM, but questions
    like "how many failures overall?" or "which module is worst?" are about the
    WHOLE result. Given 400 rows and the first 50, the model either answers
    from the visible slice (wrong) or hedges (useless). These facts are
    computed in pandas over every row, so the totals and extremes it quotes are
    the real ones regardless of how much of the table it can see."""
    if df is None or df.empty:
        return ""

    lines: list[str] = [f"Total rows in the full result: {len(df)}"]
    if len(df) > cap:
        lines.append(
            f"IMPORTANT: only the first {cap} rows are shown below. Use the "
            f"aggregates in this section for any statement about the whole "
            f"result — never extrapolate from the visible rows."
        )

    numeric = df.select_dtypes(include=[np.number])
    for col in list(numeric.columns)[:8]:
        series = numeric[col].dropna()
        if series.empty:
            continue
        stat = (f"{col}: sum={series.sum():,.2f} avg={series.mean():,.2f} "
                f"min={series.min():,.2f} max={series.max():,.2f}")
        # Name the row holding the extreme, which is usually the actual answer
        # to "which X is worst/best".
        label_cols = [c for c in ("test_name", "module_name", "project_name",
                                  "platform_type", "status", "browser", "build_id")
                      if c in df.columns]
        if label_cols:
            try:
                hi = df.loc[series.idxmax()]
                lo = df.loc[series.idxmin()]
                hi_label = " / ".join(str(hi[c]) for c in label_cols[:2])
                lo_label = " / ".join(str(lo[c]) for c in label_cols[:2])
                stat += f" | highest: {hi_label} | lowest: {lo_label}"
            except Exception:
                pass
        lines.append(f"- {stat}")

    for col in [c for c in df.columns if c not in numeric.columns][:6]:
        try:
            all_counts = df[col].value_counts()
            # A column where (nearly) every value is distinct — test_name,
            # error text — has no distribution worth reporting; listing its
            # first five values at one occurrence each is pure token noise.
            if all_counts.empty or len(all_counts) > max(1, len(df) * 0.5):
                continue
            top = ", ".join(f"{k} ({v})" for k, v in all_counts.head(5).items())
            suffix = f", …+{len(all_counts) - 5} more" if len(all_counts) > 5 else ""
            lines.append(f"- {col} distribution: {top}{suffix}")
        except Exception:
            continue

    return "\n".join(lines)


async def _run_sql_with_repair(llm, sql: str, user_message: str, user_id: str,
                               workspace_id: str, attempts: int = 2):
    """Execute SQL, and if DuckDB rejects it, hand the error back to the model
    to fix. A complex question ("tests failing on mobile but passing on desktop
    in the checkout module, ranked by duration") is exactly where the first
    query is most likely to have a small syntax or column error — and where
    silently falling back to a generic keyword-matched query produces a
    confident answer to a much simpler question. One repair round-trip is far
    cheaper than a wrong answer. Returns (df, err, sql)."""
    df, err = await run_in_threadpool(data_loader.execute_sql, sql)
    if not err and _is_df_usable(df):
        return df, None, sql

    for _ in range(attempts):
        if not err:
            break  # ran fine but returned nothing — repairing syntax won't help
        fixed = await llm.agenerate(
            "The following DuckDB query failed. Return ONLY the corrected SQL "
            "(no markdown, no explanation), preserving the original intent and "
            "every filter it applied.\n\n"
            f"Question: {user_message}\nSQL: {sql}\nError: {err}",
            temperature=0.0, user_id=user_id, workspace_id=workspace_id,
        )
        if not fixed:
            break
        candidate = _sanitize_sql(fixed)
        if not candidate or candidate == sql:
            break
        sql = candidate
        df, err = await run_in_threadpool(data_loader.execute_sql, sql)
        if not err and _is_df_usable(df):
            return df, None, sql

    return df, err, sql


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


_SUPERLATIVE_RE = re.compile(
    r"\b(highest|lowest|most|least|worst|best|slowest|fastest|top|bottom|"
    r"leads?|trails?|majority|more than|fewer than|all of|none of|every)\b",
    re.IGNORECASE,
)

# Figures the model is entitled to write without them appearing in the data:
# ordinals and small list positions ("1.", "top 3"), and the percentage-point
# vocabulary the answer prompt asks for.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numeric_tokens(text: str) -> set:
    out = set()
    for raw in _NUMBER_RE.findall(text or ""):
        try:
            out.add(round(float(raw.replace(",", "")), 2))
        except ValueError:
            continue
    return out


def _grounded_numbers(df: pd.DataFrame, facts: str) -> set:
    """Every figure a correct answer could legitimately quote.

    Cell values, plus the aggregates already computed over the whole result
    (`_dataset_facts`), plus the row count and simple derivations of a value
    the answer is expected to make (a rounded percentage, a difference between
    two of them)."""
    grounded = _numeric_tokens(facts)
    grounded.add(round(float(len(df)), 2))

    numeric = df.select_dtypes(include=[np.number])
    for col in numeric.columns:
        for value in numeric[col].dropna().tolist():
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            grounded.add(round(v, 2))
            grounded.add(round(v, 1))
            grounded.add(round(v, 0))

    # String columns can carry numbers too ("2.3s", "build 41").
    for col in df.columns:
        if col in numeric.columns:
            continue
        try:
            for value in df[col].dropna().astype(str).head(_ANSWER_ROW_CAP).tolist():
                grounded |= _numeric_tokens(value)
        except Exception:
            continue

    # Differences between any two grounded figures — "mobile trails desktop by
    # 15.2 points" is arithmetic on data the model was given, not a new claim.
    base = sorted(grounded)[:120]
    for i, a in enumerate(base):
        for b in base[i + 1:]:
            grounded.add(round(abs(a - b), 2))
            grounded.add(round(abs(a - b), 1))
    return grounded


def _needs_llm_validation(draft: str, df: pd.DataFrame, facts: str) -> bool:
    """Decide whether the validation round-trip can be skipped.

    The validation pass is a second full LLM call re-sending the same data,
    and it was running on every single answer — roughly a third of the wait,
    spent overwhelmingly on answers that turn out to be fine. This gate keeps
    the check where it earns its cost and drops it where it cannot help:

    - Any superlative or ordering claim ("worst module", "leads by") goes to
      the validator. Per CHAT_VALIDATION_PROMPT's own checklist that is the
      most common error class, and it is not checkable from the numbers alone.
    - Any figure in the draft that is not present in, or derivable from, the
      data goes to the validator — that is exactly the hallucinated-number
      case it exists to catch.
    - Everything else — an answer whose every figure reconciles against the
      result and which makes no ranking claim — is returned as written.
    """
    text = str(draft or "")
    if not text.strip():
        return False
    if df is None or df.empty:
        return True
    if _SUPERLATIVE_RE.search(text):
        return True

    grounded = _grounded_numbers(df, facts)
    for value in _numeric_tokens(text):
        # Small integers are list markers, years, "top 5" — not data claims.
        if value <= 12 and float(value).is_integer():
            continue
        if value in grounded:
            continue
        if any(abs(value - g) <= 0.05 for g in grounded):
            continue
        return True
    return False


async def _validate_grounded_response(
    llm,
    user_message: str,
    draft_answer: str,
    df_safe: pd.DataFrame,
    user_id: str = "anonymous",
    workspace_id: str = "default",
) -> str:
    raw = await llm.agenerate(
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

    source_table = (
        "project_metrics" if entity == "project"
        else "flattened_tests" if entity == "platform"
        else "module_metrics"
    )

    if "rank_type" in df.columns and len(df) >= 2:
        lines = ["📊 **Validated comparison result**"]
        for direction_label, rank_key in (("Highest", "highest"), ("Lowest", "lowest")):
            group = df[df["rank_type"] == rank_key]
            for i, (_, row) in enumerate(group.iterrows(), start=1):
                value = row.get(value_col, "N/A")
                prefix = f"{direction_label} #{i}" if len(group) > 1 else direction_label
                lines.append(f"- **{prefix} {metric_label}:** {value} on {_entity_name(row)}")
        lines.append(f"Validation source: computed directly from {source_table}.")
        return "\n".join(lines)

    if len(df) > 1:
        lines = [f"📊 **Validated result — {len(df)} results by {metric_label}**"]
        for i, (_, row) in enumerate(df.iterrows(), start=1):
            value = row.get(value_col, "N/A")
            lines.append(f"{i}. **{value}** — {_entity_name(row)}")
        lines.append(f"Validation source: computed directly from {source_table}.")
        return "\n".join(lines)

    row = df.iloc[0]
    value = row.get(value_col, "N/A")
    return (
        "📊 **Validated result**\n"
        f"- **{metric_label.title()}:** {value}\n"
        f"- **Entity:** {_entity_name(row)}\n"
        f"- Validation source: computed directly from {source_table}."
    )


# ---------------------------------------------------------------------------
# Cross-build (historical/trend) questions
#
# Two tiers, matched to two different costs:
# - "How are we trending" / "vs the previous build" -> answered entirely
#   from each build's cached summary.json (data_loader.list_builds). A few
#   KB per build, so this is fast no matter how much ingestion history
#   exists - it's not something that needs bounding.
# - "Which tests failed in the last N builds" -> genuinely needs row-level
#   data from more than one build's full dataset. That's real per-build
#   query cost, so it's routed through data_loader.execute_sql_across_builds,
#   which is hard-capped at config.MAX_CROSS_BUILD_QUERY_BUILDS regardless
#   of how many builds actually exist.
# ---------------------------------------------------------------------------

_HISTORICAL_PHRASES = (
    "previous build", "prior build", "last build", "past build", "past builds",
    "earlier build", "build history", "compare build", "compare builds",
    "build over build", "build-over-build", "across builds", "over builds",
    "over time", "historical trend", "trend over time", "week over week",
    "since last release", "since the last build", "regressed", "regression over",
    "improving over", "getting better", "getting worse", "how are we trending",
    "trending over", "last few builds", "last several builds", "recent builds",
)

_ROW_LEVEL_HISTORICAL_CUES = (
    "which tests", "which test", "list the tests", "what tests", "show tests",
    "show the tests", "same test", "same tests", "still failing", "newly failing",
    "newly broken", "flaky", "error message", "errors in", "failed in both",
    "failed in all", "failed in each",
)


def _detect_historical_intent(prompt: str) -> bool:
    p = (prompt or "").lower()
    return any(phrase in p for phrase in _HISTORICAL_PHRASES)


def _needs_row_level_history(prompt: str) -> bool:
    p = (prompt or "").lower()
    return any(cue in p for cue in _ROW_LEVEL_HISTORICAL_CUES)


def _build_history_trend_answer(nid: str, limit: int = None) -> str:
    """Deterministic (no LLM call) trend/comparison answer built purely from
    list_builds()'s cached summaries. Returns "" if there's fewer than 2
    builds to compare - callers should fall through to the normal flow in
    that case rather than treating it as an error."""
    builds = data_loader.list_builds(limit=limit or config.MAX_TREND_BUILDS)
    if len(builds) < 2:
        return ""

    current_idx = next((i for i, b in enumerate(builds) if b.get("build_id") == nid), 0)
    current = builds[current_idx]
    previous = builds[current_idx + 1] if current_idx + 1 < len(builds) else None

    lines = ["📊 **Build trend (most recent first)**"]
    for b in builds:
        marker = " ← current" if b.get("build_id") == current.get("build_id") else ""
        pr = b.get("pass_rate")
        pr_str = f"{pr}%" if pr is not None else "n/a"
        date = (b.get("ingested_at") or "")[:10]
        executed = b.get("executed_tests", b.get("total_tests", "?"))
        lines.append(
            f"- {date} · **{pr_str}** pass rate · {b.get('passed', '?')}/{executed} passed{marker}"
        )

    if previous is not None:
        cur_pr, prev_pr = current.get("pass_rate"), previous.get("pass_rate")
        if cur_pr is not None and prev_pr is not None:
            delta = round(cur_pr - prev_pr, 2)
            if delta > 0.5:
                verdict = f"📈 **Improving** — pass rate is up **{delta} points** vs the previous build."
            elif delta < -0.5:
                verdict = f"📉 **Regressing** — pass rate is down **{abs(delta)} points** vs the previous build."
            else:
                verdict = "➡️ **Stable** — pass rate is essentially unchanged from the previous build."
            lines.append(f"\n{verdict}")

    lines.append(
        f"\n*(Showing the {len(builds)} most recent builds. Ask about specific failing "
        "tests to see row-level detail across builds.)*"
    )
    return "\n".join(lines)


def _build_trend_dataframe(limit: int = None) -> pd.DataFrame:
    """Real cross-build trend data for chart requests (pass rate/test count
    over time), from the same cached summaries as _build_history_trend_answer
    - replaces the old single-build proxy (module name order standing in
    for time) with an actual time series."""
    builds = data_loader.list_builds(limit=limit or config.MAX_TREND_BUILDS)
    if len(builds) < 2:
        return pd.DataFrame()
    chronological = list(reversed(builds))  # oldest -> newest, left-to-right on a line chart
    return pd.DataFrame([
        {
            "build_date": (b.get("ingested_at") or "")[:10],
            "build_id": b.get("build_id"),
            "pass_rate": b.get("pass_rate"),
            "total_tests": b.get("total_tests"),
            "failed": b.get("failed"),
        }
        for b in chronological
    ])


_HISTORY_TURN_CHAR_CAP = 220


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
        text = h.get("prompt", "") if role == "user" else h.get("response", "")
        # History is only here to give the decision LLM conversational
        # context (what was asked/answered before), not to re-litigate
        # exact past numbers - an assistant turn can be a full formatted
        # table/paragraph that costs real tokens on EVERY subsequent
        # message in the session if sent unbounded. Cap per turn instead.
        text = str(text)
        if len(text) > _HISTORY_TURN_CHAR_CAP:
            text = text[:_HISTORY_TURN_CHAR_CAP].rstrip() + "…"
        lines.append(f"{'User' if role == 'user' else 'Assistant'}: {text}")
    return "\n".join(lines[-20:])




def _build_schema_context(schema_summary: dict, max_tables: int = 8, max_columns: int = 25) -> str:
    """Renders the '[RUNTIME TABLE PROFILE]' prompt block from an
    already-computed schema_context.build_schema_summary() result, rather
    than issuing its own fresh DESCRIBE/COUNT/SELECT burst against every
    table - that summary is cached per ingestion_id and carries the same
    row_count/columns data this needs."""
    tables = schema_summary.get("tables", {}) if isinstance(schema_summary, dict) else {}
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



def _filter_relevant_vector_docs(
    docs: list, relative_margin: float = 1.6, absolute_slack: float = 0.05
) -> list:
    """Keep only results reasonably close to the single best match, instead
    of always feeding the LLM every top_k result regardless of relevance.
    A RELATIVE cutoff (vs. the best distance in this result set) rather
    than a fixed absolute threshold, since LanceDB's `_distance` scale
    depends on the embedding model/dataset and there's no single number
    that's safely correct everywhere without empirical tuning per corpus."""
    if not docs:
        return []
    distances = [d.get("_distance") for d in docs if isinstance(d.get("_distance"), (int, float))]
    if not distances:
        return docs
    cutoff = min(distances) * relative_margin + absolute_slack
    return [
        d for d in docs
        if not isinstance(d.get("_distance"), (int, float)) or d["_distance"] <= cutoff
    ]


async def _answer_from_multiple_queries(llm, sql_steps: list, user_message: str,
                                        augmented_message: str, feedback_hints: str,
                                        user_id: str, workspace_id: str):
    """Run each step of a decomposed question and answer from all of them at
    once. Returns (response, primary_df).

    Every step is labelled so the answering model knows which numbers belong to
    which sub-question — without labels, several result sets concatenated into
    one blob is how "mobile pass rate" and "desktop pass rate" get swapped."""
    blocks: list[str] = []
    frames: list[pd.DataFrame] = []
    failures: list[str] = []

    for step in sql_steps[:4]:   # a question needing >4 queries is a report, not a chat turn
        sql = _sanitize_sql(step["sql"])
        if not sql:
            continue
        df, err, sql = await _run_sql_with_repair(
            llm, sql, user_message, user_id, workspace_id)
        if err or not _is_df_usable(df):
            failures.append(f"{step['label']}: {err or 'no matching rows'}")
            continue
        frames.append(df)
        df_safe = _prepare_df_for_prompt(df)
        blocks.append(
            f"--- {step['label']} ({len(df)} rows) ---\n"
            f"{_dataset_facts(df)}\n"
            f"Rows:\n{df_safe.head(_ANSWER_ROW_CAP).to_json(orient='records', force_ascii=False)}"
        )

    if not blocks:
        detail = "; ".join(failures) if failures else "no data"
        return (f"📭 I couldn't retrieve data for that question ({detail}). "
                "Try rephrasing or narrowing it."), pd.DataFrame()

    note = ""
    if failures:
        # Say what's missing rather than answering the answerable part as if it
        # were the whole question.
        note = ("\n\n[NOTE] These sub-queries returned nothing and must be reported "
                "as unavailable rather than guessed at: " + "; ".join(failures))

    answer = await llm.agenerate(
        CHAT_MULTI_ANSWER_PROMPT.format(
            user_message=augmented_message + note,
            feedback_hints=feedback_hints or "None",
            result_blocks="\n\n".join(blocks),
        ),
        temperature=0.15, user_id=user_id, workspace_id=workspace_id,
    )
    if not answer:
        return _fallback_tabular_response(frames[0]), frames[0]
    return answer, frames[0]


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

async def handle_chat(user_message: str, session_id: str, ingestion_id: str,
                      role: str = None, project_id: str = None,
                      user_id: str = "anonymous", workspace_id: str = "default"):
    nid = str(ingestion_id or "").strip()
    response_df = pd.DataFrame()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, nid)
    if _entry is None:
        return f"❌ Ingestion '{ingestion_id}' not found or data unavailable."
    state.set_active_ingestion(nid, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

    # Layer 1: deterministic intent handler for critical analytical prompts.
    structured_intent = _detect_structured_intent(user_message)
    if structured_intent:
        sql = _build_structured_sql(structured_intent)
        df, err = await run_in_threadpool(data_loader.execute_sql, sql)
        if not err and _is_df_usable(df):
            response = _format_structured_response(structured_intent, df)
            _record_interaction(session_id, user_message, response,
                                user_id, nid, workspace_id)
            return response

    # Layer 1b: "how are we trending" / "vs the previous build" - answered
    # from cached per-build summaries only (see _build_history_trend_answer),
    # never touching another build's full dataset. Skipped when the question
    # actually needs row-level detail (e.g. "which tests failed") - that
    # goes through the bounded cross-build SQL path further below instead.
    wants_cross_build_rows = False
    if _detect_historical_intent(user_message):
        if _needs_row_level_history(user_message):
            wants_cross_build_rows = True
        else:
            trend_response = _build_history_trend_answer(nid)
            if trend_response:
                _record_interaction(session_id, user_message, trend_response,
                                    user_id, nid, workspace_id)
                return trend_response
            # Fewer than 2 builds exist yet - nothing to compare, fall
            # through to the normal single-build flow below.

    llm = llm_client.LLMClient()

    # Four independent lookups, none of which needs any of the others: three
    # LanceDB scans plus the schema summary. Run sequentially on the event
    # loop they added their full combined latency to every chat AND blocked
    # every other request for the duration. Gathered in the threadpool they
    # cost the slowest one and leave the loop free.
    (
        learning_context,
        related_concepts,
        feedback_hints,
        schema_summary,
    ) = await asyncio.gather(
        run_in_threadpool(
            memory.get_learning_context, user_id, nid, workspace_id, user_message, 6
        ),
        run_in_threadpool(
            memory.get_related_concepts, user_id, nid, workspace_id, user_message, 8
        ),
        run_in_threadpool(
            _feedback_hints, user_id, nid, workspace_id, "chat", user_message
        ),
        run_in_threadpool(schema_context.build_schema_summary),
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
    schema_context_block = _build_schema_context(schema_summary)
    if schema_context_block:
        augmented_message += f"\n\n{schema_context_block}"
    if wants_cross_build_rows:
        augmented_message += (
            f"\n\n[NOTE] This question needs row-level data from multiple builds. Write SQL "
            f"against the tables below exactly as if for a single build - it will automatically "
            f"be run against each of the last {config.MAX_CROSS_BUILD_QUERY_BUILDS} builds and "
            f"combined, with a build_id column added to identify which build each row came from."
        )

    raw = await llm.agenerate(
        CHAT_DECISION_PROMPT.format(
            history=_build_history(session_id, user_id, nid),
            user_message=augmented_message,
            schema_examples=schema_context.render_prompt_examples(schema_summary),
        ),
        temperature=0.05,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    if not raw:
        return "⚠️ AI service unavailable. Please try again."

    decision = _extract_json_object(raw)
    if decision is None:
        if "SELECT" in raw.upper():
            sm = re.search(r'SELECT.+', raw, re.IGNORECASE | re.DOTALL)
            decision = {"action": "sql", "data": sm.group() if sm else ""}
        else:
            decision = {"action": "answer", "data": raw.strip()}

    action = decision.get("action", "answer")
    data   = decision.get("data", "")

    # A comparative question ("how does mobile compare to desktop, and which
    # modules regressed?") is genuinely two or three queries. Forcing it into
    # one means either a contorted CTE the model gets wrong, or an answer that
    # silently drops half the question. The decision prompt may return a list.
    sql_steps: list[dict] = []
    if action == "sql_multi" or isinstance(data, list):
        action = "sql_multi"
        for step in (data if isinstance(data, list) else []):
            if isinstance(step, dict) and step.get("sql"):
                sql_steps.append({"label": str(step.get("label") or "Result"),
                                  "sql": str(step["sql"])})
            elif isinstance(step, str) and step.strip():
                sql_steps.append({"label": f"Result {len(sql_steps) + 1}", "sql": step})
        if not sql_steps:
            action, data = "answer", ""

    if action == "sql_multi":
        pass
    elif isinstance(data, str) and "SELECT" in data.upper():
        action = "sql"
    elif action == "answer" and _looks_like_data_question(user_message):
        # Only escalate when the model landed on "answer" without
        # recognizing this as a data question at all - never override a
        # deliberate "vector" choice, which already IS the model
        # recognizing this as a data question (just one sql can't answer).
        action = "sql"
        data = _fallback_sql(user_message, FALLBACK_SQL_MAP)

    if action == "sql_multi":
        response, response_df = await _answer_from_multiple_queries(
            llm, sql_steps, user_message, augmented_message, feedback_hints,
            user_id, workspace_id,
        )

    elif action == "sql":
        sql = _sanitize_sql(data) if data else ""
        # schema_summary already computed above, reused here (cached per ingestion_id).

        contradiction = _detect_contradiction(user_message, schema_summary)
        if contradiction:
            response = (
                "⚠️ That question combines conditions that can't both be true for the same test ("
                + " + ".join(contradiction)
                + "). Could you clarify which status you meant?"
            )
        else:
            if not sql:
                df, err = pd.DataFrame(), "empty"
            elif wants_cross_build_rows:
                recent_build_ids = [b["build_id"] for b in data_loader.list_builds(limit=config.MAX_CROSS_BUILD_QUERY_BUILDS)]
                df, err = await run_in_threadpool(data_loader.execute_sql_across_builds, sql, recent_build_ids)
            else:
                # Repair before falling back: a keyword-matched fallback query
                # answers a *simpler* question than the one asked, so it should
                # be the last resort, not the first response to a syntax slip.
                df, err, sql = await _run_sql_with_repair(
                    llm, sql, user_message, user_id, workspace_id)
            unknown_ref = _find_unknown_entity_reference(user_message, schema_summary)

            if (err or not _is_df_usable(df)) and unknown_ref:
                col_hint, bad_value = unknown_ref
                known_values = schema_context.all_known_values(schema_summary, column_hint=col_hint)
                response = (
                    f"❌ I couldn't find '{bad_value}' as a {col_hint} in the ingested data. "
                    f"Available: {', '.join(known_values) if known_values else 'none ingested yet'}."
                )
            else:
                if err or not _is_df_usable(df):
                    mentions = schema_context.find_entity_mentions(user_message, schema_summary)
                    fb = _fallback_sql(user_message, FALLBACK_SQL_MAP)
                    if fb and fb != sql and not _fallback_would_drop_entity(sql, fb, mentions):
                        df, err = await run_in_threadpool(data_loader.execute_sql, fb)
                        sql = fb

                if err:
                    response = f"⚠️ Could not retrieve that data. Details: {err}"
                elif not _is_df_usable(df):
                    response = "📭 I couldn't find data matching exactly what you asked. Try rephrasing or broadening the request."
                else:
                    response_df = df
                    is_release = any(kw in user_message.lower()
                                     for kw in ("release", "good to go", "ready for", "ship", "deploy"))
                    if is_release and "pass_rate" in df.columns:
                        scope_note = ""
                        mentions = schema_context.find_entity_mentions(user_message, schema_summary)
                        scope_issue = None
                        sql_lower = (sql or "").lower()
                        for col, value in mentions.items():
                            if str(value).lower() not in sql_lower:
                                scope_issue = (col, value)
                                break

                        if scope_issue:
                            col, value = scope_issue
                            escaped_value = str(value).replace("'", "''")
                            scoped_sql = (
                                "SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate,"
                                " COUNT(*) AS total,"
                                " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count"
                                f" FROM flattened_tests WHERE status IN ('passed','failed') AND {col} = '{escaped_value}'"
                            )
                            scoped_df, scoped_err = await run_in_threadpool(data_loader.execute_sql, scoped_sql)
                            if not scoped_err and _is_df_usable(scoped_df):
                                df = scoped_df
                                scope_note = f"\n\n*(Scoped to {col} = '{value}', not the global figure across all projects.)*"
                            else:
                                scope_note = (
                                    f"\n\n⚠️ *Could not verify this is scoped to '{value}' — the figures above are "
                                    "GLOBAL across all projects.*"
                                )

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
                        response = f"{response}{scope_note}"
                    else:
                        df_safe = _prepare_df_for_prompt(df)
                        answer_message = augmented_message
                        if wants_cross_build_rows and "build_id" in df_safe.columns:
                            answer_message += (
                                "\n\n[NOTE] Each row's build_id column identifies which build it came "
                                "from - this data spans multiple builds, not just the current one. "
                                "Explicitly say which build(s) each fact applies to (e.g. call out "
                                "tests that recur across every build vs ones unique to one build)."
                            )
                        dataset_facts = _dataset_facts(df)
                        answer_prompt = CHAT_ANSWER_PROMPT.format(
                            user_message=answer_message,
                            feedback_hints=feedback_hints or "None",
                            row_count=len(df),
                            dataset_facts=dataset_facts or "(none)",
                            data_json=df_safe.head(_ANSWER_ROW_CAP).to_json(
                                orient="records", force_ascii=False),
                        )
                        llm_response = await llm.agenerate(
                            answer_prompt, temperature=0.15, user_id=user_id, workspace_id=workspace_id
                        )
                        if llm_response:
                            # Validation is a second full LLM call re-sending
                            # the same data - only worth it for actual LLM
                            # prose, which can hallucinate. The deterministic
                            # fallback below is a mechanical table dump of
                            # the exact query result - nothing to validate,
                            # so skip the extra round-trip entirely.
                            #
                            # Even for prose, it is only worth it when there
                            # is something a validator could actually catch:
                            # _needs_llm_validation re-derives every figure in
                            # the draft against the result first, and only
                            # pays for the round-trip when a number does not
                            # reconcile or a ranking claim is made.
                            if _needs_llm_validation(llm_response, df, dataset_facts):
                                response = await _validate_grounded_response(
                                    llm,
                                    user_message,
                                    llm_response,
                                    df_safe,
                                    user_id=user_id,
                                    workspace_id=workspace_id,
                                )
                            else:
                                logger.debug("Skipped validation pass: draft is fully grounded")
                                response = llm_response
                        else:
                            response = _fallback_tabular_response(df)

    elif action == "vector":
        search_query = str(data or "").strip() or user_message
        # vector_search loads/runs the embedding model synchronously (CPU
        # work) - offload it like every other blocking call in this path.
        docs = await run_in_threadpool(data_loader.vector_search, search_query, 8)
        relevant = _filter_relevant_vector_docs(docs)
        if relevant:
            # Ingestion already chunks text to ~1200 chars (chunk_text's
            # target - see universal_ingester/core/chunking.py), so a
            # display cap well above that never truncates a properly
            # chunked doc mid-content. A structured row's useful field
            # (e.g. log_excerpt/error) can sit near the END of its
            # assembled "col: val | col: val | ..." text, so a too-small
            # cap here silently hides it even when retrieval found the
            # right document.
            context_lines = [
                f"[{i}] ({d.get('doc_type', 'document')}) {str(d.get('text', '')).strip()[:1500]}"
                for i, d in enumerate(relevant, start=1)
            ]
            vector_prompt = (
                "You are answering from search results over the ingested test/document data "
                "below. Only use information actually present in these excerpts - if none of "
                "them genuinely answer the question, say plainly that you couldn't find relevant "
                "information in the ingested data instead of guessing.\n\n"
                f"Search results:\n{chr(10).join(context_lines)}\n\n"
                f"Question: {user_message}\n\n"
                "Answer concisely, citing the bracket number(s) (e.g. [1]) of whichever result(s) you used."
            )
            response = await llm.agenerate(
                vector_prompt, temperature=0.15, user_id=user_id, workspace_id=workspace_id,
            ) or "No relevant information found in the ingested data."
        else:
            response = "No relevant information found in the ingested data."

    else:
        response = str(data) if data else "I'm not sure how to answer that. Try rephrasing."

    response = _enhance_response_formatting(response)
    if not response_df.empty:
        response = _improve_numeric_formatting(response, response_df)

    _record_interaction(session_id, user_message, response,
                        user_id, nid, workspace_id)
    return response


# ---------------------------------------------------------------------------
# Chart handler
# ---------------------------------------------------------------------------

def _spec_sql_directives(spec) -> str:
    """Turn the parsed intent into explicit instructions for the SQL writer.

    Without this the LLM sees only the raw prompt and routinely returns SQL
    that is *valid* but answers a slightly different question — no LIMIT for a
    "top 5", the wrong measure column, an unrequested platform filter. Stating
    the parse makes the SQL and the rendered chart agree by construction."""
    lines = [f"- Chart form: {spec.chart_type}"]
    if spec.measure:
        cols = ", ".join(spec.measure_columns())
        lines.append(f"- Primary measure: {spec.measure_label} (prefer columns: {cols})")
    if spec.measure2:
        lines.append(f"- Second measure (y axis): {spec.measure2_label()}")
    if spec.dimension:
        cols = ", ".join(spec.dimension_columns())
        lines.append(f"- Group by: {spec.dimension} (prefer columns: {cols})")
    if spec.breakdown:
        lines.append(f"- Also split by: {spec.breakdown} (include that column)")
    if spec.direction != "none":
        order = "DESC" if spec.direction == "highest" else "ASC"
        lines.append(f"- MUST end with ORDER BY <measure> {order} LIMIT {spec.limit}")
    else:
        lines.append(f"- Return at most {spec.limit} rows")
    for col, value in (spec.filters or {}).items():
        lines.append(f"- MUST filter: WHERE {col} = '{value}'")
    if spec.chart_type in ("scatter", "bubble"):
        lines.append("- Return at least TWO numeric columns (one per axis)")
    if spec.chart_type == "heatmap":
        lines.append("- Return exactly TWO categorical columns plus one numeric column")
    if spec.chart_type in ("pie", "donut", "funnel", "treemap"):
        lines.append("- Return ONE categorical column plus ONE numeric column")
    return "\n".join(lines)


async def _chart_sql(llm, spec, user_prompt, prompt_for_llm, schema_summary,
                     user_id, workspace_id):
    """Produce SQL for a chart request, in order of decreasing confidence:
    a deterministic structured query, then the LLM, then the fallback map."""
    structured_intent = _detect_structured_intent(user_prompt)
    if structured_intent:
        return _build_structured_sql(structured_intent), "structured"

    raw_sql = await llm.agenerate(
        CHART_SQL_PROMPT.format(
            user_prompt=prompt_for_llm,
            chart_type=spec.chart_type,
            spec_directives=_spec_sql_directives(spec),
            schema_examples=schema_context.render_prompt_examples(schema_summary),
        ),
        temperature=0.05,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    sql = _sanitize_sql(raw_sql or "")
    if sql and sql.upper() != "N/A":
        return sql, "llm"
    return _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP), "fallback"


async def handle_chart(user_prompt: str, session_id: str, ingestion_id: str,
                       role: str = None, project_id: str = None,
                       user_id: str = "anonymous", workspace_id: str = "default"):
    nid = str(ingestion_id or "").strip()
    _entry = await run_in_threadpool(data_loader.get_or_load_ingestion, nid)
    if _entry is None:
        return None, f"❌ Ingestion '{ingestion_id}' not found.", None
    state.set_active_ingestion(nid, _entry["duck_conn"], _entry["lance_db"], _entry["embedder"])

    llm = llm_client.LLMClient()
    # Independent of each other, and both are blocking reads — see the same
    # treatment in handle_chat.
    feedback_hints, chart_schema_summary = await asyncio.gather(
        run_in_threadpool(
            _feedback_hints, user_id, nid, workspace_id, "chart", user_prompt
        ),
        run_in_threadpool(schema_context.build_schema_summary),
    )
    prompt_for_llm = user_prompt
    if feedback_hints:
        prompt_for_llm += f"\n\n[USER FEEDBACK PREFERENCES]\n{feedback_hints}"
    schema_context_block = _build_schema_context(chart_schema_summary)
    if schema_context_block:
        prompt_for_llm += f"\n\n{schema_context_block}"

    # STEP 1 — parse intent once, deterministically. Everything downstream
    # (SQL shaping, rendering, titling) reads from this single parse, so the
    # query and the picture can't end up answering different questions.
    spec = chart_spec_mod.parse(user_prompt)
    logger.info("Chart spec: %s | prompt=%r", spec.describe(), user_prompt[:80])

    wants_cross_build_rows = _detect_historical_intent(user_prompt) and \
        _needs_row_level_history(user_prompt)

    # A real "pass rate over builds" trend has genuine cross-build data
    # available for free from each build's cached summary.json. Use it rather
    # than asking for SQL against a single build and calling the result a trend.
    if spec.is_cross_build and spec.chart_type in ("line", "area") and not wants_cross_build_rows:
        trend_df = _build_trend_dataframe()
        if not trend_df.empty:
            return await run_in_threadpool(
                _render_and_store,
                trend_df, spec, user_prompt, session_id,
                "-- cross-build trend from each build's summary.json, not a live query --",
                user_id, nid, workspace_id,
            )
        # Fewer than 2 builds exist yet — fall through to the single-build flow.

    # STEP 2 — SQL. Cache only prompts that resolved to something concrete; an
    # ambiguous "compare them" has no anchor, so caching it would replay a
    # stale, wrong-context query across unrelated sessions and datasets.
    chart_entity_mentions = schema_context.find_entity_mentions(user_prompt, chart_schema_summary)
    is_cacheable_prompt = bool(_detect_structured_intent(user_prompt)) or bool(chart_entity_mentions)
    cache_key = f"{nid}:{session_id or 'global'}:{user_prompt.lower().strip()}"
    sql = _sql_cache.get(cache_key) if is_cacheable_prompt else None
    if not sql:
        sql, _source = await _chart_sql(
            llm, spec, user_prompt, prompt_for_llm, chart_schema_summary, user_id, workspace_id,
        )
    if not sql:
        return None, "Could not determine what data to chart.", None

    # STEP 3 — execute, with a bounded repair loop.
    if wants_cross_build_rows:
        recent_build_ids = [b["build_id"] for b in
                            data_loader.list_builds(limit=config.MAX_CROSS_BUILD_QUERY_BUILDS)]
        df, err = await run_in_threadpool(
            data_loader.execute_sql_across_builds, sql, recent_build_ids)
    else:
        df, err = await run_in_threadpool(data_loader.execute_sql, sql)

    if err or not _is_df_usable(df):
        df, err, sql = await _repair_chart_sql(
            llm, sql, err, df, user_prompt, user_id, workspace_id)

    if err:
        return None, f"SQL error: {err}", None
    if not _is_df_usable(df):
        return None, "No data returned for this chart.", None

    if is_cacheable_prompt:
        _sql_cache[cache_key] = sql
        if len(_sql_cache) > 100:
            for k in list(_sql_cache.keys())[:20]:
                del _sql_cache[k]

    # Building the Plotly figure is real CPU work (and the LanceDB write that
    # follows it is blocking I/O). Left on the event loop it stalled every
    # other in-flight request for the duration of each chart render.
    return await run_in_threadpool(
        _render_and_store, df, spec, user_prompt, session_id, sql, user_id, nid, workspace_id
    )


async def _repair_chart_sql(llm, sql, err, df, user_prompt, user_id, workspace_id):
    """Two recovery attempts, cheapest first: the deterministic fallback map,
    then one LLM repair with the actual error text. Returns (df, err, sql)."""
    fb = _fallback_sql(user_prompt, CHART_FALLBACK_SQL_MAP)
    if fb and fb != sql:
        fb_df, fb_err = await run_in_threadpool(data_loader.execute_sql, fb)
        if not fb_err and _is_df_usable(fb_df):
            return fb_df, None, fb

    fixed = await llm.agenerate(
        f"Fix this DuckDB SQL. Error: {err or 'query returned no rows'}\n"
        f"SQL: {sql}\nRequest: {user_prompt}\nReturn ONLY corrected SQL:",
        temperature=0.1, user_id=user_id, workspace_id=workspace_id,
    )
    if fixed:
        fixed_sql = _sanitize_sql(fixed)
        fixed_df, fixed_err = await run_in_threadpool(data_loader.execute_sql, fixed_sql)
        if not fixed_err and _is_df_usable(fixed_df):
            return fixed_df, None, fixed_sql

    return df, err, sql


def _render_and_store(df, spec, user_prompt, session_id, sql, user_id, ingestion_id, workspace_id):
    """Reconcile the requested form against the data that actually came back,
    render it, and persist. Reconciliation is what stops a 400-slice pie or a
    two-point 'trend' from ever reaching the user.

    Returns (chart_json, error, chart_id)."""
    try:
        spec = chart_spec_mod.reconcile(spec, df)
        fig, meta = chart_builder.build_figure(df, spec)
        chart_json = fig.to_json()
    except Exception as exc:
        logger.exception("Chart build failed for %r: %s", user_prompt[:80], exc)
        return None, f"Chart generation failed: {exc}", None

    # The store itself stays inline: its id is handed to the browser so the
    # gallery can show this figure immediately and still recognise it when the
    # history list catches up. The learning write has no such reader, so it
    # goes to the background rather than into the user's wait.
    chart_id = memory.store_chart(
        session_id,
        user_prompt,
        chart_json,
        {
            "sql": sql,
            "chart_type": spec.chart_type,
            "measure": meta.get("measure"),
            "dimension": meta.get("dimension"),
            "insight": meta.get("insight"),
        },
        user_id=user_id,
        ingestion_id=ingestion_id,
        workspace_id=workspace_id,
    )
    _persist_in_background(
        memory.learn_from_interaction,
        user_id, ingestion_id, session_id, workspace_id, user_prompt, chart_json,
        kind="chart",
    )
    return chart_json, None, chart_id
