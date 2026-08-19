"""
prompts.py — LLM prompts for chat and chart SQL generation.

The LLM's job in the chart path is SQL only. Chart form, measure, dimension,
top-N, filters and all rendering are decided deterministically in
services/chart_spec.py and services/chart_builder.py; CHART_SQL_PROMPT receives
that parse as hard directives so the query and the picture agree.

Schema (column shape is fixed; actual project/module/browser VALUES are
whatever was ingested — see services/schema_context.py for live introspection):
  flattened_tests:
    test_name, status (passed|failed|skipped|pending|unknown),
    duration FLOAT (seconds), error, spec_file,
    project_name, module_name,
    platform_type (desktop|mobile),
    browser

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
  project_name  VARCHAR   – see ACTUAL VALUES section below for this dataset's real project names
  module_name   VARCHAR   – see ACTUAL VALUES section below for this dataset's real module names
  platform_type VARCHAR   – desktop | mobile
  browser       VARCHAR   – see ACTUAL VALUES section below for this dataset's real browser strings

{schema_examples}

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

-- failed tests in a specific module (substitute a real module_name substring
-- from the ACTUAL VALUES section, e.g. '%Checkout%' if that module exists here)
SELECT test_name, project_name, platform_type, browser, error
FROM flattened_tests WHERE status = 'failed' AND module_name ILIKE '%<module keyword>%'
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

=== DECISION RULES ===
1. Data question about counts, rates, comparisons, filters, or anything the
   tables/columns above can express (tests, metrics, pass rates, failures,
   modules, etc.) → action="sql"
1b. A question with SEVERAL DISTINCT PARTS that one query cannot answer well —
   e.g. "how does mobile compare to desktop, and which modules regressed?", or
   "give me the overall pass rate plus the worst 5 modules plus the slowest
   tests" → action="sql_multi", with "data" as a LIST of {{"label": "...",
   "sql": "SELECT ..."}} objects, one per part, max 4. Use this instead of
   contorting everything into one CTE, and instead of answering only the part
   that fits a single query. Each label should name the sub-question it
   answers ("Mobile vs desktop pass rate", "Modules below 80%"). Prefer a
   single "sql" when one query genuinely answers the whole question — a
   two-query plan for a one-query question just costs time.
2. Free-text search over unstructured content — the user wants to find or
   understand something inside error messages, logs, or descriptions that
   isn't a clean column filter (e.g. "find tests with errors mentioning
   timeout", "what kinds of issues show up in the logs", "search for
   anything related to authentication failures") → action="vector", with
   "data" set to a short search phrase capturing what to look for (not SQL)
3. Greetings, meta questions, or help requests → action="answer"
4. SQL must be valid DuckDB — no trailing semicolon, no LIMIT unless asking for top N
5. Always use ILIKE for case-insensitive string matching on VARCHAR columns
6. For mobile/desktop questions always use platform_type column, NOT browser name
7. Prefer aggregated tables (module_metrics, project_metrics) for summarized data
8. If unsure about status values, use WHERE status IN ('passed','failed','skipped','pending','unknown')
9. Complex questions may need multiple CTEs or joins — feel free to use them
10. For questions asking "top N" or "highest/lowest", always ORDER BY and LIMIT explicitly
11. When in doubt between sql and vector, prefer sql — it's precise and
    verifiable; vector is a fallback for questions sql genuinely can't answer.

RESPONSE_QUALITY_HINTS:
- SQL should return data that DIRECTLY answers the user's question
- Avoid SELECT * unless necessary; include only relevant columns
- Use aliases for clarity (e.g., AS total_failures, AS pct_failed)
- Order results in ways that reveal patterns (DESC for impact metrics)

Return ONLY this JSON (no markdown, no explanation), in one of these shapes:
{{"action":"sql","data":"SELECT ..."}}
{{"action":"sql_multi","data":[{{"label":"...","sql":"SELECT ..."}},{{"label":"...","sql":"SELECT ..."}}]}}
{{"action":"vector","data":"search phrase"}}
{{"action":"answer","data":"plain text"}}"""


# ---------------------------------------------------------------------------
# CHAT – ANSWER PROMPT
# ---------------------------------------------------------------------------

CHAT_ANSWER_PROMPT = """You are a senior QA analyst. Answer the question from the data below.

USER QUESTION: {user_message}

USER FEEDBACK PREFERENCES:
{feedback_hints}

WHOLE-RESULT FACTS (computed over ALL {row_count} rows — these are exact):
{dataset_facts}

SAMPLE ROWS (may be a subset of the full result):
{data_json}

=== HOW TO ANSWER ===

Structure, in this order, omitting any part the data doesn't support:
1. **The answer.** One sentence that directly answers what was asked, leading
   with the number or name that IS the answer. No preamble, no restating the
   question.
2. **The evidence.** The two or three figures that back it up. Name the
   entities (module, project, platform) — "Checkout on mobile", never "one
   module".
3. **What stands out.** An outlier, a concentration, a gap worth knowing —
   only if the data actually shows one. Skip it rather than manufacture it.
4. **What to do.** One concrete next step, only when the data implies one.

=== ACCURACY RULES (these override style) ===
- Every number you write must appear in, or be directly computed from, the data
  above. Never estimate, round to a "nicer" number, or infer a trend from a
  single snapshot.
- For anything about the WHOLE result (totals, "which is worst", "how many in
  all"), use the WHOLE-RESULT FACTS section. The sample rows may be a subset —
  never count them and present that count as the total.
- If the data doesn't answer the question, say exactly that and say what IS in
  the data. A clear "the data doesn't show X" beats a confident wrong answer.
- Don't describe a percentage difference as a percentage: a move from 78% to
  93% is **15 percentage points**, not 15%.
- If a figure is scoped (one project, one platform, executed tests only), say
  so — an unscoped-sounding number the reader applies globally is a wrong
  answer even when the arithmetic is right.

=== STYLE ===
- **Bold** every figure, with its unit: "**347 tests**", "**82.4%**", "**12.3s**".
- Emojis only as section markers where they earn it: 📊 metrics, ✅ healthy,
  ❌ failing, ⚠️ needs attention. Never more than one per line.
- Lists: numbered, at most 10 entries; if there are more, show the top 10 and
  write "…and N more".
- Under 200 words unless the user asked for depth. Cut adjectives before facts.
- No hedging ("seems", "appears", "might suggest") when the data is definite.

=== EXAMPLES ===
Single metric:
"📊 **347 tests failed** across **12 modules**. Checkout accounts for **89** of
them — 26% of all failures, more than the next three modules combined."

Comparison:
"Mobile trails desktop by **15.2 percentage points** (**78.2%** vs **93.4%**).
The gap is concentrated in Login: **41** of mobile's **62** failures. ⚠️ Worth
checking the iOS viewport setup before the next run."

No answer available:
"The data doesn't include execution timestamps, so I can't show a trend over
time. I can show current pass rate by module or by platform instead."

Answer:"""


CHAT_MULTI_ANSWER_PROMPT = """You are a senior QA analyst. The question below needed
several queries. Each labelled block is one part of it.

USER QUESTION: {user_message}

USER FEEDBACK PREFERENCES:
{feedback_hints}

RESULTS:
{result_blocks}

=== HOW TO ANSWER ===
- Answer the question as ONE coherent response, not a list of query dumps. The
  labels are for you, not the reader — don't echo them as headings unless they
  genuinely help.
- Address every part of the question. If a block returned nothing, say that
  part is unavailable; never quietly drop it or fill it with a guess.
- Connect the parts where the data connects them ("mobile's gap is almost
  entirely the two modules in the second result"). That relationship is the
  reason the question needed several queries, and it is the most valuable
  thing you can add.
- Each block's WHOLE-RESULT FACTS are exact and computed over every row; the
  row samples may be partial. Take totals and extremes from the facts.
- Never mix numbers between blocks — each figure belongs to the block it came
  from, and mislabelling which platform or module a number describes is the
  main failure mode here.
- Don't call a difference between two percentages a percentage: use
  "percentage points".

=== STYLE ===
- Lead with the single most important finding across all parts.
- **Bold** every figure with its unit. Emojis sparingly: 📊 ✅ ❌ ⚠️.
- Under 300 words. Numbered lists capped at 10 entries.

Answer:"""


CHAT_VALIDATION_PROMPT = """You are a strict QA answer validator. Your job is to ensure responses are accurate, grounded, and useful.

USER_QUESTION: {user_message}
DRAFT_ANSWER: {draft_answer}

DATA ({row_count} rows):
{data_json}

VALIDATION CHECKLIST (check each against the data, in order):
1. Every number, percentage and count in the answer appears in the data or is
   correctly computed from it. Re-derive each one; do not assume.
2. Every entity named (project, module, test, platform, browser) exists in the data.
3. Every superlative and ordering claim (highest, lowest, most, slowest, "leads",
   "worst") is actually true of the data — this is the most common error.
4. The answer addresses the question that was asked, not an adjacent one.
5. Nothing is extrapolated beyond the rows provided. If the data is a subset,
   the answer must not present its figures as totals.
6. A difference between two percentages is stated in **percentage points**,
   not as a percentage.
7. Any scope the figures carry (one project, one platform, executed tests only)
   is stated — an unscoped-sounding number that is actually scoped is an error
   even when the arithmetic is right.
8. No hedging where the data is definite; no false confidence where it isn't.

CORRECTION STRATEGY:
- If is_valid=false, fix ONLY the errors. Keep every correct statement verbatim.
- Preserve the answer's structure, formatting and tone — you are correcting
  facts, not rewriting.
- If a claim cannot be supported by the data at all, delete it rather than
  softening it into a vaguer version of the same wrong claim.
- Never add new claims of your own that the data does not support.

Return ONLY valid JSON:
{{"is_valid": true, "corrected_answer": ""}}
or
{{"is_valid": false, "corrected_answer": "...", "issues": ["issue 1", "issue 2"]}}"""


SUGGESTION_PROMPT = """You are an analytics copilot generating prompt suggestions for whatever
data has actually been ingested. It may be QA/test results, but it could just as easily be
sales records, support tickets, survey responses, PDF report extracts, or any other dataset —
infer the actual domain from the RUNTIME DATA PROFILE below. Do not assume test/QA analytics
unless the profile's real columns (status, pass_rate, failed, etc.) actually show that.

ROLE ID: {role_id}
PROJECT: {project_id}

ROLE INSTRUCTION:
{role_instruction}

RUNTIME DATA PROFILE (actual tables, columns, and sample rows in this ingestion):
{schema_profile}

INGESTION QUALITY SUMMARY:
{quality_summary}

TASK:
Generate practical, high-value suggestions so users can click and run them directly. Ground
every suggestion in the REAL column names and, where useful, real sample values shown in the
RUNTIME DATA PROFILE above — never invent a field that isn't present, and never default to
test/QA phrasing ("pass rate", "failed tests", etc.) unless those columns genuinely exist in
the profile.

OUTPUT RULES:
1. Return ONLY valid JSON.
2. Provide exactly 8 chat suggestions and 8 chart suggestions.
3. Suggestions must be grounded in the actual schema above, tailored to this role's priorities.
4. Avoid duplicates and vague phrases.
5. Each suggestion should be one concise sentence.

Return JSON:
{{"chat": ["..."], "chart": ["..."]}}"""


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
  project_name, module_name, platform_type(desktop|mobile),
  browser

{schema_examples}

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

=== PARSED INTENT — YOUR SQL MUST SATISFY EVERY LINE ===
These were extracted deterministically from the user's wording. They are not
suggestions: the renderer builds the chart from this same parse, so SQL that
ignores a line here produces a chart that answers a different question than
was asked (a "top 5" with no LIMIT, a measure the chart can't find, an
unrequested filter). If a directive names a column that does not exist in this
dataset, pick the closest real column rather than dropping the directive.
{spec_directives}

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

[line / area]
  -- A line chart needs a genuinely ORDERED x axis. Use executed_at or
  -- build_id when they vary. Never order by a name alphabetically and present
  -- it as a trend — alphabetical order is not time, and a chart that implies
  -- it is is simply wrong. If no ordered column exists, return a plain
  -- aggregate and let the renderer draw it as a bar instead.
  SELECT DATE_TRUNC('day', executed_at) AS day,
         ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 1) AS pass_rate,
         COUNT(*) AS total_tests
  FROM flattened_tests WHERE executed_at IS NOT NULL
  GROUP BY day ORDER BY day

[stacked_bar]
  -- one categorical axis + one series column + one measure
  SELECT module_name, platform_type, failed AS failure_count
  FROM module_metrics WHERE failed > 0 ORDER BY failure_count DESC

[histogram / box]
  -- raw per-row values, NOT pre-aggregated — the renderer does the bucketing
  SELECT test_name, module_name, platform_type, ROUND(duration, 2) AS duration_sec
  FROM flattened_tests WHERE duration IS NOT NULL AND duration > 0

[gauge]
  -- exactly one row, one number
  SELECT ROUND(SUM(CASE WHEN status='passed' THEN 1.0 ELSE 0 END)*100.0/COUNT(*), 2) AS pass_rate
  FROM flattened_tests WHERE status IN ('passed','failed')

[treemap / sunburst / funnel / radar]
  -- one categorical column + one numeric column (a second categorical column
  -- becomes the parent level for treemap/sunburst)
  SELECT project_name, module_name, failed AS failure_count
  FROM module_metrics WHERE failed > 0 ORDER BY failure_count DESC

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
3. Honour the row limit stated in PARSED INTENT above; if none was stated, keep
   the result under 100 rows (the renderer ranks and truncates for readability,
   but it can only truncate rows the query actually returned)
4. Handle NULLs with IS NOT NULL
5. Prefer module_metrics / project_metrics for aggregated charts; use
   flattened_tests when the chart needs per-test rows (histogram, box, scatter
   of individual tests)
6. Alias every computed column to a clear name (AS pass_rate, AS failure_count) —
   the renderer resolves the measure by column name
7. If the request is genuinely impossible against these tables →
   SELECT status, COUNT(*) AS count FROM flattened_tests GROUP BY status

SQL:"""


# ---------------------------------------------------------------------------
# NOTE: the Plotly-code prompt and the per-type code templates that used to
# live here are gone. Charts are now built deterministically in
# services/chart_builder.py from services/chart_spec.py's parse — see the
# handlers.py module docstring for why. detect_chart_type() moved to
# chart_spec.parse(), which returns the measure, dimension, top-N and filters
# alongside the chart type instead of only the type.
# ---------------------------------------------------------------------------


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
    # Note: per-project (e.g. "FSA"/"HSA"/"WDH") and per-module (e.g.
    # "eligibility") keyword lookups are handled dynamically by
    # schema_context.build_entity_filter_sql() in handlers._fallback_sql,
    # which matches against whatever project/module values actually exist
    # in the ingested data rather than a fixed hardcoded set.
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
    # A bare mention of a specific project code (whatever this dataset's
    # actual project names are) is handled dynamically by
    # schema_context.build_entity_filter_sql() in handlers._fallback_sql.
    r"\bproject\b": (
        "SELECT project_name, platform_type,"
        " ROUND(pass_rate, 1) AS pass_rate, total_tests, passed, failed"
        " FROM project_metrics ORDER BY project_name, platform_type"
    ),
}