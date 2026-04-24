"""
prompts.py — Centralized LLM prompt templates for chat and chart generation.
All prompts are schema-aware, concise, and validated for DuckDB + Plotly usage.
"""

# ---------------------------------------------------------------------------
# CHAT PROMPTS
# ---------------------------------------------------------------------------

CHAT_DECISION_PROMPT = """You are a precise QA analytics assistant. Analyze the user request and return ONLY valid JSON.

Available DuckDB tables:
- flattened_tests: test_name(varchar), status(varchar: passed|failed|skipped|pending|unknown), duration(float seconds), error(varchar), spec_file(varchar), build_id(varchar)
- test_cases: module_name(varchar), priority(varchar), title(varchar)
- JOIN condition: test_cases.title = flattened_tests.test_name

CONVERSATION HISTORY (last 10 turns):
{history}

CURRENT USER REQUEST: "{user_message}"

RELEASE DECISION LOGIC:
- pass_rate >= 95% AND no critical failures → GOOD FOR RELEASE
- pass_rate 80–94% → CONSIDER WITH CAUTION
- pass_rate < 80% → NOT READY FOR RELEASE

PROVEN SQL PATTERNS (use these exactly):
- count failed: SELECT COUNT(*) AS failed_count FROM flattened_tests WHERE status = 'failed'
- count passed: SELECT COUNT(*) AS passed_count FROM flattened_tests WHERE status = 'passed'
- pass rate: SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate FROM flattened_tests WHERE status IN ('passed','failed')
- status breakdown: SELECT status, COUNT(*) AS cnt FROM flattened_tests GROUP BY status ORDER BY cnt DESC
- all modules: SELECT DISTINCT module_name FROM test_cases ORDER BY module_name
- module test count: SELECT module_name, COUNT(*) AS test_count FROM test_cases GROUP BY module_name ORDER BY test_count DESC
- failed tests: SELECT test_name, error FROM flattened_tests WHERE status = 'failed' ORDER BY test_name LIMIT 50
- slowest tests: SELECT test_name, ROUND(duration, 2) AS duration_sec FROM flattened_tests WHERE duration IS NOT NULL ORDER BY duration DESC LIMIT 15
- tests in module X: SELECT ft.test_name, ft.status FROM test_cases tc JOIN flattened_tests ft ON tc.title = ft.test_name WHERE tc.module_name ILIKE '%X%' ORDER BY ft.test_name
- release check: SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate, COUNT(*) AS total, SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count FROM flattened_tests WHERE status IN ('passed','failed')

RULES:
1. For ANY data question → action="sql"
2. For greetings/meta questions → action="answer"
3. SQL must be valid DuckDB syntax
4. Never use window functions without proper syntax
5. Always use ILIKE for string matching

Return ONLY this JSON (no markdown, no explanation):
{{"action":"sql","data":"SELECT ..."}} OR {{"action":"answer","data":"plain text"}}"""


CHAT_ANSWER_PROMPT = """You are a concise QA analytics assistant. Answer the user's question directly using the provided data.

USER QUESTION: {user_message}

DATA ({row_count} rows):
{data_json}

RULES:
- Be direct and specific — no filler phrases like "based on the data" or "it appears"
- For single numbers: state the number with context (e.g. "📊 347 tests failed")
- For lists: numbered list, max 20 items shown
- For modules: list all with numbers
- For pass rate: include percentage + one-line verdict
- Use markdown formatting sparingly but effectively
- Keep response under 150 words unless listing items
- Never invent data not in the provided JSON

Answer:"""


CHAT_RELEASE_VERDICT = """📊 **Release Readiness Report**

**Pass Rate:** {pass_rate}% ({passed} passed / {total} executed)
**Failed Tests:** {failed_count}

**Verdict:** {verdict}

**Recommendation:** {recommendation}"""


# ---------------------------------------------------------------------------
# CHART PROMPTS
# ---------------------------------------------------------------------------

CHART_SQL_PROMPT = """You are a DuckDB SQL expert. Generate a single valid SQL query for the given chart request.

Available tables:
- flattened_tests: test_name(varchar), status(varchar: passed|failed|skipped|pending|unknown), duration(float seconds), error(varchar), spec_file(varchar), build_id(varchar)
- test_cases: module_name(varchar), priority(varchar), title(varchar)
- JOIN: test_cases.title = flattened_tests.test_name

USER REQUEST: "{user_prompt}"

PROVEN QUERY PATTERNS:
- status distribution: SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC
- passed vs failed pie: SELECT status, COUNT(*) AS count FROM flattened_tests WHERE status IN ('passed','failed') GROUP BY status
- failures by module: SELECT tc.module_name, COUNT(*) AS failure_count FROM test_cases tc JOIN flattened_tests ft ON tc.title = ft.test_name WHERE ft.status = 'failed' GROUP BY tc.module_name ORDER BY failure_count DESC LIMIT 15
- slowest tests bar: SELECT test_name, ROUND(duration, 2) AS duration_sec FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0 ORDER BY duration DESC LIMIT 10
- pass rate by module: SELECT tc.module_name, ROUND(SUM(CASE WHEN ft.status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 1) AS pass_rate, COUNT(*) AS total FROM test_cases tc JOIN flattened_tests ft ON tc.title = ft.test_name GROUP BY tc.module_name ORDER BY pass_rate ASC
- priority vs failures heatmap: SELECT tc.module_name, tc.priority, COUNT(*) AS failures FROM test_cases tc JOIN flattened_tests ft ON tc.title = ft.test_name WHERE ft.status = 'failed' GROUP BY tc.module_name, tc.priority
- duration histogram: SELECT CASE WHEN duration < 1 THEN '< 1s' WHEN duration < 5 THEN '1–5s' WHEN duration < 30 THEN '5–30s' WHEN duration < 60 THEN '30–60s' ELSE '> 60s' END AS bucket, COUNT(*) AS count FROM flattened_tests WHERE duration IS NOT NULL GROUP BY bucket ORDER BY MIN(duration)

RULES:
1. Return ONLY raw SQL — no markdown, no explanation, no semicolon
2. Use ILIKE for string matching, not LIKE
3. Limit results to 20 rows maximum for readability
4. Handle NULL values with IS NOT NULL checks
5. If request is impossible, return: SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status

SQL:"""


CHART_CODE_PROMPT = """You are a Plotly expert. Generate clean Python code to create a professional chart.

USER REQUEST: "{user_prompt}"
CHART TYPE HINT: {chart_type}

DATA (as Python dict list, use variable named `data`):
{data_sample}

COLUMNS AVAILABLE: {columns}

STRICT REQUIREMENTS:
1. Import ONLY: import plotly.express as px  OR  import plotly.graph_objects as go
2. Use `data` variable (already defined as list of dicts) — DO NOT redefine it
3. Convert to DataFrame if needed: import pandas as pd; df = pd.DataFrame(data)
4. Final figure MUST be stored in variable named `fig`
5. ALLOWED color scales: 'Viridis', 'RdYlGn', 'Blues', 'Reds', 'Plasma'
6. ALLOWED discrete colors: ['#60a5fa','#34d399','#f59e0b','#f87171','#a78bfa','#38bdf8']
7. FORBIDDEN: hovertemplate, customdata, piecolorway, Blues_d, Blues_r, width=, height=
8. Text on bars/pie slices: use textinfo or text_auto for readability
9. Font sizes: axis labels 12px, title 15px, tick labels 11px
10. For bar charts with long labels: fig.update_xaxes(tickangle=45)
11. For pie charts: use ONLY px.pie(df, names=..., values=..., title=...) — nothing else
12. ALWAYS end with this exact block:
fig.update_layout(
    template='plotly_dark',
    paper_bgcolor='rgba(15,15,15,0)',
    plot_bgcolor='rgba(15,15,15,0)',
    font=dict(family='monospace', color='#e2e8f0', size=12),
    title=dict(font=dict(size=15, color='#f1f5f9'), x=0.5, xanchor='center'),
    margin=dict(l=60, r=40, t=70, b=80),
    legend=dict(bgcolor='rgba(255,255,255,0.05)', bordercolor='rgba(255,255,255,0.1)', borderwidth=1),
    xaxis=dict(gridcolor='rgba(255,255,255,0.05)', linecolor='rgba(255,255,255,0.1)'),
    yaxis=dict(gridcolor='rgba(255,255,255,0.05)', linecolor='rgba(255,255,255,0.1)'),
)

CHART TYPE GUIDES:
- Bar chart: px.bar(df, x=..., y=..., title=..., color_discrete_sequence=['#60a5fa'], text_auto=True)
  Then: fig.update_traces(textfont_size=11, textangle=0, textposition='outside', cliponaxis=False)
- Pie chart: px.pie(df, names=..., values=..., title=..., color_discrete_sequence=[...])
  Then: fig.update_traces(textposition='inside', textinfo='percent+label', textfont_size=12)
- Heatmap: go.Figure(go.Heatmap(z=..., x=..., y=..., colorscale='Viridis', text=..., texttemplate='%{{text}}'))
- Line chart: px.line(df, x=..., y=..., title=..., markers=True, color_discrete_sequence=['#60a5fa'])
- Horizontal bar: px.bar(df, x=value_col, y=name_col, orientation='h', color_discrete_sequence=['#60a5fa'], text_auto=True)

Return ONLY Python code. No markdown fences. No explanation."""


# ---------------------------------------------------------------------------
# FALLBACK SQL MAP  (keyed by keyword patterns)
# ---------------------------------------------------------------------------

FALLBACK_SQL_MAP = {
    "how many.*fail": "SELECT COUNT(*) AS failed_count FROM flattened_tests WHERE status = 'failed'",
    "how many.*pass": "SELECT COUNT(*) AS passed_count FROM flattened_tests WHERE status = 'passed'",
    "pass rate|good for release|ready for release|release": (
        "SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count "
        "FROM flattened_tests WHERE status IN ('passed','failed')"
    ),
    "status|breakdown|distribution": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC"
    ),
    "module.*count|count.*module|number.*module": (
        "SELECT module_name, COUNT(*) AS test_count FROM test_cases GROUP BY module_name ORDER BY test_count DESC"
    ),
    "all.*module|list.*module|module.*list": (
        "SELECT DISTINCT module_name FROM test_cases ORDER BY module_name"
    ),
    "fail.*test|failed.*test|list.*fail": (
        "SELECT test_name, error FROM flattened_tests WHERE status = 'failed' ORDER BY test_name LIMIT 50"
    ),
    "slow|duration|longest": (
        "SELECT test_name, ROUND(duration, 2) AS duration_sec FROM flattened_tests "
        "WHERE duration IS NOT NULL AND duration > 0 ORDER BY duration DESC LIMIT 15"
    ),
    "how many.*skip|how many.*pending|skipped|pending": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests WHERE status IN ('skipped','pending') GROUP BY status"
    ),
    "tests.*took more than|longer than|greater than.*second|duration.*above": (
        "SELECT test_name, ROUND(duration, 2) AS duration_sec FROM flattened_tests "
        "WHERE duration IS NOT NULL AND duration > 30 ORDER BY duration DESC LIMIT 20"
    ),
}

CHART_FALLBACK_SQL_MAP = {
    "status|distribution|breakdown": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC"
    ),
    "pass.*fail|fail.*pass|pie": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests WHERE status IN ('passed','failed') GROUP BY status"
    ),
    "module.*fail|fail.*module|failures.*module": (
        "SELECT tc.module_name, COUNT(*) AS failure_count FROM test_cases tc "
        "JOIN flattened_tests ft ON tc.title = ft.test_name "
        "WHERE ft.status = 'failed' GROUP BY tc.module_name ORDER BY failure_count DESC LIMIT 15"
    ),
    "slow|duration|longest": (
        "SELECT test_name, ROUND(duration, 2) AS duration_sec FROM flattened_tests "
        "WHERE duration IS NOT NULL AND duration > 0 ORDER BY duration DESC LIMIT 10"
    ),
    "pass rate.*module|module.*pass rate": (
        "SELECT tc.module_name, ROUND(SUM(CASE WHEN ft.status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 1) AS pass_rate "
        "FROM test_cases tc JOIN flattened_tests ft ON tc.title = ft.test_name "
        "GROUP BY tc.module_name ORDER BY pass_rate ASC"
    ),
}