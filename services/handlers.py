import json
import re
import logging
from datetime import datetime
import pandas as pd
from . import config, data_loader, memory, llm_client

logger = logging.getLogger(__name__)

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

async def handle_chat(user_message: str, session_id: str):
    history = memory.get_chat_history(session_id, limit=config.MAX_HISTORY_TURNS)
    context = ""
    for h in reversed(history):
        role = h["type"]
        content = h["prompt"] if role == "user" else h["response"]
        context += f"{role.capitalize()}: {content}\n"

    schemas = data_loader.get_schema_info()
    schema_str = json.dumps(schemas, indent=2)

    decision_prompt = f"""You are a QA analytics assistant. Given the user request and available data, decide the best action.

Available tables and columns:
{schema_str}

**Rules:**
- Use `test_cases` table for questions about test case definitions (counts per module, test case details).
- Use `flattened_tests` table for questions about test execution results (pass/fail, duration, errors).
- For "how many tests in module X" -> SELECT COUNT(*) FROM test_cases WHERE module_name = '...'
- For "how many failed tests" -> SELECT COUNT(*) FROM flattened_tests WHERE status = 'failed'
- For "pass rate" -> SELECT SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END)*1.0/COUNT(*) FROM flattened_tests
- For "module with highest test count" -> SELECT module_name, COUNT(*) FROM test_cases GROUP BY module_name ORDER BY COUNT(*) DESC LIMIT 1
- For "failed/passed per module" you may need to join tables, but be careful.

User request: "{user_message}"
Conversation history:
{context}

Return a JSON object with exactly two keys:
- "action": one of "sql", "vector", "answer"
- "data": for "sql", provide a DuckDB SQL query; for "vector", provide a search query string; for "answer", provide the direct answer.

If using SQL, ensure the query is valid and returns only necessary columns. If the request cannot be answered, return "answer" with "I don't have enough information."

Output ONLY the JSON, no other text.
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
            answer_prompt = f"""Based on the following data, answer the user's request concisely and in a well‑formatted way.

User request: {user_message}

Data (as JSON):
{data_json}

Instructions:
- Use bullet points or numbered lists for multiple items.
- Add blank lines between sections.
- Use bold for key numbers (if possible with markdown).
- Keep the answer clear and scannable.
- If the data contains counts or statuses, present them in a table or list.
- Do not include extra commentary about formatting; just produce the formatted answer.

Provide the final answer:
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
            answer_prompt = f"""Using the following retrieved context, answer the user's question.

Context:
{context}

User question: {user_message}

Answer concisely and naturally.
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
    schemas = data_loader.get_schema_info()
    schema_str = json.dumps(schemas, indent=2)

    # Improved SQL prompt with explicit examples
    sql_prompt = f"""You are a data analyst. Generate a DuckDB SQL query to fetch the data needed for the chart described by the user.

Available tables and columns:
{schema_str}

**Important rules:**
- For "number of tests per module", use: SELECT module_name, COUNT(*) AS count FROM test_cases GROUP BY module_name ORDER BY module_name
- For test status distribution, use: SELECT status, COUNT(*) FROM flattened_tests GROUP BY status
- For pass rate over time, use: SELECT executed_at, SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END)*1.0/COUNT(*) as pass_rate FROM flattened_tests GROUP BY executed_at ORDER BY executed_at
- If the user asks for a line chart but the x-axis is categorical (like module names), it's still acceptable to use a line chart with those categories.
- Return only the SQL query, no explanation. If the request cannot be answered, return "N/A".

User request: "{user_prompt}"
"""
    llm = llm_client.LLMClient()
    sql = llm.generate(sql_prompt, temperature=0.1)
    logger.info(f"Generated SQL for chart: {sql}")
    if not sql or sql.strip() == "N/A":
        return None, "Could not determine data for chart"

    sql = re.sub(r"```sql\n?|```", "", sql).strip()
    df, sql_error = data_loader.execute_sql(sql)
    if sql_error:
        logger.error(f"SQL error: {sql_error}")
        return None, f"SQL error: {sql_error}"
    
    # FALLBACK: If empty result and request is about module counts, try known query
    if df.empty:
        logger.warning(f"Empty result for SQL: {sql}")
        if "module" in user_prompt.lower() and ("count" in user_prompt.lower() or "number" in user_prompt.lower()):
            fallback_sql = "SELECT module_name, COUNT(*) AS count FROM test_cases GROUP BY module_name ORDER BY module_name"
            df, fallback_error = data_loader.execute_sql(fallback_sql)
            if fallback_error:
                logger.error(f"Fallback SQL error: {fallback_error}")
                return None, "No data found for chart"
            if df.empty:
                return None, "No data found for chart"
            logger.info("Using fallback SQL for module counts")
        else:
            return None, "No data found for chart"

    # Convert DataFrame to serializable dict, handling timestamps
    data_sample = df.head(100).to_dict(orient="records")
    data_sample_serializable = _convert_timestamp(data_sample)
    chart_prompt = f"""You are a data visualization expert. Generate a Plotly Python code that creates the chart described.

User request: "{user_prompt}"

Data (first 100 rows):
{json.dumps(data_sample_serializable, indent=2)}

Return only the Python code, no explanation. The code should define a variable `fig` containing the Plotly figure. Use `import plotly.graph_objects as go` or `plotly.express as px`. Ensure the code is self‑contained and uses the data provided.

Example for line chart:
import plotly.express as px
fig = px.line(data, x='module_name', y='count', title='Tests per Module')
"""
    code = llm.generate(chart_prompt, temperature=0.2)
    if not code:
        return None, "Chart generation failed"

    code = re.sub(r"```python\n?|```", "", code).strip()
    try:
        logger.info(f"Chart code execution - generated code length: {len(code)}")
        import plotly.express as px
        import plotly.graph_objects as go
        namespace = {"px": px, "go": go, "data": df, "pd": pd}
        exec(code, namespace)
        fig = namespace.get("fig")
        logger.info(f"Fig object: {fig}")
        if fig is None:
            raise ValueError("No 'fig' variable defined")
        chart_json = fig.to_json()
        logger.info(f"Chart JSON length: {len(chart_json)}")
        # Store chart
        result = memory.store_chart(session_id, user_prompt, chart_json, {"sql": sql})
        logger.info(f"store_chart returned: {result}")
        return chart_json, None
    except Exception as e:
        logger.error(f"Chart code execution error: {e}")
        import traceback
        traceback.print_exc()
        return None, f"Chart generation execution failed: {str(e)}"