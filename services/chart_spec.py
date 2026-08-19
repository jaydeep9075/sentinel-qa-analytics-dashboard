"""
chart_spec.py — Deterministic chart-intent parsing.

The old `prompts.detect_chart_type()` answered exactly one question ("which of
8 chart types?") from a flat keyword list, and threw away everything else the
user said. That is why charts came back generically correct but rarely
*answered the prompt*: "top 5 slowest modules on mobile" and "modules" both
collapsed to chart_type="bar" with no N, no measure, no filter.

This module parses the prompt ONCE into a `ChartSpec` carrying everything
downstream needs:

    chart_type   what to draw (17 types, reconcilable against real data shape)
    measure      which numeric idea the user asked about (pass_rate/failed/...)
    dimension    what to break it down by (module/project/platform/status/...)
    breakdown    an optional second grouping (-> grouped/stacked series)
    limit        explicit "top 5" / "10 worst", else a sane per-type default
    direction    highest | lowest | none
    filters      status/platform constraints stated in the prompt
    emphasis     what the chart should visually call out (target line, worst bar)

Everything is regex/keyword driven — no LLM call, so it is free, instant, and
identical for identical prompts. The LLM's job shrinks to writing SQL, which
is the part it is actually good at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Ordered most-specific-first; the first hit wins.
_CHART_TYPE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    # --- explicitly named chart types (user said the words) ---
    ("treemap", ("treemap", "tree map", "tree-map")),
    ("sunburst", ("sunburst", "sun burst", "hierarchy chart", "hierarchical breakdown")),
    ("funnel", ("funnel chart", "funnel graph", "funnel view", "drop off", "drop-off")),
    ("waterfall", ("waterfall",)),
    ("gauge", ("gauge", "speedometer", "kpi card", "single number", "score card", "scorecard")),
    ("radar", ("radar chart", "spider chart", "radar plot", "spider plot")),
    ("box", ("box plot", "boxplot", "box-plot", "distribution spread", "quartile", "iqr", "outlier spread")),
    ("histogram", ("histogram", "frequency distribution", "duration buckets", "bucketed")),
    ("heatmap", ("heatmap", "heat map", "heat-map", "matrix", "cross tab", "crosstab")),
    ("bubble", ("bubble chart", "bubble plot")),
    ("scatter", ("scatter", "dot plot", "correlation between", "vs each other")),
    ("area", ("area chart", "area graph", "stacked area", "filled line")),
    ("donut", ("donut", "doughnut")),
    ("pie", ("pie chart", "pie graph", "pie of", "as a pie")),
    ("stacked_bar", ("stacked bar", "stacked column", "stack the", "stacked chart")),
    ("horizontal_bar", ("horizontal bar", "horizontal chart", "bar across", "ranked bar")),
    ("line", ("line chart", "line graph", "trend line", "over time", "timeline",
              "over builds", "build over build", "across builds", "trajectory")),
    ("bar", ("bar chart", "bar graph", "column chart", "grouped bar")),
]

# Semantic fallbacks — the user described a *question shape* rather than naming
# a chart. These fire only if nothing above matched.
_SEMANTIC_TYPE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("line", ("trend", "trending", "over the last", "progression", "history of", "evolution")),
    ("platform_comparison", ("mobile vs desktop", "desktop vs mobile", "platform comparison",
                             "compare platform", "platform split", "by platform",
                             "across platforms", "per platform")),
    ("donut", ("share of", "proportion", "percentage split", "composition", "makeup", "make up")),
    ("pie", ("split between", "ratio of",)),
    ("horizontal_bar", ("slowest", "fastest", "longest", "shortest", "top offender",
                        "worst performing", "best performing", "ranked by", "ranking",
                        "leaderboard", "top ", "bottom ")),
    ("heatmap", ("by module and", "by project and", "module and platform",
                 "project and module", "cross-section")),
    ("scatter", ("relationship between", "correlate", "correlation")),
    ("bar", ("distribution", "breakdown", "count of", "how many", "failures by",
             "pass rate by", "per module", "per project", "by module", "by project",
             "by status", "by browser", "compare")),
]

# A measure is the numeric idea being plotted. `columns` lists the DB column
# names that satisfy it, best-first — the SQL layer and the renderer both
# resolve against the frame's real columns using this order.
_MEASURES: dict[str, dict] = {
    "pass_rate": {
        "keywords": ("pass rate", "passing rate", "success rate", "pass %", "pass percent",
                     "pass percentage", "health", "quality score"),
        "columns": ("pass_rate", "passed"),
        "label": "Pass rate",
        "unit": "%",
        "good_direction": "high",
    },
    "fail_rate": {
        "keywords": ("fail rate", "failure rate", "failing rate", "fail %", "failure percent"),
        "columns": ("fail_rate", "failure_rate", "failed"),
        "label": "Failure rate",
        "unit": "%",
        "good_direction": "low",
    },
    "failed": {
        "keywords": ("failed", "failure", "failures", "failing", "broken", "red tests"),
        "columns": ("failed", "failure_count", "failed_count", "failures", "count"),
        "label": "Failed tests",
        "unit": "",
        "good_direction": "low",
    },
    "passed": {
        "keywords": ("passed", "passing", "green tests", "pass count"),
        "columns": ("passed", "passed_count", "count"),
        "label": "Passed tests",
        "unit": "",
        "good_direction": "high",
    },
    "skipped": {
        "keywords": ("skipped", "skip count", "not run", "unexecuted"),
        "columns": ("skipped", "skipped_count", "count"),
        "label": "Skipped tests",
        "unit": "",
        "good_direction": "low",
    },
    "duration": {
        "keywords": ("duration", "slow", "slowest", "fast", "fastest", "runtime",
                     "execution time", "how long", "time taken", "elapsed", "longest"),
        "columns": ("duration_sec", "duration", "avg_duration_seconds",
                    "total_duration_seconds", "avg_duration", "total_duration"),
        "label": "Duration (s)",
        "unit": "s",
        "good_direction": "low",
    },
    "total_tests": {
        "keywords": ("total tests", "test count", "number of tests", "how many tests",
                     "volume", "coverage", "test volume"),
        "columns": ("total_tests", "total", "count", "test_count"),
        "label": "Tests",
        "unit": "",
        "good_direction": "high",
    },
}

# A dimension is what the measure is broken down by.
_DIMENSIONS: dict[str, dict] = {
    "module": {
        "keywords": ("module", "modules", "feature", "features", "area", "areas", "suite", "suites"),
        "columns": ("module_name", "module"),
        "label": "Module",
    },
    "project": {
        "keywords": ("project", "projects", "app", "application", "product"),
        "columns": ("project_name", "project"),
        "label": "Project",
    },
    "platform": {
        "keywords": ("platform", "platforms", "mobile", "desktop", "device"),
        "columns": ("platform_type", "platform"),
        "label": "Platform",
    },
    "status": {
        "keywords": ("status", "outcome", "result", "passed vs failed", "pass vs fail",
                     "pass/fail", "state"),
        "columns": ("status", "result", "outcome"),
        "label": "Status",
    },
    "browser": {
        "keywords": ("browser", "browsers", "chrome", "firefox", "safari", "edge",
                     "iphone", "ipad", "android"),
        "columns": ("browser", "browser_name"),
        "label": "Browser",
    },
    "test": {
        "keywords": ("test", "tests", "test case", "test cases", "spec", "specs", "scenario"),
        "columns": ("test_name", "title", "spec_file", "test"),
        "label": "Test",
    },
    "build": {
        "keywords": ("build", "builds", "run", "runs", "release", "releases", "over time"),
        "columns": ("build_date", "build_id", "executed_at", "ingested_at", "date"),
        "label": "Build",
    },
}

_STATUS_FILTER_WORDS = {
    "failed": ("failed", "failing", "failures", "broken", "red"),
    "passed": ("passed", "passing", "green"),
    "skipped": ("skipped", "not run"),
}

_PLATFORM_FILTER_WORDS = {
    "mobile": ("mobile", "iphone", "ipad", "android", "phone", "tablet"),
    "desktop": ("desktop", "web browser", "on desktop"),
}

# Per-type sensible category counts. A pie with 30 slices is unreadable; a
# ranked bar with 4 bars wastes the canvas. These are the defaults used when
# the user did not say "top N" themselves.
_DEFAULT_LIMITS: dict[str, int] = {
    "pie": 8,
    "donut": 8,
    "funnel": 8,
    "gauge": 1,
    "radar": 8,
    "treemap": 25,
    "sunburst": 40,
    "horizontal_bar": 15,
    "bar": 20,
    "stacked_bar": 20,
    "line": 40,
    "area": 40,
    "heatmap": 40,
    "scatter": 200,
    "bubble": 150,
    "box": 500,
    "histogram": 1000,
    "waterfall": 15,
    "platform_comparison": 6,
}

_MAX_LIMIT = 500


@dataclass
class ChartSpec:
    """Everything the SQL writer and the renderer need, parsed once."""

    prompt: str
    chart_type: str = "bar"
    measure: Optional[str] = None
    measure2: Optional[str] = None     # second axis for scatter/bubble ("x vs y")
    dimension: Optional[str] = None
    breakdown: Optional[str] = None
    limit: int = 20
    direction: str = "none"            # highest | lowest | none
    filters: dict = field(default_factory=dict)
    explicit_type: bool = False        # user literally named the chart type
    explicit_limit: bool = False       # user literally said "top 5"
    wants_percent: bool = False
    is_cross_build: bool = False

    # --- convenience accessors -------------------------------------------

    @property
    def measure_meta(self) -> dict:
        return _MEASURES.get(self.measure or "", {})

    @property
    def dimension_meta(self) -> dict:
        return _DIMENSIONS.get(self.dimension or "", {})

    @property
    def measure_label(self) -> str:
        return self.measure_meta.get("label", "Value")

    @property
    def measure_unit(self) -> str:
        return self.measure_meta.get("unit", "")

    @property
    def good_direction(self) -> str:
        """'high' if a bigger number is better, 'low' if smaller is better."""
        return self.measure_meta.get("good_direction", "high")

    def measure_columns(self) -> tuple:
        return tuple(self.measure_meta.get("columns", ()))

    def measure2_columns(self) -> tuple:
        return tuple(_MEASURES.get(self.measure2 or "", {}).get("columns", ()))

    def measure2_label(self) -> str:
        return _MEASURES.get(self.measure2 or "", {}).get("label", "")

    def resolve_measure2_column(self, columns) -> Optional[str]:
        cols = list(columns)
        for candidate in self.measure2_columns():
            if candidate in cols:
                return candidate
        return None

    def dimension_columns(self) -> tuple:
        return tuple(self.dimension_meta.get("columns", ()))

    def resolve_measure_column(self, columns) -> Optional[str]:
        """First column of the frame that satisfies this spec's measure."""
        cols = list(columns)
        for candidate in self.measure_columns():
            if candidate in cols:
                return candidate
        return None

    def resolve_dimension_column(self, columns) -> Optional[str]:
        cols = list(columns)
        for candidate in self.dimension_columns():
            if candidate in cols:
                return candidate
        return None

    def describe(self) -> str:
        """Short human summary, used in logs and chart subtitles."""
        bits = [self.chart_type]
        if self.measure:
            bits.append(self.measure_label.lower())
        if self.dimension:
            bits.append(f"by {self.dimension_meta.get('label', self.dimension).lower()}")
        if self.direction != "none":
            bits.append(f"({self.direction} {self.limit})")
        for col, val in self.filters.items():
            bits.append(f"[{col}={val}]")
        return " ".join(bits)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _match_keyword(text: str, keywords) -> bool:
    for kw in keywords:
        if " " in kw or kw.endswith(" "):
            if kw in text:
                return True
        elif re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
            return True
    return False


def _detect_type(p: str) -> tuple[str, bool]:
    """Returns (chart_type, was_explicitly_named)."""
    for chart_type, keywords in _CHART_TYPE_PATTERNS:
        if _match_keyword(p, keywords):
            return chart_type, True
    for chart_type, keywords in _SEMANTIC_TYPE_PATTERNS:
        if _match_keyword(p, keywords):
            return chart_type, False
    return "bar", False


def detect_all_measures(prompt: str) -> list[str]:
    """Every measure named in the prompt, in the order the user said them.
    'duration vs pass rate' -> ['duration', 'pass_rate'], which is what lets a
    scatter put the right thing on each axis instead of grabbing whichever
    numeric column happened to come back first."""
    p = (prompt or "").lower()
    hits: list[tuple[int, int, str]] = []   # (position, -keyword_len, measure)
    for name, meta in _MEASURES.items():
        best_pos, best_len = None, 0
        for kw in meta["keywords"]:
            m = re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", p)
            if m and len(kw) > best_len:
                best_pos, best_len = m.start(), len(kw)
        if best_pos is not None:
            hits.append((best_pos, -best_len, name))
    hits.sort()
    return [name for _, _, name in hits]


def _detect_measure(p: str) -> Optional[str]:
    """Longest keyword wins, so 'pass rate' beats bare 'passed'."""
    best: Optional[str] = None
    best_len = 0
    for name, meta in _MEASURES.items():
        for kw in meta["keywords"]:
            if _match_keyword(p, (kw,)) and len(kw) > best_len:
                best, best_len = name, len(kw)
    return best


def _detect_dimension(p: str, exclude: Optional[str] = None) -> Optional[str]:
    """Prefer an explicit 'by X' / 'per X' phrasing, then any mention."""
    for name, meta in _DIMENSIONS.items():
        if name == exclude:
            continue
        for kw in meta["keywords"]:
            if re.search(rf"\b(?:by|per|across|for each|group(?:ed)? by)\s+(?:the\s+)?{re.escape(kw)}\b", p):
                return name
    best: Optional[str] = None
    best_len = 0
    for name, meta in _DIMENSIONS.items():
        if name == exclude:
            continue
        for kw in meta["keywords"]:
            if _match_keyword(p, (kw,)) and len(kw) > best_len:
                best, best_len = name, len(kw)
    return best


def _detect_limit(p: str) -> tuple[Optional[int], str]:
    """Returns (explicit_limit_or_None, direction)."""
    direction = "none"
    if re.search(r"\b(top|highest|best|most|max|maximum|largest|greatest)\b", p):
        direction = "highest"
    if re.search(r"\b(bottom|lowest|worst|least|min|minimum|smallest|fewest)\b", p):
        # "worst" wins over "top" in "top 5 worst" — the user means bottom 5.
        direction = "lowest"

    # "slowest"/"longest" are a highest-duration ask; "fastest" is lowest.
    if re.search(r"\b(slowest|longest)\b", p):
        direction = "highest"
    elif re.search(r"\b(fastest|shortest|quickest)\b", p):
        direction = "lowest"

    m = (
        re.search(r"\b(?:top|bottom|first|last)\s+(\d{1,3})\b", p)
        or re.search(r"\b(\d{1,3})\s+(?:highest|lowest|best|worst|slowest|fastest|most|least)\b", p)
        or re.search(r"\b(?:top|bottom)\s*[-]?\s*(\d{1,3})\b", p)
    )
    if m:
        return max(1, min(_MAX_LIMIT, int(m.group(1)))), direction
    return None, direction


# Phrasings that mean "compare across these values", not "restrict to one of
# them". "mobile vs desktop pass rate" names both platforms; reading that as
# `WHERE platform_type='mobile'` answers a narrower question than was asked.
_COMPARISON_MARKERS = (" vs ", " vs. ", " versus ", "compare", "comparison",
                       "against each other", "side by side", "difference between",
                       "by platform", "per platform", "across platform",
                       "each platform", "both platform")


def _is_comparison_over(p: str, words_by_value: dict) -> bool:
    """True when the prompt names two or more of a dimension's values, or
    explicitly asks to compare across it."""
    named = sum(1 for words in words_by_value.values() if _match_keyword(p, words))
    if named >= 2:
        return True
    return any(marker in p for marker in _COMPARISON_MARKERS)


def _detect_filters(p: str, measure: Optional[str] = None) -> dict:
    """Row filters the prompt genuinely states. Deliberately conservative: a
    false filter here silently narrows the SQL and produces a chart that looks
    right and answers the wrong question, which is worse than missing one."""
    filters: dict = {}

    for status, words in _STATUS_FILTER_WORDS.items():
        if not _match_keyword(p, words):
            continue
        # "failures by module" / "top 5 modules by failed tests" use the status
        # word as the MEASURE being counted, not as a row filter. Only an
        # explicit restricting phrase makes it a filter.
        if measure in ("failed", "passed", "skipped", "fail_rate") and \
                not re.search(r"\b(only|just|among|of the)\b", p):
            break
        if re.search(rf"\b(only|just|which|list|show|of the|among)\b[^.]*\b{words[0]}\b", p) \
                or re.search(rf"\b{words[0]}\s+tests?\b", p):
            filters["status"] = status
        break

    if not _is_comparison_over(p, _PLATFORM_FILTER_WORDS):
        for platform, words in _PLATFORM_FILTER_WORDS.items():
            if _match_keyword(p, words):
                filters["platform_type"] = platform
                break

    return filters


_CROSS_BUILD_PHRASES = (
    "over time", "over builds", "across builds", "build over build", "build-over-build",
    "previous build", "last build", "past builds", "build history", "recent builds",
    "trend over", "last few builds", "since last release", "compare builds",
)


def parse(prompt: str) -> ChartSpec:
    """Parse a natural-language chart request into a ChartSpec."""
    raw = prompt or ""
    p = raw.lower().strip()

    chart_type, explicit_type = _detect_type(p)
    measure = _detect_measure(p)
    dimension = _detect_dimension(p)
    breakdown = None

    # A second dimension only makes sense for types that can carry series, and
    # ONLY when the user actually asked for one. Auto-splitting "failures by
    # module" into a per-platform stack answers a question nobody asked and
    # doubles the ink; if a breakdown column exists but wasn't requested, the
    # renderer aggregates over it instead.
    if dimension and chart_type in ("bar", "stacked_bar", "line", "area", "heatmap",
                                    "scatter", "bubble", "treemap", "sunburst"):
        breakdown = _detect_dimension(p, exclude=dimension)

    # Scatter/bubble are the one form that plots two measures against each
    # other, so "duration vs pass rate" has to keep both, in the stated order.
    measures = detect_all_measures(raw)
    measure2 = None
    if chart_type in ("scatter", "bubble") and len(measures) >= 2:
        measure, measure2 = measures[0], measures[1]

    explicit_limit, direction = _detect_limit(p)
    limit = explicit_limit if explicit_limit is not None else _DEFAULT_LIMITS.get(chart_type, 20)

    filters = _detect_filters(p, measure=measure)
    is_cross_build = any(phrase in p for phrase in _CROSS_BUILD_PHRASES)

    # Cross-build phrasing implies a time axis whatever the wording suggested,
    # unless the user explicitly asked for something else (e.g. "heatmap of
    # failures across builds" — they named heatmap, honour it).
    if is_cross_build and not explicit_type:
        chart_type = "line"
        dimension = "build"

    # A measure with an inherent good/bad direction and no stated dimension
    # still needs one — default to module, the most actionable QA grouping.
    if measure and not dimension and chart_type not in ("gauge", "histogram", "box"):
        dimension = "module"

    wants_percent = bool(measure and _MEASURES.get(measure, {}).get("unit") == "%") or \
        any(k in p for k in ("percent", "percentage", "%", "share of", "proportion"))

    spec = ChartSpec(
        prompt=raw,
        chart_type=chart_type,
        measure=measure,
        measure2=measure2,
        dimension=dimension,
        breakdown=breakdown if breakdown != dimension else None,
        limit=limit,
        direction=direction,
        filters=filters,
        explicit_type=explicit_type,
        explicit_limit=explicit_limit is not None,
        wants_percent=wants_percent,
        is_cross_build=is_cross_build,
    )
    return spec


# ---------------------------------------------------------------------------
# Reconciliation against the data that actually came back
# ---------------------------------------------------------------------------

# Types whose data requirements can't be faked; if the frame can't support
# them we downgrade rather than render something broken or misleading.
def reconcile(spec: ChartSpec, df) -> ChartSpec:
    """Adjust a parsed spec to what the returned dataframe can actually
    support. A requested type is honoured whenever the data allows it — this
    only intervenes when rendering as-asked would produce a wrong or empty
    chart (e.g. a pie of a column with 400 distinct values, or a scatter with
    only one numeric column)."""
    import pandas as pd  # local import: keeps this module import-cheap

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return spec

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in df.columns if c not in num_cols]
    n_rows = len(df)
    ct = spec.chart_type

    def _switch(new_type: str) -> ChartSpec:
        spec.chart_type = new_type
        spec.limit = min(spec.limit, _DEFAULT_LIMITS.get(new_type, spec.limit)) \
            if not spec.explicit_limit else spec.limit
        return spec

    # Part-of-whole types need exactly one category axis and one measure, and
    # become unreadable past ~12 slices. Beyond that a ranked bar is strictly
    # more informative, so switch rather than draw confetti.
    if ct in ("pie", "donut", "funnel", "radar"):
        if not num_cols or not cat_cols:
            return _switch("bar")
        if n_rows > 12 and not spec.explicit_limit:
            # Keep the type if the user named it — the builder will bucket the
            # tail into "Other". Only auto-chosen part-of-whole types downgrade.
            if not spec.explicit_type:
                return _switch("horizontal_bar")

    if ct in ("scatter", "bubble") and len(num_cols) < 2:
        return _switch("bar")

    if ct == "heatmap" and (len(cat_cols) < 2 or not num_cols):
        return _switch("bar")

    if ct in ("treemap", "sunburst") and not (cat_cols and num_cols):
        return _switch("bar")

    if ct in ("histogram", "box") and not num_cols:
        return _switch("bar")

    if ct == "gauge" and not num_cols:
        return _switch("bar")

    if ct in ("line", "area"):
        if not num_cols:
            return _switch("bar")
        # A "trend" over 3 unordered categories is not a trend; a bar is honest.
        if n_rows < 3 and not spec.explicit_type:
            return _switch("bar")

    if ct == "platform_comparison" and "platform_type" not in df.columns:
        return _switch("bar")

    # A single row can't be a distribution — show the number instead.
    if n_rows == 1 and ct in ("bar", "horizontal_bar", "line", "area", "stacked_bar") \
            and len(num_cols) == 1 and not cat_cols:
        return _switch("gauge")

    # Many categories read far better lying down than crammed on the x axis.
    if ct == "bar" and n_rows > 12 and len(cat_cols) >= 1 and not spec.explicit_type:
        return _switch("horizontal_bar")

    return spec
