"""
prompts.py — LLM prompts for chat and chart generation.

KEY FIX: Chart type is now STRICTLY enforced via a dedicated per-type code template.
The LLM receives the exact Plotly pattern it must use — no room to substitute chart types.

Schema:
  flattened_tests:
    test_name, status (passed|failed|skipped|pending|unknown),
    duration FLOAT (seconds), error, spec_file,
    project_name (FSA|HSA|WDH|unknown),
    module_name  ("Eligibility Tests"|"Checkout Tests"|"Cart Tests"|…),
    platform_type (desktop|mobile),
    browser  ("GoogleChrome"|"GoogleChromeiPhoneX"|"GoogleChromeiPad"|…)

  module_metrics:
    project_name, module_name, platform_type,
    total_tests, passed, failed, skipped, pending, unknown,
    pass_rate FLOAT, total_duration_seconds FLOAT, avg_duration_seconds FLOAT

  project_metrics:
    project_name, platform_type, module_count,
    total_tests, passed, failed, skipped, pending, unknown,
    pass_rate FLOAT, total_duration_seconds FLOAT, avg_duration_seconds FLOAT

  test_cases:
    module_name, priority, title (= test_name), project_name, platform_type
"""

# ---------------------------------------------------------------------------
# CHAT – DECISION PROMPT
# ---------------------------------------------------------------------------

CHAT_DECISION_PROMPT = """You are a precise QA analytics assistant. Return ONLY valid JSON for the action to take.

=== AVAILABLE DUCKDB TABLES ===

flattened_tests:
  test_name     VARCHAR   – full test identifier
  status        VARCHAR   – passed | failed | skipped | pending | unknown
  duration      FLOAT     – seconds
  error         VARCHAR   – failure message
  spec_file     VARCHAR
  project_name  VARCHAR   – FSA | HSA | WDH | unknown
  module_name   VARCHAR   – "Eligibility Tests" | "Checkout Tests" | "Cart Tests" |
                            "Catalog/Products Tests" | "My Account Tests" |
                            "Sign-up/Registration Tests" | "FSA Perks Tests" |
                            "Eligibility TPA Tests" | "Expense Dashboard Tests" |
                            "Split Payment Tests" | …
  platform_type VARCHAR   – desktop | mobile
  browser       VARCHAR   – "GoogleChrome" | "GoogleChromeiPhoneX" | "GoogleChromeiPad" | …

module_metrics:
  project_name, module_name, platform_type,
  total_tests INT, passed INT, failed INT, skipped INT, pending INT, unknown INT,
  pass_rate FLOAT, total_duration_seconds FLOAT, avg_duration_seconds FLOAT

project_metrics:
  project_name, platform_type, module_count INT,
  total_tests INT, passed INT, failed INT, skipped INT, pending INT, unknown INT,
  pass_rate FLOAT, total_duration_seconds FLOAT, avg_duration_seconds FLOAT

test_cases:
  module_name, priority, title (= test_name), project_name, platform_type

JOINs:
  test_cases.title = flattened_tests.test_name
  module_metrics.module_name = flattened_tests.module_name
    AND module_metrics.project_name = flattened_tests.project_name
    AND module_metrics.platform_type = flattened_tests.platform_type

=== PLATFORM RULES ===
• platform_type = 'mobile'   → iPhone/iPad/Android simulation
• platform_type = 'desktop'  → standard Chrome browser
• browser column holds exact value, e.g. "GoogleChromeiPhoneX"
• Mobile filter: WHERE platform_type = 'mobile'
• iPhone filter: WHERE browser ILIKE '%iphone%'
• Desktop filter: WHERE platform_type = 'desktop'

=== CONVERSATION HISTORY (last 20 turns) ===
{history}

=== CURRENT USER REQUEST ===
"{user_message}"

=== RELEASE DECISION LOGIC ===
pass_rate >= 95% → GOOD FOR RELEASE
pass_rate 80–94% → CONSIDER WITH CAUTION
pass_rate < 80%  → NOT READY FOR RELEASE

=== PROVEN SQL PATTERNS ===

-- overall counts
SELECT COUNT(*) AS total FROM flattened_tests
SELECT COUNT(*) AS failed_count FROM flattened_tests WHERE status = 'failed'

-- pass rate
SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate,
       COUNT(*) AS total,
       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count
FROM flattened_tests WHERE status IN ('passed','failed')

-- status breakdown
SELECT status, COUNT(*) AS cnt FROM flattened_tests GROUP BY status ORDER BY cnt DESC

-- mobile vs desktop
SELECT platform_type, COUNT(*) AS total,
       SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS passed,
       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
       ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate
FROM flattened_tests GROUP BY platform_type ORDER BY platform_type

-- failed tests on mobile only
SELECT test_name, project_name, module_name, error
FROM flattened_tests WHERE status = 'failed' AND platform_type = 'mobile'
ORDER BY project_name, module_name

-- failed tests on desktop only
SELECT test_name, project_name, module_name, error
FROM flattened_tests WHERE status = 'failed' AND platform_type = 'desktop'
ORDER BY project_name, module_name

-- failed only on mobile (passed on desktop)
SELECT m.test_name, m.project_name, m.module_name, m.error AS mobile_error
FROM flattened_tests m
JOIN flattened_tests d ON m.test_name = d.test_name
WHERE m.platform_type = 'mobile' AND m.status = 'failed'
  AND d.platform_type = 'desktop' AND d.status = 'passed'
ORDER BY m.project_name, m.module_name

-- failed only on desktop (passed on mobile)
SELECT d.test_name, d.project_name, d.module_name, d.error AS desktop_error
FROM flattened_tests d
JOIN flattened_tests m ON d.test_name = m.test_name
WHERE d.platform_type = 'desktop' AND d.status = 'failed'
  AND m.platform_type = 'mobile'  AND m.status = 'passed'
ORDER BY d.project_name, d.module_name

-- module-level metrics
SELECT project_name, module_name, platform_type, total_tests, passed, failed, pass_rate
FROM module_metrics ORDER BY project_name, module_name, platform_type

-- project-level metrics
SELECT project_name, platform_type, total_tests, passed, failed, pass_rate, module_count
FROM project_metrics ORDER BY project_name, platform_type

-- failed tests in specific module
SELECT test_name, project_name, platform_type, browser, error
FROM flattened_tests WHERE status = 'failed' AND module_name ILIKE '%Eligibility%'
ORDER BY platform_type, test_name

-- all failed tests
SELECT test_name, project_name, module_name, platform_type, browser, error
FROM flattened_tests WHERE status = 'failed'
ORDER BY project_name, module_name, platform_type LIMIT 100

-- slowest tests
SELECT test_name, module_name, project_name, platform_type,
       ROUND(duration, 2) AS duration_sec
FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0
ORDER BY duration DESC LIMIT 15

-- release check
SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate,
       COUNT(*) AS total,
       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count
FROM flattened_tests WHERE status IN ('passed','failed')

=== RULES ===
1. ANY data question → action="sql"
2. Greetings / meta only → action="answer"
3. SQL must be valid DuckDB — no trailing semicolon
4. Always use ILIKE for string matching
5. For mobile/desktop questions always use platform_type column
6. Prefer module_metrics / project_metrics for aggregated answers

Return ONLY this JSON (no markdown, no explanation):
{{"action":"sql","data":"SELECT ..."}} OR {{"action":"answer","data":"plain text"}}"""


# ---------------------------------------------------------------------------
# CHAT – ANSWER PROMPT
# ---------------------------------------------------------------------------

CHAT_ANSWER_PROMPT = """You are a concise QA analytics assistant. Answer directly using the data below.

USER QUESTION: {user_message}

DATA ({row_count} rows):
{data_json}

RULES:
- Direct and specific — no "based on the data" filler
- Single number → emoji + bold (e.g. "📊 **347 tests failed**")
- Lists → numbered, max 30 items, then "… and N more"
- Include project_name, module_name, platform_type when present in data
- Pass rate → percentage + one-line verdict
- Keep under 250 words unless listing many items
- Never invent data not in the JSON

Answer:"""


CHAT_VALIDATION_PROMPT = """You are a strict QA answer validator.

Validate whether DRAFT_ANSWER is fully supported by the DATA rows.

USER_QUESTION: {user_message}
DRAFT_ANSWER: {draft_answer}

DATA ({row_count} rows):
{data_json}

RULES:
1. Mark is_valid=true only if every claim in DRAFT_ANSWER is supported by DATA.
2. If any claim is unsupported, set is_valid=false and provide corrected_answer grounded only in DATA.
3. Never invent values or entities not present in DATA.
4. Keep corrected_answer concise and direct.

Return ONLY valid JSON:
{{"is_valid": true, "corrected_answer": ""}}
or
{{"is_valid": false, "corrected_answer": "..."}}"""


# ---------------------------------------------------------------------------
# CHAT – RELEASE VERDICT TEMPLATE
# ---------------------------------------------------------------------------

CHAT_RELEASE_VERDICT = """📊 **Release Readiness Report**

**Pass Rate:** {pass_rate}% ({passed} passed / {total} executed)
**Failed Tests:** {failed_count}

**Verdict:** {verdict}

**Recommendation:** {recommendation}"""


# ---------------------------------------------------------------------------
# CHART – SQL PROMPT
# ---------------------------------------------------------------------------

CHART_SQL_PROMPT = """You are a DuckDB SQL expert. Generate ONE valid SQL query for this chart request.

Tables:

flattened_tests:
  test_name, status(passed|failed|skipped|pending|unknown),
  duration FLOAT (seconds), error, spec_file,
  project_name(FSA|HSA|WDH), module_name, platform_type(desktop|mobile),
  browser (GoogleChrome | GoogleChromeiPhoneX | …)

module_metrics:
  project_name, module_name, platform_type,
  total_tests, passed, failed, skipped, pending, unknown,
  pass_rate FLOAT, total_duration_seconds FLOAT, avg_duration_seconds FLOAT

project_metrics:
  project_name, platform_type, module_count,
  total_tests, passed, failed, skipped, pending, unknown,
  pass_rate FLOAT, total_duration_seconds FLOAT

USER REQUEST: "{user_prompt}"
REQUESTED CHART TYPE: {chart_type}

PATTERNS BY CHART TYPE:

[bar / grouped_bar]
  -- failures by module
  SELECT module_name, project_name, platform_type, failed AS failure_count
  FROM module_metrics WHERE failed > 0 ORDER BY failure_count DESC LIMIT 15

  -- pass rate by module
  SELECT module_name, project_name, platform_type,
         ROUND(pass_rate, 1) AS pass_rate, total_tests
  FROM module_metrics ORDER BY pass_rate ASC LIMIT 20

  -- failures by project
  SELECT project_name, platform_type, failed AS failure_count, total_tests, pass_rate
  FROM project_metrics ORDER BY project_name, platform_type

  -- test counts per module
  SELECT module_name, project_name, platform_type, total_tests, passed, failed
  FROM module_metrics ORDER BY total_tests DESC LIMIT 20

[horizontal_bar]
  -- slowest tests
  SELECT test_name, module_name, project_name, platform_type,
         ROUND(duration, 2) AS duration_sec
  FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0
  ORDER BY duration DESC LIMIT 10

  -- modules by failure count
  SELECT module_name, project_name, failed AS failure_count
  FROM module_metrics WHERE failed > 0 ORDER BY failure_count DESC LIMIT 15

[pie / donut]
  -- passed vs failed
  SELECT status, COUNT(*) AS count FROM flattened_tests
  WHERE status IN ('passed','failed') GROUP BY status

  -- full status distribution
  SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC

  -- mobile vs desktop split
  SELECT platform_type, COUNT(*) AS count FROM flattened_tests GROUP BY platform_type

[line]
  -- NOTE: line charts need an x-axis with ordered values.
  -- Use duration bucketed, or if build_id/executed_at vary use that.
  -- Duration over time: ordered by duration
  SELECT test_name, ROUND(duration, 2) AS duration_sec,
         ROW_NUMBER() OVER (ORDER BY duration) AS test_index
  FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0
  ORDER BY duration LIMIT 30

  -- pass rate trend by module (alphabetical as proxy)
  SELECT module_name, ROUND(pass_rate, 1) AS pass_rate
  FROM module_metrics WHERE project_name IS NOT NULL
  ORDER BY module_name LIMIT 20

[heatmap]
  -- project × module failures
  SELECT project_name, module_name, failed AS failures
  FROM module_metrics WHERE failed > 0 ORDER BY project_name, failures DESC

  -- module × platform failures
  SELECT module_name, platform_type, failed AS failures
  FROM module_metrics WHERE failed > 0 ORDER BY module_name, platform_type

[scatter]
  -- duration vs status (each test is a point)
  SELECT test_name, ROUND(duration, 2) AS duration_sec, status, project_name, platform_type
  FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0
  ORDER BY duration DESC LIMIT 50

[platform_comparison]
  SELECT platform_type,
         ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 1) AS pass_rate,
         COUNT(*) AS total_tests,
         SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
  FROM flattened_tests WHERE status IN ('passed','failed')
  GROUP BY platform_type ORDER BY platform_type

RULES:
1. Return ONLY raw SQL — no markdown, no semicolon at end
2. Use ILIKE for string matching
3. Max 25 rows for readability
4. Handle NULLs with IS NOT NULL
5. Prefer module_metrics / project_metrics for aggregated charts
6. If request is impossible → SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status

SQL:"""


# ---------------------------------------------------------------------------
# CHART – CODE PROMPT (STRICT TYPE ENFORCEMENT)
# ---------------------------------------------------------------------------
# This is NOT a generic "generate any chart" prompt.
# We inject the EXACT Plotly template for the detected chart type.
# The LLM only fills in column names and title — it cannot change the chart type.

CHART_CODE_PROMPT = """You are a Plotly Python expert. Generate chart code for this EXACT chart type.

USER REQUEST: "{user_prompt}"

⚠️ MANDATORY CHART TYPE: {chart_type}
You MUST use ONLY the chart pattern shown below. Do NOT substitute a different chart type.
If the user asked for a line chart, generate a LINE chart.
If the user asked for a pie chart, generate a PIE chart.
Generating the wrong chart type is a critical failure.

DATA (variable `data` is already defined as list of dicts):
{data_sample}

COLUMNS AVAILABLE: {columns}

=== REQUIRED CHART PATTERN FOR: {chart_type} ===
{chart_template}

=== STRICT RULES ===
1. Use EXACTLY the chart pattern above — same chart type, same function
2. `data` is already defined as a Python list of dicts — DO NOT reassign it
3. Always start with: import pandas as pd; df = pd.DataFrame(data)
4. Final figure MUST be stored in variable named `fig`
5. FORBIDDEN kwargs: hovertemplate, customdata, piecolorway, Blues_d, Blues_r, width=, height=, template=
6. DO NOT include any fig.update_layout() call — caller applies all layout/theme
7. Use color='platform_type' when platform_type column exists
8. Use color='project_name' when project_name column exists (and no platform_type split needed)
9. Long axis labels: fig.update_xaxes(tickangle=-35) or fig.update_yaxes(automargin=True)
10. ALLOWED discrete colors only: ['#6C8BFF','#22C55E','#F59E0B','#EF4444','#A855F7','#06B6D4','#EC4899']
11. ALLOWED color scales only: 'Viridis', 'RdYlGn', 'Plasma', 'Reds', 'Blues'

Return ONLY Python code. No markdown fences. No explanation. No comments."""


# ---------------------------------------------------------------------------
# CHART TYPE TEMPLATES — injected into CHART_CODE_PROMPT at runtime
# ---------------------------------------------------------------------------

CHART_TEMPLATES = {
    "bar": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
# Determine x and y from available columns
x_col = next((c for c in ['module_name','project_name','status','browser'] if c in df.columns), df.columns[0])
y_col = next((c for c in ['failure_count','failed','pass_rate','total_tests','count','duration_sec'] if c in df.columns), df.columns[-1])
color_col = 'platform_type' if 'platform_type' in df.columns else ('project_name' if 'project_name' in df.columns else None)
fig = px.bar(
    df, x=x_col, y=y_col,
    color=color_col,
    title="{title}",
    barmode='group',
    color_discrete_sequence=['#6C8BFF','#22C55E','#F59E0B','#EF4444','#A855F7','#06B6D4']
)
fig.update_traces(textfont_size=11, textangle=0, textposition='outside', cliponaxis=False)
fig.update_xaxes(tickangle=-35)
""",

    "horizontal_bar": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
x_col = next((c for c in ['duration_sec','failure_count','failed','count','total_tests'] if c in df.columns), df.columns[-1])
y_col = next((c for c in ['test_name','module_name','project_name'] if c in df.columns), df.columns[0])
color_col = 'platform_type' if 'platform_type' in df.columns else ('project_name' if 'project_name' in df.columns else None)
# Sort descending by value for readability
df = df.sort_values(x_col, ascending=True)
fig = px.bar(
    df, x=x_col, y=y_col, orientation='h',
    color=color_col,
    title="{title}",
    color_discrete_sequence=['#6C8BFF','#22C55E','#F59E0B','#EF4444','#A855F7','#06B6D4']
)
fig.update_traces(textfont_size=10, textposition='outside', cliponaxis=False)
fig.update_yaxes(automargin=True)
""",

    "pie": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
names_col = next((c for c in ['status','platform_type','project_name','module_name'] if c in df.columns), df.columns[0])
values_col = next((c for c in ['count','total_tests','failed','passed'] if c in df.columns), df.columns[-1])
fig = px.pie(
    df, names=names_col, values=values_col,
    title="{title}",
    color_discrete_sequence=['#22C55E','#EF4444','#F59E0B','#A855F7','#06B6D4','#6C8BFF','#EC4899']
)
fig.update_traces(textposition='inside', textinfo='percent+label', textfont_size=13)
""",

    "donut": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
names_col = next((c for c in ['status','platform_type','project_name','module_name'] if c in df.columns), df.columns[0])
values_col = next((c for c in ['count','total_tests','failed','passed'] if c in df.columns), df.columns[-1])
fig = px.pie(
    df, names=names_col, values=values_col,
    hole=0.45,
    title="{title}",
    color_discrete_sequence=['#22C55E','#EF4444','#F59E0B','#A855F7','#06B6D4','#6C8BFF','#EC4899']
)
fig.update_traces(textposition='inside', textinfo='percent+label', textfont_size=13)
""",

    "line": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
x_col = next((c for c in ['test_index','module_name','executed_at','build_id'] if c in df.columns), df.columns[0])
y_col = next((c for c in ['pass_rate','duration_sec','count','total_tests'] if c in df.columns), df.columns[-1])
color_col = 'platform_type' if 'platform_type' in df.columns else ('project_name' if 'project_name' in df.columns else None)
fig = px.line(
    df, x=x_col, y=y_col,
    color=color_col,
    title="{title}",
    markers=True,
    color_discrete_sequence=['#6C8BFF','#22C55E','#F59E0B','#EF4444','#A855F7','#06B6D4']
)
fig.update_traces(line_width=2.5, marker_size=8)
fig.update_xaxes(tickangle=-35)
""",

    "heatmap": """
import pandas as pd
import plotly.graph_objects as go
df = pd.DataFrame(data)
# Pick row/column axes for pivot
row_col = next((c for c in ['module_name','project_name'] if c in df.columns), df.columns[0])
col_col = next((c for c in ['project_name','platform_type','module_name'] if c in df.columns and c != row_col), df.columns[1])
val_col = next((c for c in ['failures','failed','count','total_tests','pass_rate'] if c in df.columns), df.columns[-1])
pivot = df.pivot_table(index=row_col, columns=col_col, values=val_col, fill_value=0, aggfunc='sum')
text_vals = pivot.values.astype(int).astype(str)
fig = go.Figure(go.Heatmap(
    z=pivot.values,
    x=pivot.columns.tolist(),
    y=pivot.index.tolist(),
    colorscale='Reds',
    text=text_vals,
    texttemplate='%{{text}}',
    showscale=True
))
fig.update_layout(title="{title}")
""",

    "scatter": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
x_col = next((c for c in ['duration_sec','total_tests'] if c in df.columns), df.columns[0])
y_col = next((c for c in ['pass_rate','failed','passed'] if c in df.columns), df.columns[-1])
color_col = 'platform_type' if 'platform_type' in df.columns else ('status' if 'status' in df.columns else None)
hover_col = 'test_name' if 'test_name' in df.columns else ('module_name' if 'module_name' in df.columns else None)
fig = px.scatter(
    df, x=x_col, y=y_col,
    color=color_col,
    hover_name=hover_col,
    title="{title}",
    color_discrete_sequence=['#6C8BFF','#22C55E','#F59E0B','#EF4444','#A855F7','#06B6D4']
)
fig.update_traces(marker_size=10, marker_opacity=0.8)
""",

    "platform_comparison": """
import pandas as pd
import plotly.express as px
df = pd.DataFrame(data)
x_col = 'platform_type' if 'platform_type' in df.columns else df.columns[0]
y_col = next((c for c in ['pass_rate','failed','passed','total_tests'] if c in df.columns), df.columns[-1])
color_map = {'mobile': '#EF4444', 'desktop': '#22C55E'}
fig = px.bar(
    df, x=x_col, y=y_col,
    color=x_col,
    title="{title}",
    color_discrete_map=color_map,
    text_auto=True
)
fig.update_traces(textfont_size=13, textposition='outside')
""",
}


def get_chart_template(chart_type: str, title: str) -> str:
    """Return the filled-in chart template for the given chart type."""
    template = CHART_TEMPLATES.get(chart_type, CHART_TEMPLATES["bar"])
    return template.replace("{title}", title[:60])


# ---------------------------------------------------------------------------
# CHART TYPE DETECTION — deterministic, not LLM-based
# ---------------------------------------------------------------------------

def detect_chart_type(prompt: str) -> str:
    """
    Deterministic chart type detection from the user prompt.
    Returns one of: bar, horizontal_bar, pie, donut, line, heatmap, scatter, platform_comparison
    Order matters — more specific patterns checked first.
    """
    p = prompt.lower()

    # Line chart — must check BEFORE bar to catch "line chart"
    if any(k in p for k in ("line chart", "line graph", "trend", "over time", "timeline", "over builds")):
        return "line"

    # Heatmap
    if any(k in p for k in ("heatmap", "heat map", "matrix", "grid")):
        return "heatmap"

    # Scatter
    if any(k in p for k in ("scatter", "bubble", "dot plot")):
        return "scatter"

    # Donut (before pie)
    if "donut" in p or "doughnut" in p:
        return "donut"

    # Pie
    if any(k in p for k in ("pie chart", "pie graph", "pie ")):
        return "pie"

    # Platform comparison (before horizontal/bar)
    if any(k in p for k in (
        "mobile vs desktop", "desktop vs mobile", "platform comparison",
        "compare platform", "platform split", "by platform"
    )):
        return "platform_comparison"

    # Horizontal bar — must check BEFORE generic "bar"
    if any(k in p for k in (
        "horizontal bar", "horizontal chart", "slowest", "longest",
        "top offender", "ranked by", "ranking"
    )):
        return "horizontal_bar"

    # Bar (default for most data questions)
    if any(k in p for k in (
        "bar chart", "bar graph", "column chart", "grouped bar",
        "stacked bar", "distribution", "breakdown", "count",
        "failures by", "pass rate by", "per module", "per project",
        "by module", "by project", "by status"
    )):
        return "bar"

    # Final fallback
    return "bar"


# ---------------------------------------------------------------------------
# FALLBACK SQL MAPS
# ---------------------------------------------------------------------------

FALLBACK_SQL_MAP = {
    r"(highest|best|max|top).*(pass rate)|(pass rate).*(highest|best|max|top)": (
        "SELECT project_name, module_name, platform_type, total_tests, passed, failed,"
        " ROUND(pass_rate, 2) AS pass_rate"
        " FROM module_metrics ORDER BY pass_rate DESC LIMIT 1"
    ),
    r"(lowest|least|min|worst|bottom).*(pass rate)|(pass rate).*(lowest|least|min|worst|bottom)": (
        "SELECT project_name, module_name, platform_type, total_tests, passed, failed,"
        " ROUND(pass_rate, 2) AS pass_rate"
        " FROM module_metrics ORDER BY pass_rate ASC LIMIT 1"
    ),
    r"how many.*fail|count.*fail": (
        "SELECT COUNT(*) AS failed_count FROM flattened_tests WHERE status = 'failed'"
    ),
    r"how many.*pass|count.*pass": (
        "SELECT COUNT(*) AS passed_count FROM flattened_tests WHERE status = 'passed'"
    ),
    r"pass rate|good for release|ready for release|release|ship|deploy": (
        "SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate,"
        " COUNT(*) AS total,"
        " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count"
        " FROM flattened_tests WHERE status IN ('passed','failed')"
    ),
    r"status|breakdown|distribution": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC"
    ),
    r"mobile.*fail|fail.*mobile|iphone.*fail|fail.*iphone": (
        "SELECT test_name, project_name, module_name, browser, error"
        " FROM flattened_tests WHERE status = 'failed' AND platform_type = 'mobile'"
        " ORDER BY project_name, module_name"
    ),
    r"desktop.*fail|fail.*desktop": (
        "SELECT test_name, project_name, module_name, browser, error"
        " FROM flattened_tests WHERE status = 'failed' AND platform_type = 'desktop'"
        " ORDER BY project_name, module_name"
    ),
    r"cross.platform|platform.*comparison|mobile.*vs.*desktop|desktop.*vs.*mobile": (
        "SELECT platform_type,"
        " SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS passed,"
        " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,"
        " COUNT(*) AS total,"
        " ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate"
        " FROM flattened_tests GROUP BY platform_type ORDER BY platform_type"
    ),
    r"fail.*mobile.*not.*desktop|mobile.*only.*fail|only.*mobile.*fail": (
        "SELECT m.test_name, m.project_name, m.module_name, m.error AS mobile_error"
        " FROM flattened_tests m JOIN flattened_tests d ON m.test_name = d.test_name"
        " WHERE m.platform_type = 'mobile' AND m.status = 'failed'"
        " AND d.platform_type = 'desktop' AND d.status = 'passed'"
        " ORDER BY m.project_name, m.module_name"
    ),
    r"fail.*desktop.*not.*mobile|desktop.*only.*fail|only.*desktop.*fail": (
        "SELECT d.test_name, d.project_name, d.module_name, d.error AS desktop_error"
        " FROM flattened_tests d JOIN flattened_tests m ON d.test_name = m.test_name"
        " WHERE d.platform_type = 'desktop' AND d.status = 'failed'"
        " AND m.platform_type = 'mobile'  AND m.status = 'passed'"
        " ORDER BY d.project_name, d.module_name"
    ),
    r"all.*project|list.*project|projects": (
        "SELECT project_name, platform_type, total_tests, passed, failed, pass_rate, module_count"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
    r"all.*module|list.*module|module.*list": (
        "SELECT project_name, module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics ORDER BY project_name, module_name, platform_type"
    ),
    r"module.*count|count.*module|number.*module|tests.*per.*module": (
        "SELECT project_name, module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics ORDER BY project_name, total_tests DESC"
    ),
    r"\bfsa\b": (
        "SELECT module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics WHERE project_name = 'FSA'"
        " ORDER BY module_name, platform_type"
    ),
    r"\bhsa\b": (
        "SELECT module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics WHERE project_name = 'HSA'"
        " ORDER BY module_name, platform_type"
    ),
    r"\bwdh\b": (
        "SELECT module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics WHERE project_name = 'WDH'"
        " ORDER BY module_name, platform_type"
    ),
    r"eligibility.*tpa|tpa.*eligibility": (
        "SELECT test_name, project_name, module_name, platform_type, status, error"
        " FROM flattened_tests WHERE module_name ILIKE '%EligibilityTPA%' OR module_name ILIKE '%Eligibility TPA%'"
        " ORDER BY status, platform_type, test_name"
    ),
    r"eligibility": (
        "SELECT test_name, project_name, module_name, platform_type, status, error"
        " FROM flattened_tests WHERE module_name ILIKE '%Eligibility%'"
        " ORDER BY status, platform_type, test_name"
    ),
    r"fail.*test|failed.*test|list.*fail": (
        "SELECT test_name, project_name, module_name, platform_type, browser, error"
        " FROM flattened_tests WHERE status = 'failed'"
        " ORDER BY project_name, module_name, platform_type LIMIT 100"
    ),
    r"slow|duration|longest": (
        "SELECT test_name, module_name, project_name, platform_type,"
        " ROUND(duration, 2) AS duration_sec"
        " FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0"
        " ORDER BY duration DESC LIMIT 15"
    ),
    r"how many.*skip|skipped": (
        "SELECT platform_type, COUNT(*) AS skipped_count"
        " FROM flattened_tests WHERE status = 'skipped' GROUP BY platform_type"
    ),
    r"total.*test|how many.*test": (
        "SELECT platform_type, COUNT(*) AS total_tests"
        " FROM flattened_tests GROUP BY platform_type"
    ),
    r"critical.*fail|fail.*critical": (
        "SELECT COUNT(*) AS critical_failures FROM flattened_tests WHERE status = 'failed'"
    ),
}

CHART_FALLBACK_SQL_MAP = {
    r"status|distribution|breakdown": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC"
    ),
    r"pass.*fail|fail.*pass|pie|donut": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests"
        " WHERE status IN ('passed','failed') GROUP BY status"
    ),
    r"mobile.*desktop|platform|cross|by platform": (
        "SELECT platform_type,"
        " ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 1) AS pass_rate,"
        " COUNT(*) AS total"
        " FROM flattened_tests WHERE status IN ('passed','failed')"
        " GROUP BY platform_type ORDER BY platform_type"
    ),
    r"module.*fail|fail.*module|failures.*module": (
        "SELECT module_name, project_name, platform_type, failed AS failure_count, pass_rate"
        " FROM module_metrics WHERE failed > 0 ORDER BY failure_count DESC LIMIT 15"
    ),
    r"project.*fail|fail.*project": (
        "SELECT project_name, platform_type, failed AS failure_count, total_tests, pass_rate"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
    r"slow|duration|longest|horizontal": (
        "SELECT test_name, module_name, project_name, platform_type,"
        " ROUND(duration, 2) AS duration_sec"
        " FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0"
        " ORDER BY duration DESC LIMIT 10"
    ),
    r"pass rate.*module|module.*pass rate": (
        "SELECT module_name, project_name, platform_type,"
        " ROUND(pass_rate, 1) AS pass_rate, total_tests"
        " FROM module_metrics ORDER BY pass_rate ASC LIMIT 20"
    ),
    r"pass rate.*project|project.*pass rate": (
        "SELECT project_name, platform_type,"
        " ROUND(pass_rate, 1) AS pass_rate, total_tests, passed, failed"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
    r"module.*count|tests.*per.*module": (
        "SELECT module_name, project_name, platform_type, total_tests, passed, failed"
        " FROM module_metrics ORDER BY total_tests DESC LIMIT 20"
    ),
    r"heatmap|matrix|heat": (
        "SELECT project_name, module_name, failed AS failures"
        " FROM module_metrics WHERE failed > 0 ORDER BY project_name, failures DESC"
    ),
    r"line|trend|over time": (
        "SELECT module_name, ROUND(pass_rate, 1) AS pass_rate"
        " FROM module_metrics WHERE project_name IS NOT NULL"
        " ORDER BY module_name LIMIT 20"
    ),
    r"scatter": (
        "SELECT test_name, ROUND(duration, 2) AS duration_sec, status, project_name, platform_type"
        " FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0"
        " ORDER BY duration DESC LIMIT 50"
    ),
    r"project|fsa|hsa|wdh": (
        "SELECT project_name, platform_type,"
        " ROUND(pass_rate, 1) AS pass_rate, total_tests, passed, failed"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
}