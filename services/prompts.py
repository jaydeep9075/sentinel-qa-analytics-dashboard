"""
prompts.py — LLM prompt templates for chat and chart generation.

Schema is now:
  flattened_tests:
    test_name, status, duration (float sec), error, spec_file,
    project_name (FSA|HSA|WDH|unknown),
    module_name  ("Eligibility Tests", "Checkout Tests", …),
    platform_type (desktop | mobile),
    browser  (e.g. "GoogleChrome", "GoogleChromeiPhoneX", "GoogleChromeiPad")

  module_metrics:
    project_name, module_name, platform_type,
    total_tests, passed, failed, skipped, pending, unknown,
    pass_rate, total_duration_seconds, avg_duration_seconds

  project_metrics:
    project_name, platform_type, module_count,
    total_tests, passed, failed, skipped, pending, unknown,
    pass_rate, total_duration_seconds, avg_duration_seconds

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
  module_name   VARCHAR   – "Eligibility Tests" | "Checkout Tests" | "Cart Tests" | …
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
• platform_type = 'mobile'   means tests run on iPhone/iPad/Android simulation
• platform_type = 'desktop'  means tests run on standard Chrome browser
• browser column holds the exact value, e.g. "GoogleChromeiPhoneX"
• To filter mobile: WHERE platform_type = 'mobile'
• To filter iPhone specifically: WHERE browser ILIKE '%iphone%'
• To filter desktop: WHERE platform_type = 'desktop'
• Cross-platform comparison: GROUP BY platform_type

=== CONVERSATION HISTORY (last 20 turns) ===
{history}

=== CURRENT USER REQUEST ===
"{user_message}"

=== RELEASE DECISION LOGIC ===
pass_rate >= 95% AND failed = 0 → GOOD FOR RELEASE
pass_rate 80–94%               → CONSIDER WITH CAUTION
pass_rate < 80%                → NOT READY FOR RELEASE

=== PROVEN SQL PATTERNS (copy exactly) ===

-- overall counts
SELECT COUNT(*) AS total FROM flattened_tests
SELECT COUNT(*) AS failed_count FROM flattened_tests WHERE status = 'failed'

-- pass rate (exclude skipped from denominator)
SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate,
       COUNT(*) AS total,
       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count
FROM flattened_tests WHERE status IN ('passed','failed')

-- status breakdown
SELECT status, COUNT(*) AS cnt FROM flattened_tests GROUP BY status ORDER BY cnt DESC

-- mobile vs desktop comparison
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

-- tests that failed on mobile but passed on desktop (cross-platform failures)
SELECT m.test_name, m.project_name, m.module_name, m.error AS mobile_error
FROM flattened_tests m
JOIN flattened_tests d ON m.test_name = d.test_name
WHERE m.platform_type = 'mobile' AND m.status = 'failed'
  AND d.platform_type = 'desktop' AND d.status = 'passed'
ORDER BY m.project_name, m.module_name

-- tests that failed on desktop but passed on mobile
SELECT d.test_name, d.project_name, d.module_name, d.error AS desktop_error
FROM flattened_tests d
JOIN flattened_tests m ON d.test_name = m.test_name
WHERE d.platform_type = 'desktop' AND d.status = 'failed'
  AND m.platform_type = 'mobile'  AND m.status = 'passed'
ORDER BY d.project_name, d.module_name

-- all projects with metrics
SELECT project_name, platform_type, total_tests, passed, failed, pass_rate, module_count
FROM project_metrics ORDER BY project_name, platform_type

-- all modules with metrics (both platforms)
SELECT project_name, module_name, platform_type, total_tests, passed, failed, pass_rate
FROM module_metrics ORDER BY project_name, module_name, platform_type

-- failed tests in a specific module
SELECT test_name, project_name, platform_type, browser, error
FROM flattened_tests WHERE status = 'failed' AND module_name ILIKE '%Eligibility%'
ORDER BY platform_type, test_name

-- failed tests in a specific project
SELECT test_name, module_name, platform_type, error
FROM flattened_tests WHERE status = 'failed' AND project_name = 'FSA'
ORDER BY module_name, platform_type

-- all failed tests (all projects, all platforms)
SELECT test_name, project_name, module_name, platform_type, browser, error
FROM flattened_tests WHERE status = 'failed'
ORDER BY project_name, module_name, platform_type

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
4. ALWAYS use ILIKE for string matching, not LIKE
5. For mobile/desktop questions use platform_type column
6. Use module_metrics / project_metrics for aggregated answers (faster, exact)
7. Use flattened_tests for individual test lookups and cross-platform joins

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
- Include project_name, module_name, platform_type columns when present
- Pass rate → percentage + one-line verdict
- Keep under 250 words unless listing items
- Never invent data not in the JSON

Answer:"""


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

CHART_SQL_PROMPT = """You are a DuckDB SQL expert. Generate ONE valid SQL query for the given chart request.

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

test_cases:
  module_name, priority, title(=test_name), project_name, platform_type

USER REQUEST: "{user_prompt}"

PROVEN PATTERNS:
-- status distribution
SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC

-- passed vs failed (pie)
SELECT status, COUNT(*) AS count FROM flattened_tests
WHERE status IN ('passed','failed') GROUP BY status

-- mobile vs desktop pass rate (bar)
SELECT platform_type,
       ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 1) AS pass_rate,
       COUNT(*) AS total_tests
FROM flattened_tests WHERE status IN ('passed','failed')
GROUP BY platform_type ORDER BY platform_type

-- failures by module, split by platform (grouped bar)
SELECT module_name, project_name, platform_type, failed AS failure_count
FROM module_metrics WHERE failed > 0
ORDER BY failure_count DESC LIMIT 20

-- failures by project (bar)
SELECT project_name, platform_type, failed AS failure_count, total_tests, pass_rate
FROM project_metrics ORDER BY project_name, platform_type

-- pass rate by module (bar, colored by project)
SELECT module_name, project_name, platform_type,
       ROUND(pass_rate, 1) AS pass_rate, total_tests
FROM module_metrics ORDER BY pass_rate ASC LIMIT 20

-- slowest tests (horizontal bar)
SELECT test_name, module_name, project_name, platform_type,
       ROUND(duration, 2) AS duration_sec
FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0
ORDER BY duration DESC LIMIT 10

-- module test count (bar, grouped by project)
SELECT module_name, project_name, platform_type, total_tests, passed, failed
FROM module_metrics ORDER BY total_tests DESC LIMIT 20

-- heatmap: project × module failures
SELECT project_name, module_name, failed AS failures
FROM module_metrics WHERE failed > 0 ORDER BY project_name, failures DESC

-- cross-platform: tests failing on both
SELECT ft.test_name, ft.project_name, ft.module_name,
       SUM(CASE WHEN ft.platform_type='mobile'  AND ft.status='failed' THEN 1 ELSE 0 END) AS failed_mobile,
       SUM(CASE WHEN ft.platform_type='desktop' AND ft.status='failed' THEN 1 ELSE 0 END) AS failed_desktop
FROM flattened_tests ft
GROUP BY ft.test_name, ft.project_name, ft.module_name
HAVING failed_mobile > 0 OR failed_desktop > 0
ORDER BY failed_mobile DESC, failed_desktop DESC LIMIT 20

RULES:
1. Return ONLY raw SQL — no markdown, no semicolon
2. Use ILIKE for string matching
3. Max 25 rows
4. Handle NULLs with IS NOT NULL
5. Prefer module_metrics / project_metrics for aggregated charts
6. If impossible → SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status

SQL:"""


# ---------------------------------------------------------------------------
# CHART – CODE PROMPT
# ---------------------------------------------------------------------------

CHART_CODE_PROMPT = """You are a Plotly expert. Generate clean Python code for a professional chart.

USER REQUEST: "{user_prompt}"
CHART TYPE HINT: {chart_type}

DATA (variable `data` is already defined as list of dicts):
{data_sample}

COLUMNS AVAILABLE: {columns}

STRICT REQUIREMENTS:
1. Import ONLY: import plotly.express as px  OR  import plotly.graph_objects as go
2. `data` is already defined — DO NOT reassign it
3. Convert: import pandas as pd; df = pd.DataFrame(data)
4. Final figure MUST be in variable `fig`
5. ALLOWED color scales: 'Viridis', 'RdYlGn', 'Plasma', 'Reds'
6. ALLOWED discrete colors: ['#6C8BFF','#22C55E','#F59E0B','#EF4444','#A855F7','#06B6D4','#EC4899']
7. FORBIDDEN kwargs: hovertemplate, customdata, piecolorway, Blues_d, Blues_r, width=, height=, template=
8. DO NOT include fig.update_layout() — caller handles all layout styling
9. Bar text outside: fig.update_traces(textfont_size=11, textangle=0, textposition='outside', cliponaxis=False)
10. Pie text inside: fig.update_traces(textposition='inside', textinfo='percent+label', textfont_size=12)
11. Long labels: fig.update_xaxes(tickangle=-35)
12. When platform_type column exists, use color='platform_type' for grouped bars
13. When project_name column exists, use color='project_name' for grouped bars

CHART TYPE GUIDES:

Vertical bar:
  df = pd.DataFrame(data)
  fig = px.bar(df, x='module_name', y='failure_count', color='project_name',
               title='Failures by Module', barmode='group',
               color_discrete_sequence=['#6C8BFF','#22C55E','#F59E0B','#EF4444'])
  fig.update_traces(textfont_size=11, textangle=0, textposition='outside', cliponaxis=False)

Horizontal bar (long names / slowest tests):
  df = pd.DataFrame(data)
  fig = px.bar(df, x='duration_sec', y='test_name', orientation='h',
               color='platform_type', title='Slowest Tests',
               color_discrete_sequence=['#6C8BFF','#22C55E'])

Pie chart:
  df = pd.DataFrame(data)
  fig = px.pie(df, names='status', values='count', title='Test Status',
               color_discrete_sequence=['#22C55E','#EF4444','#F59E0B','#A855F7','#06B6D4'])
  fig.update_traces(textposition='inside', textinfo='percent+label', textfont_size=12)

Grouped bar (mobile vs desktop):
  df = pd.DataFrame(data)
  fig = px.bar(df, x='project_name', y='pass_rate', color='platform_type',
               barmode='group', title='Pass Rate: Mobile vs Desktop',
               color_discrete_map={{'mobile':'#EF4444','desktop':'#22C55E'}})

Heatmap:
  df = pd.DataFrame(data)
  pivot = df.pivot_table(index='module_name', columns='project_name',
                         values='failures', fill_value=0, aggfunc='sum')
  fig = go.Figure(go.Heatmap(
      z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
      colorscale='Reds', text=pivot.values.astype(str), texttemplate='%{{text}}'
  ))

Return ONLY Python code. No markdown fences. No explanation."""


# ---------------------------------------------------------------------------
# FALLBACK SQL MAPS
# ---------------------------------------------------------------------------

FALLBACK_SQL_MAP = {
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
    # ── mobile / desktop ──
    r"mobile.*fail|fail.*mobile|iphone.*fail|fail.*iphone": (
        "SELECT test_name, project_name, module_name, browser, error"
        " FROM flattened_tests WHERE status = 'failed' AND platform_type = 'mobile'"
        " ORDER BY project_name, module_name"
    ),
    r"desktop.*fail|fail.*desktop|chrome.*fail|fail.*chrome": (
        "SELECT test_name, project_name, module_name, browser, error"
        " FROM flattened_tests WHERE status = 'failed' AND platform_type = 'desktop'"
        " ORDER BY project_name, module_name"
    ),
    r"mobile.*pass|pass.*mobile": (
        "SELECT COUNT(*) AS passed_mobile FROM flattened_tests"
        " WHERE status = 'passed' AND platform_type = 'mobile'"
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
        " FROM flattened_tests m"
        " JOIN flattened_tests d ON m.test_name = d.test_name"
        " WHERE m.platform_type = 'mobile' AND m.status = 'failed'"
        " AND d.platform_type = 'desktop' AND d.status = 'passed'"
        " ORDER BY m.project_name, m.module_name"
    ),
    r"fail.*desktop.*not.*mobile|desktop.*only.*fail|only.*desktop.*fail": (
        "SELECT d.test_name, d.project_name, d.module_name, d.error AS desktop_error"
        " FROM flattened_tests d"
        " JOIN flattened_tests m ON d.test_name = m.test_name"
        " WHERE d.platform_type = 'desktop' AND d.status = 'failed'"
        " AND m.platform_type = 'mobile'  AND m.status = 'passed'"
        " ORDER BY d.project_name, d.module_name"
    ),
    # ── projects ──
    r"all.*project|list.*project|projects": (
        "SELECT project_name, platform_type, total_tests, passed, failed, pass_rate, module_count"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
    # ── modules ──
    r"all.*module|list.*module|module.*list": (
        "SELECT project_name, module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics ORDER BY project_name, module_name, platform_type"
    ),
    r"module.*count|count.*module|number.*module|tests.*per.*module": (
        "SELECT project_name, module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics ORDER BY project_name, total_tests DESC"
    ),
    r"\bfsa\b.*module|module.*\bfsa\b|\bfsa\b": (
        "SELECT module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics WHERE project_name = 'FSA'"
        " ORDER BY module_name, platform_type"
    ),
    r"\bhsa\b.*module|module.*\bhsa\b|\bhsa\b": (
        "SELECT module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics WHERE project_name = 'HSA'"
        " ORDER BY module_name, platform_type"
    ),
    r"\bwdh\b.*module|module.*\bwdh\b|\bwdh\b": (
        "SELECT module_name, platform_type, total_tests, passed, failed, pass_rate"
        " FROM module_metrics WHERE project_name = 'WDH'"
        " ORDER BY module_name, platform_type"
    ),
    # ── eligibility ──
    r"eligibility.*tpa|tpa.*eligibility": (
        "SELECT test_name, project_name, module_name, platform_type, status, error"
        " FROM flattened_tests WHERE module_name ILIKE '%EligibilityTPA%'"
        " ORDER BY status, platform_type, test_name"
    ),
    r"eligibility": (
        "SELECT test_name, project_name, module_name, platform_type, status, error"
        " FROM flattened_tests WHERE module_name ILIKE '%Eligibility%'"
        " ORDER BY status, platform_type, test_name"
    ),
    # ── failed tests ──
    r"fail.*test|failed.*test|list.*fail": (
        "SELECT test_name, project_name, module_name, platform_type, browser, error"
        " FROM flattened_tests WHERE status = 'failed'"
        " ORDER BY project_name, module_name, platform_type LIMIT 100"
    ),
    # ── slowest ──
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
}

CHART_FALLBACK_SQL_MAP = {
    r"status|distribution|breakdown": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status ORDER BY count DESC"
    ),
    r"pass.*fail|fail.*pass|pie": (
        "SELECT status, COUNT(*) AS count FROM flattened_tests"
        " WHERE status IN ('passed','failed') GROUP BY status"
    ),
    r"mobile.*desktop|platform|cross": (
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
    r"project.*fail|fail.*project|failures.*project": (
        "SELECT project_name, platform_type, failed AS failure_count, total_tests, pass_rate"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
    r"slow|duration|longest": (
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
    r"heatmap|matrix": (
        "SELECT project_name, module_name, failed AS failures"
        " FROM module_metrics WHERE failed > 0 ORDER BY project_name, failures DESC"
    ),
    r"project|fsa|hsa|wdh": (
        "SELECT project_name, platform_type,"
        " ROUND(pass_rate, 1) AS pass_rate, total_tests, passed, failed"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
}