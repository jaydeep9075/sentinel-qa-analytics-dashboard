import json
import re
import logging
from datetime import datetime
import pandas as pd
from . import config, data_loader, memory, llm_client, state
from .project_manager import ProjectManager
from .role_manager import RoleManager

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
    if not state.duck_conn:
        return {}
    tables = state.duck_conn.execute("SHOW TABLES").fetchall()
    schema = {}
    for (tbl,) in tables:
        cols = state.duck_conn.execute(f"DESCRIBE {tbl}").fetchall()
        col_info = []
        for col_name, col_type, _, _, _, _ in cols:
            samples = []
            if "varchar" in col_type.lower() or "text" in col_type.lower():
                try:
                    samples = state.duck_conn.execute(f"SELECT DISTINCT {col_name} FROM {tbl} LIMIT 5").fetchall()
                    samples = [s[0] for s in samples if s[0] is not None]
                except:
                    pass
            col_info.append({"name": col_name, "type": col_type, "sample_values": samples})
        schema[tbl] = col_info
    return schema

async def handle_chat(user_message: str, session_id: str, ingestion_id: str,
                      role: str = None, project_id: str = None):
    # Ensure data for this ingestion is loaded
    if state.current_ingestion_id != ingestion_id:
        if not data_loader.init_data(ingestion_id):
            return f"Error: Ingestion '{ingestion_id}' not found or data unavailable."

    # Initialize RBA managers if needed
    if state.project_manager is None:
        state.project_manager = ProjectManager()
    if state.role_manager is None:
        state.role_manager = RoleManager()

    # Retrieve project context (only relevant sections)
    project_context = ""
    if project_id:
        project_context = state.project_manager.retrieve_relevant_context(project_id, user_message)

    # Load role instruction
    role_instruction = ""
    if role:
        role_instruction = state.role_manager.get_role_instruction(role)
    if not role_instruction:
        role_instruction = "You are a helpful QA analytics assistant. Provide clear, concise answers."

    # Build system prompt for the decision phase (kept short)
    system_context = f"{role_instruction}\n\n"
    if project_id:
        system_context += f"Project: {project_id}\n"
    if project_context:
        system_context += f"Relevant project knowledge:\n{project_context}\n"

    # Get conversation history
    history = memory.get_chat_history(session_id, limit=config.MAX_HISTORY_TURNS)
    context = ""
    for h in reversed(history[-5:]):
        role_label = h["type"]
        content = h["prompt"] if role_label == "user" else h["response"]
        context += f"{role_label.capitalize()}: {content}\n"

    schemas = _get_schema_with_samples()
    schema_str = json.dumps(schemas, indent=2)

    # --------------------------------------------------------------
    # Decision prompt (copied from working version)
    # --------------------------------------------------------------
    decision_prompt = f"""{system_context}

You are a QA analytics assistant. Analyze the user request and return JSON.

Available tables:
- test_cases: module_name, priority, title
- flattened_tests: status, duration, error, test_name
Join: test_cases.title = flattened_tests.test_name

**PREVIOUS CONVERSATION:**
{context}

**CURRENT USER REQUEST:** "{user_message}"

**BUSINESS LOGIC RULES FOR RELEASE DECISIONS:**
When user asks "is this good for release" or similar:
1. Calculate pass rate = (passed / total) * 100
2. Check critical failures count
3. Provide verdict based on:
   - Pass rate >= 95% AND no critical failures → "✅ GOOD FOR RELEASE"
   - Pass rate >= 80% AND < 95% → "⚠️ CONSIDER WITH CAUTION"  
   - Pass rate < 80% OR any critical failures → "❌ NOT READY FOR RELEASE"

**SQL QUERY PATTERNS (USE THESE EXACT PATTERNS):**
- "how many tests failed" → SELECT COUNT(*) FROM flattened_tests WHERE status='failed'
- "how many tests passed" → SELECT COUNT(*) FROM flattened_tests WHERE status='passed'
- "pass rate" → SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END)*100.0/COUNT(*), 2) as pass_rate FROM flattened_tests
- "list all modules" → SELECT DISTINCT module_name FROM test_cases ORDER BY module_name
- "number of modules" → SELECT COUNT(DISTINCT module_name) as module_count FROM test_cases
- "module with most tests" → SELECT module_name, COUNT(*) as test_count FROM test_cases GROUP BY module_name ORDER BY test_count DESC LIMIT 1
- "failed tests list" → SELECT test_name, error FROM flattened_tests WHERE status='failed' LIMIT 10
- "list all tests in module X" → SELECT title FROM test_cases WHERE module_name = 'X' ORDER BY title

**IMPORTANT RULES:**
1. For ANY question about data (counts, lists, modules, failures), use action="sql"
2. For release readiness questions, use action="sql" to get metrics first
3. For follow-up questions (like "what about X module"), use action="sql" with module filter
4. Only use "answer" for greetings or when no data needed

Return JSON: {{"action":"sql","data":"SQL_QUERY"}} or {{"action":"answer","data":"text"}}
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
        if "SELECT" in decision_str.upper():
            decision = {"action": "sql", "data": decision_str}
        else:
            decision = {"action": "answer", "data": "I couldn't understand your request."}

    action = decision.get("action")
    data = decision.get("data")

    # --------------------------------------------------------------
    # SQL execution and answer generation (working logic)
    # --------------------------------------------------------------
    if action == "sql" or (action == "answer" and "SELECT" in data.upper()):
        if "SELECT" in data.upper():
            action = "sql"
        df, sql_error = data_loader.execute_sql(data)
        # Retry with hardcoded fallbacks for common queries (same as original)
        if sql_error and "how many tests failed" in user_message.lower():
            data = "SELECT COUNT(*) FROM flattened_tests WHERE status='failed'"
            df, sql_error = data_loader.execute_sql(data)
        elif sql_error and "how many tests passed" in user_message.lower():
            data = "SELECT COUNT(*) FROM flattened_tests WHERE status='passed'"
            df, sql_error = data_loader.execute_sql(data)
        elif sql_error and "pass rate" in user_message.lower():
            data = "SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END)*100.0/COUNT(*), 2) as pass_rate FROM flattened_tests"
            df, sql_error = data_loader.execute_sql(data)
        if sql_error:
            response = f"SQL error: {sql_error}"
        elif df.empty:
            response = "No data found for your request."
        else:
            df_copy = df.copy()
            for col in df_copy.select_dtypes(include=['datetime64']).columns:
                df_copy[col] = df_copy[col].dt.isoformat()
            data_json = df_copy.head(50).to_json(orient="records")
            is_release_question = any(phrase in user_message.lower() for phrase in ['release', 'good to go', 'ready for'])
            if is_release_question and 'pass_rate' in df.columns:
                pass_rate = df.iloc[0]['pass_rate']
                if pass_rate >= 95:
                    verdict = "✅ GOOD FOR RELEASE"
                    recommendation = "Quality meets release criteria. Proceed with deployment."
                elif pass_rate >= 80:
                    verdict = "⚠️ CONSIDER WITH CAUTION"
                    recommendation = f"Pass rate is {pass_rate}%. Review failures before release."
                else:
                    verdict = "❌ NOT READY FOR RELEASE"
                    recommendation = f"Pass rate is only {pass_rate}%. Fix critical issues before release."
                response = f"""📊 **Release Readiness Report**

**Pass Rate:** {pass_rate}%

**Verdict:** {verdict}

**Recommendation:** {recommendation}"""
            else:
                # Use the system context (role + project) in the answer prompt
                answer_prompt = f"""{system_context}

Based on the data, answer the user's request.

User request: {user_message}

Data (as JSON):
{data_json}

Total rows: {len(df)}

**RESPONSE FORMAT RULES:**
- For counts: "📊 [description]: [number]"
- For lists: Use numbered list (1., 2., 3.)
- For modules: List all with numbers
- For test names in a module: List each test name with a number
- For pass rate: Include percentage and brief assessment
- Be direct and specific. Don't say "based on the data"

Provide final answer:
"""
                response = llm.generate(answer_prompt, temperature=0.2)
                if not response:
                    # Fallback formatting (same as original)
                    if len(df) == 1 and len(df.columns) == 1:
                        response = f"📊 Result: {df.iloc[0, 0]}"
                    elif 'module_name' in df.columns and len(df.columns) == 1:
                        modules = "\n".join([f"{i+1}. {row['module_name']}" for i, row in df.iterrows()])
                        response = f"📁 **Modules:**\n{modules}"
                    elif 'title' in df.columns:
                        tests = "\n".join([f"{i+1}. {row['title']}" for i, row in df.iterrows()])
                        response = f"📋 **Tests in module:**\n{tests}"
                    elif 'test_name' in df.columns:
                        tests = "\n".join([f"{i+1}. {row['test_name']}" for i, row in df.iterrows()])
                        response = f"📋 **Failed Tests:**\n{tests}"
                    else:
                        response = f"Found {len(df)} rows matching your request."
    elif action == "vector":
        docs = data_loader.vector_search(data, top_k=5)
        if not docs:
            response = "I couldn't find relevant information."
        else:
            context_docs = "\n\n".join([d["text"][:500] for d in docs])
            answer_prompt = f"""{system_context}

Using the retrieved context, answer the user's question.

Context:
{context_docs}

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

# --------------------------------------------------------------
# Chart generation (unchanged from working version, but with RBA)
# --------------------------------------------------------------
async def handle_chart(user_prompt: str, session_id: str, ingestion_id: str,
                       role: str = None, project_id: str = None):
    if state.current_ingestion_id != ingestion_id:
        if not data_loader.init_data(ingestion_id):
            return None, f"Error: Ingestion '{ingestion_id}' not found."

    # Initialize RBA managers for chart context (optional)
    if state.project_manager is None:
        state.project_manager = ProjectManager()
    if state.role_manager is None:
        state.role_manager = RoleManager()

    project_context = ""
    if project_id:
        project_context = state.project_manager.retrieve_relevant_context(project_id, user_prompt)

    role_instruction = ""
    if role:
        role_instruction = state.role_manager.get_role_instruction(role)
    if not role_instruction:
        role_instruction = "You are a data analyst."

    system_context = f"{role_instruction}\n\n"
    if project_id:
        system_context += f"Project: {project_id}\n"
    if project_context:
        system_context += f"Relevant project knowledge:\n{project_context}\n"

    cache_key = user_prompt.lower().strip()
    if cache_key in _sql_cache:
        cached = _sql_cache[cache_key]
        logger.info(f"Using cached SQL for '{cache_key}'")
        df, err = data_loader.execute_sql(cached)
        if not err and not df.empty:
            return _generate_chart_from_df(df, user_prompt, session_id, cached, system_context)

    schemas = _get_schema_with_samples()
    schema_str = json.dumps(schemas, indent=2)

    sql_prompt = f"""{system_context}

You are a data analyst. Generate a DuckDB SQL query.

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
            correction_prompt = f"""{system_context}

The previous SQL query failed.
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

    return _generate_chart_from_df(df, user_prompt, session_id, sql, system_context)

def _detect_chart_type(prompt: str) -> str:
    prompt_lower = prompt.lower()
    if "line" in prompt_lower or "trend" in prompt_lower or "over time" in prompt_lower:
        return "line"
    elif "pie" in prompt_lower or "distribution" in prompt_lower or "percentage" in prompt_lower:
        return "pie"
    elif "heatmap" in prompt_lower or "matrix" in prompt_lower:
        return "heatmap"
    elif "bar" in prompt_lower or "top" in prompt_lower:
        return "bar"
    else:
        return "auto"

def _generate_chart_from_df(df: pd.DataFrame, user_prompt: str, session_id: str, sql: str, system_context: str = ""):
    if df.empty:
        return None, "No data available for chart"
    chart_type = _detect_chart_type(user_prompt)
    if chart_type == "pie" and len(df.columns) < 2:
        return None, "Pie chart requires at least 2 columns (category and value)"
    elif chart_type == "line" and len(df) < 2:
        return None, "Line chart requires at least 2 data points"
    df = df.dropna()
    if df.empty:
        return None, "Data contains only null values"
    data_sample = df.head(100).to_dict(orient="records")
    data_sample_serializable = _convert_timestamp(data_sample)

    is_heatmap = 'heatmap' in user_prompt.lower()
    chart_type_hint = ""
    if is_heatmap:
        chart_type_hint = """
Use plotly.express.density_heatmap or plotly.graph_objects.Heatmap.
Example:
import plotly.express as px
fig = px.density_heatmap(data, x='module_name', y='priority', z='failures', 
                         title='Risk Heatmap',
                         color_continuous_scale='Viridis')
fig.update_layout(template='plotly_dark', title_x=0.5)
"""
    else:
        chart_type_hint = """
Example for bar chart:
import plotly.express as px
fig = px.bar(data, x='module_name', y='failure_count', 
             title='Failures by Module',
             color_discrete_sequence=['#3b82f6'])
fig.update_layout(template='plotly_dark', title_x=0.5)
"""

    chart_prompt = f"""{system_context}

Generate Plotly Python code for a professional chart as described.

User request: "{user_prompt}"

Data (first 100 rows):
{json.dumps(data_sample_serializable, indent=2)}

STRICT REQUIREMENTS:
1. Use plotly.express (px) for simplicity
2. ALWAYS set title, xaxis_title, yaxis_title
3. For bar charts: use px.bar()
4. For line charts: use px.line()
5. For pie charts: use px.pie() with ONLY: names, values, title, hole
6. For heatmaps: use px.density_heatmap()
7. For colors, use ONLY: 'Viridis', 'Blues', 'Set2', or color_discrete_sequence=['#3b82f6']
8. Format numbers with commas for thousands
9. Rotate x-axis labels if needed (tickangle=45)
10. DO NOT use: 'Blues_d', 'Blues_r', hovertemplate, customdata
11. ALWAYS add: fig.update_layout(template='plotly_dark', title_x=0.5)

Example format:
```python
import plotly.express as px
fig = px.bar(data, x='module_name', y='failure_count', 
             title='Failures by Module',
             labels={{'module_name': 'Module Name', 'failure_count': 'Number of Failures'}},
             color_discrete_sequence=['#3b82f6'])
fig.update_layout(template='plotly_dark', title_x=0.5)

Return only Python code. Define variable `fig`.
{chart_type_hint}
"""
    llm = llm_client.LLMClient()
    code = llm.generate(chart_prompt, temperature=0.4)
    if not code:
        return None, "Chart generation failed"

    code = re.sub(r"```python\n?|```", "", code).strip()
    
    code = re.sub(r"'Blues_d'", "'Blues'", code)
    code = re.sub(r'"Blues_d"', '"Blues"', code)
    code = re.sub(r"'Blues_r'", "'Blues'", code)
    code = re.sub(r'"Blues_r"', '"Blues"', code)
    
    if 'pie' in code.lower():
        code = re.sub(r',\s*hovertemplate\s*=\s*[^,)]+', '', code)
        code = re.sub(r'hovertemplate\s*=\s*[^,)]+,\s*', '', code)
        code = re.sub(r',\s*customdata\s*=\s*[^,)]+', '', code)
        code = re.sub(r'customdata\s*=\s*[^,)]+,\s*', '', code)
    
    if "template='plotly_dark'" not in code and 'template="plotly_dark"' not in code:
        if "fig.update_layout(" in code:
            code = code.replace("fig.update_layout(", "fig.update_layout(template='plotly_dark', ")
        else:
            code += "\nfig.update_layout(template='plotly_dark')"
    
    code = re.sub(r',?\s*width\s*=\s*\d+\s*,?', '', code)
    code = re.sub(r',?\s*height\s*=\s*\d+\s*,?', '', code)
    
    try:
        logger.info(f"Chart code execution - length: {len(code)}")
        import plotly.express as px
        import plotly.graph_objects as go
        namespace = {"px": px, "go": go, "data": df, "pd": pd}
        exec(code, namespace)
        fig = namespace.get("fig")
        if fig is None:
            raise ValueError("No 'fig' variable defined")
        
        fig.update_layout(
            template='plotly_dark',
            autosize=True,
            margin=dict(l=40, r=40, t=50, b=40),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e5e7eb')
        )
        
        if not fig.layout.title or not fig.layout.title.text:
            fig.update_layout(title=user_prompt[:50])
        
        if hasattr(fig, 'layout') and hasattr(fig.layout, 'xaxis'):
            if not fig.layout.xaxis.title.text:
                fig.update_xaxes(title_text=df.columns[0] if len(df.columns) > 0 else "X Axis")
            fig.update_xaxes(title_font=dict(color='#9ca3af'), tickfont=dict(color='#9ca3af'))
        
        if hasattr(fig, 'layout') and hasattr(fig.layout, 'yaxis'):
            if not fig.layout.yaxis.title.text:
                fig.update_yaxes(title_text=df.columns[1] if len(df.columns) > 1 else "Y Axis")
            fig.update_yaxes(title_font=dict(color='#9ca3af'), tickfont=dict(color='#9ca3af'))
        
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