import json
import re
import logging
from datetime import datetime
import pandas as pd
from . import config, data_loader, memory, llm_client

logger = logging.getLogger(__name__)

_sql_cache = {}

def _convert_timestamp(obj):
    if isinstance(obj, dict):
        return {k: _convert_timestamp(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_timestamp(item) for item in obj]
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

def _get_schema_with_samples():
    """Return schema including sample distinct values for key columns."""
    if not data_loader.state.duck_conn:
        return {}
    tables = data_loader.state.duck_conn.execute("SHOW TABLES").fetchall()
    schema = {}
    for (tbl,) in tables:
        cols = data_loader.state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
        col_info = []
        for col_name, col_type, _, _, _, _ in cols:
            samples = []
            if "varchar" in col_type.lower() or "text" in col_type.lower():
                try:
                    samples = data_loader.state.duck_conn.execute(f"SELECT DISTINCT {col_name} FROM {tbl} LIMIT 5").fetchall()
                    samples = [s[0] for s in samples if s[0] is not None]
                except:
                    pass
            col_info.append({"name": col_name, "type": col_type, "sample_values": samples})
        schema[tbl] = col_info
    return schema

async def handle_chat(user_message: str, session_id: str):
    history = memory.get_chat_history(session_id, limit=config.MAX_HISTORY_TURNS)
    context = ""
    for h in reversed(history):
        role = h["type"]
        content = h["prompt"] if role == "user" else h["response"]
        context += f"{role.capitalize()}: {content}\n"

    schemas = _get_schema_with_samples()
    schema_str = json.dumps(schemas, indent=2)

    decision_prompt = f"""You are a QA analytics assistant. Given the user request and available data, decide the best action.

Available tables and columns (with sample values):
{schema_str}

**Rules:**
- Use `test_cases` for test case definitions (module_name, priority, title).
- Use `flattened_tests` for test execution results (status, duration, error, test_name).
- To join test_cases with flattened_tests, use: test_cases.title = flattened_tests.test_name
- For "priority vs failure count", join and group by priority.
- For "how many tests in module X" -> SELECT COUNT(*) FROM test_cases WHERE module_name = '...'
- For pass rate -> SELECT SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END)*1.0/COUNT(*) FROM flattened_tests

User request: "{user_message}"
Conversation history:
{context}

Return a JSON object with exactly two keys:
- "action": one of "sql", "vector", "answer"
- "data": for "sql", provide a DuckDB SQL query; for "vector", provide a search query string; for "answer", provide the direct answer.

Output ONLY the JSON.
"""
    llm = llm_client.LLMClient()
    decision_str = llm.generate(decision_prompt, temperature=0.1)
    if not decision_str:
        return "I'm having trouble processing your request."

    cleaned = re.sub(r'```json\s*', '', decision_str)
    cleaned = re.sub(r'```\s*', '', cleaned)
    decision_str = cleaned.strip()

    try:
        decision = json.loads(decision_str)
    except Exception as e:
        decision = {"action": "answer", "data": "I couldn't understand your request."}

    action = decision.get("action")
    data = decision.get("data")

    if action == "sql":
        df, sql_error = data_loader.execute_sql(data)
        if sql_error:
            response = f"SQL error: {sql_error}"
        elif df.empty:
            response = "No data found for your request."
        else:
            df_copy = df.copy()
            for col in df_copy.select_dtypes(include=['datetime64']).columns:
                df_copy[col] = df_copy[col].dt.isoformat()
            data_json = df_copy.head(100).to_json(orient="records")
            answer_prompt = f"""Based on the following data, answer the user's request concisely and well‑formatted.

User request: {user_message}

Data (as JSON):
{data_json}

Use bullet points or markdown tables. Provide final answer.
"""
            response = llm.generate(answer_prompt, temperature=0.2)
            if not response:
                response = f"Found {len(df)} rows, but could not generate a summary."
    elif action == "vector":
        docs = data_loader.vector_search(data, top_k=5)
        if not docs:
            response = "I couldn't find relevant information."
        else:
            context = "\n\n".join([d["text"][:500] for d in docs])
            answer_prompt = f"""Using the retrieved context, answer the user's question.

Context:
{context}

User question: {user_message}

Answer concisely.
"""
            response = llm.generate(answer_prompt, temperature=0.2)
            if not response:
                response = "I found some information but couldn't generate a response."
    else:
        response = data

    memory.store_chat_message(session_id, "user", user_message)
    memory.store_chat_message(session_id, "assistant", response)
    return response

async def handle_chart(user_prompt: str, session_id: str):
    cache_key = user_prompt.lower().strip()
    if cache_key in _sql_cache:
        cached = _sql_cache[cache_key]
        logger.info(f"Using cached SQL for '{cache_key}'")
        df, err = data_loader.execute_sql(cached)
        if not err and not df.empty:
            return _generate_chart_from_df(df, user_prompt, session_id, cached)

    schemas = _get_schema_with_samples()
    schema_str = json.dumps(schemas, indent=2)

    sql_prompt = f"""You are a data analyst. Generate a DuckDB SQL query.

Available tables and columns (with samples):
{schema_str}

**Join instructions:**
- To join test_cases and flattened_tests, use: test_cases.title = flattened_tests.test_name
- For "priority vs failure count": 
    SELECT tc.priority, COUNT(ft.status) as failure_count
    FROM test_cases tc
    JOIN flattened_tests ft ON tc.title = ft.test_name
    WHERE ft.status = 'failed'
    GROUP BY tc.priority
- For heatmap: SELECT tc.module_name, tc.priority, COUNT(ft.status) as failures
  FROM test_cases tc
  JOIN flattened_tests ft ON tc.title = ft.test_name
  WHERE ft.status = 'failed'
  GROUP BY tc.module_name, tc.priority
- For pass rate per module: SELECT tc.module_name, 
    SUM(CASE WHEN ft.status='passed' THEN 1 ELSE 0 END)*1.0/COUNT(*) as pass_rate
  FROM test_cases tc
  JOIN flattened_tests ft ON tc.title = ft.test_name
  GROUP BY tc.module_name

User request: "{user_prompt}"

Return only SQL. If impossible, return "N/A".
"""
    llm = llm_client.LLMClient()
    sql = llm.generate(sql_prompt, temperature=0.1)
    logger.info(f"Generated SQL for chart: {sql}")
    if not sql or sql.strip() == "N/A":
        return None, "Could not determine data for chart"

    sql = re.sub(r"```sql\n?|```", "", sql).strip()
    df, sql_error = data_loader.execute_sql(sql)

    max_retries = 2
    for attempt in range(max_retries):
        if sql_error or df.empty:
            correction_prompt = f"""The previous SQL query failed.
Error: {sql_error or 'Empty result'}
Original request: {user_prompt}
Attempted SQL: {sql}
Please provide a corrected DuckDB SQL query that will return non-empty data.
Use the correct join: test_cases.title = flattened_tests.test_name
Return only SQL.
"""
            corrected_sql = llm.generate(correction_prompt, temperature=0.2)
            if corrected_sql:
                corrected_sql = re.sub(r"```sql\n?|```", "", corrected_sql).strip()
                df, sql_error = data_loader.execute_sql(corrected_sql)
                sql = corrected_sql
                logger.info(f"Retry {attempt+1}: using corrected SQL")
            else:
                break
        else:
            break

    if sql_error:
        logger.error(f"SQL error after retries: {sql_error}")
        return None, f"SQL error: {sql_error}"
    if df.empty:
        return None, "No data found for chart"

    _sql_cache[cache_key] = sql
    if len(_sql_cache) > 100:
        for k in list(_sql_cache.keys())[:20]:
            del _sql_cache[k]

    return _generate_chart_from_df(df, user_prompt, session_id, sql)

def _generate_chart_from_df(df: pd.DataFrame, user_prompt: str, session_id: str, sql: str):
    data_sample = df.head(100).to_dict(orient="records")
    data_sample_serializable = _convert_timestamp(data_sample)

    is_heatmap = 'heatmap' in user_prompt.lower()
    chart_type_hint = ""
    if is_heatmap:
        chart_type_hint = """
Use plotly.express.density_heatmap or plotly.graph_objects.Heatmap.
Example:
import plotly.express as px
fig = px.density_heatmap(data, x='module_name', y='priority', z='failures', title='Risk Heatmap')
"""
    else:
        chart_type_hint = """
Example for scatter:
import plotly.express as px
fig = px.scatter(data, x='priority', y='failure_count', title='Priority vs Failures')
"""

    chart_prompt = f"""Generate Plotly Python code for the chart described.

User request: "{user_prompt}"

Data (first 100 rows):
{json.dumps(data_sample_serializable, indent=2)}

Return only Python code. Define variable `fig`. Use plotly.express or plotly.graph_objects.
{chart_type_hint}
"""
    llm = llm_client.LLMClient()
    code = llm.generate(chart_prompt, temperature=0.2)
    if not code:
        return None, "Chart generation failed"

    code = re.sub(r"```python\n?|```", "", code).strip()
    try:
        logger.info(f"Chart code execution - length: {len(code)}")
        import plotly.express as px
        import plotly.graph_objects as go
        namespace = {"px": px, "go": go, "data": df, "pd": pd}
        exec(code, namespace)
        fig = namespace.get("fig")
        if fig is None:
            raise ValueError("No 'fig' variable defined")
        chart_json = fig.to_json()
        logger.info(f"Chart JSON length: {len(chart_json)}")
        result = memory.store_chart(session_id, user_prompt, chart_json, {"sql": sql})
        logger.info(f"store_chart returned: {result}")
        return chart_json, None
    except Exception as e:
        logger.error(f"Chart code execution error: {e}")
        import traceback
        traceback.print_exc()
        return None, f"Chart generation failed: {str(e)}"