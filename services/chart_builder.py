"""
chart_builder.py — deterministic, high-quality Plotly figure construction.

Why this replaces the LLM-writes-Python path
--------------------------------------------
The old flow asked an LLM to emit Plotly code, then `exec()`'d it. That is the
worst of both worlds: it is the slowest and most expensive step in the request,
it fails in ways that are invisible until runtime, and the code it writes is
*generic* — `px.bar(df, x=..., y=...)` with a colour list. It cannot know that a
pass-rate chart wants a 95% target line, that 40 modules should become a
horizontal ranked bar, that a duration axis wants "s" suffixes, or that a
one-row result is a KPI number rather than a one-bar bar chart.

All of that is decidable from the ChartSpec plus the dataframe's actual shape,
so it is decided here — deterministically, in microseconds, identically every
time. The LLM keeps the one job it is genuinely better at: writing the SQL.

What this module guarantees for every figure it returns
  • the chart answers the parsed prompt (measure/dimension/top-N/filters honoured)
  • colour is assigned by JOB (identity / magnitude / state), never by rank,
    from a palette validated for colourblind separation in both themes
  • high-cardinality tails fold into a neutral "Other" instead of a 9th hue
  • values are directly readable — axis + labels + rich hover, never hover-only
  • it carries a table-view twin and a dark-theme variant in `layout.meta`
  • it states its own scope in a subtitle ("Top 15 of 42 modules · mobile only")
    so a chart can never silently answer a narrower question than it looks like
"""

from __future__ import annotations

import logging
import math
import re
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import chart_theme as T
from .chart_spec import ChartSpec

logger = logging.getLogger(__name__)

# Rendering caps. Past these a chart stops being readable and the table view is
# the honest answer, so we truncate and SAY SO in the subtitle rather than
# silently drawing 400 unlabelled bars.
_MAX_CATEGORIES = 40
_MAX_POINTS = 2000
_LABEL_BAR_THRESHOLD = 18   # direct-label bars at or below this count


# ---------------------------------------------------------------------------
# Column semantics
# ---------------------------------------------------------------------------

_PERCENT_COLUMNS = ("pass_rate", "fail_rate", "failure_rate", "rate", "percent",
                    "percentage", "pct", "coverage")
_DURATION_COLUMNS = ("duration", "duration_sec", "duration_seconds", "avg_duration",
                     "total_duration", "avg_duration_seconds", "total_duration_seconds",
                     "elapsed", "runtime")
_IDENTIFIER_COLUMNS = ("result_id", "id", "uuid", "index", "row_number", "rn")

_COLUMN_LABELS = {
    "module_name": "Module",
    "project_name": "Project",
    "platform_type": "Platform",
    "browser": "Browser",
    "test_name": "Test",
    "spec_file": "Spec file",
    "status": "Status",
    "pass_rate": "Pass rate",
    "fail_rate": "Failure rate",
    "failure_rate": "Failure rate",
    "failed": "Failed tests",
    "passed": "Passed tests",
    "skipped": "Skipped tests",
    "pending": "Pending",
    "unknown": "Unknown",
    "failure_count": "Failures",
    "failed_count": "Failures",
    "passed_count": "Passed",
    "total_tests": "Tests",
    "total": "Total",
    "count": "Count",
    "cnt": "Count",
    "module_count": "Modules",
    "duration": "Duration",
    "duration_sec": "Duration",
    "avg_duration_seconds": "Avg duration",
    "total_duration_seconds": "Total duration",
    "build_id": "Build",
    "build_date": "Build date",
    "executed_at": "Executed",
    "error": "Error",
    "rank_type": "Rank",
}


def humanize(column: str) -> str:
    """`module_name` → 'Module'. Falls back to title-cased words so an
    arbitrary ingested dataset still gets readable axis titles."""
    if not column:
        return ""
    if column in _COLUMN_LABELS:
        return _COLUMN_LABELS[column]
    words = re.sub(r"[_\-]+", " ", str(column)).strip()
    words = re.sub(r"\s+(id|name|type|sec|seconds)$", "", words, flags=re.IGNORECASE)
    return words[:1].upper() + words[1:] if words else str(column)


def is_percent_column(column: str) -> bool:
    c = str(column or "").lower()
    return any(k in c for k in _PERCENT_COLUMNS)


def is_duration_column(column: str) -> bool:
    c = str(column or "").lower()
    return any(k in c for k in _DURATION_COLUMNS)


def unit_for(column: str) -> str:
    if is_percent_column(column):
        return "%"
    if is_duration_column(column):
        return "s"
    return ""


def value_format(column: str) -> str:
    """Plotly d3-format string appropriate to the column's meaning."""
    if is_percent_column(column):
        return ".1f"
    if is_duration_column(column):
        return ".2f"
    return ",.0f"


def delta_unit(column: str) -> str:
    """The unit a DIFFERENCE between two values carries. A gap between two
    percentages is percentage *points*, not a percentage — writing "pass rate
    fell 4.2%" when it fell from 92.3 to 88.1 is a different (and wrong) claim
    than "fell 4.2 pts"."""
    if is_percent_column(column):
        return " pts"
    unit = unit_for(column)
    return unit if unit else ""


def format_value(value, column: str = "") -> str:
    """Python-side formatting for insight sentences."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v):
        return "n/a"
    if is_percent_column(column):
        return f"{v:.1f}%"
    if is_duration_column(column):
        return f"{v:.2f}s"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.2f}"


# ---------------------------------------------------------------------------
# Plan: which columns play which role in the final figure
# ---------------------------------------------------------------------------

class ChartPlan:
    """Resolved column roles + the prepared frame the renderer draws from."""

    def __init__(self):
        self.frame: pd.DataFrame = pd.DataFrame()
        self.category: Optional[str] = None    # the dimension axis
        self.measure: Optional[str] = None     # the primary numeric axis
        self.measure2: Optional[str] = None    # second numeric (scatter y / bubble size)
        self.series: Optional[str] = None      # breakdown -> multiple traces
        self.hover_extra: list[str] = []
        self.total_categories: int = 0
        self.truncated: bool = False
        self.other_bucketed: bool = False
        self.source_rows: int = 0
        self.scope_notes: list[str] = []
        self.category_order: list[str] = []


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """DuckDB → pandas sometimes hands back numeric columns as objects (e.g.
    DECIMAL). A column that is 'really' numeric but typed object silently
    disqualifies itself from every numeric-column check downstream, which is
    how a perfectly good measure ends up plotted as a category."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype != object:
            continue
        converted = pd.to_numeric(out[col], errors="coerce")
        non_null = out[col].notna().sum()
        if non_null and converted.notna().sum() >= non_null * 0.9:
            out[col] = converted
    return out


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [
        c for c in df.select_dtypes(include="number").columns
        if str(c).lower() not in _IDENTIFIER_COLUMNS
    ]


# Columns the builder adds to the working frame for its own use. They must
# never be mistaken for real data columns — a heatmap that picks `__label__`
# as one of its two axes is drawing the frame's internals.
_INTERNAL_COLUMNS = ("__label__", "__full__")


def _categorical_columns(df: pd.DataFrame) -> list[str]:
    num = set(df.select_dtypes(include="number").columns)
    return [c for c in df.columns if c not in num and c not in _INTERNAL_COLUMNS]


def _pick_measure(df: pd.DataFrame, spec: ChartSpec) -> Optional[str]:
    """Prefer the column the user actually asked about; only then fall back to
    a heuristic. This is the difference between 'failures by module' plotting
    `failed` and plotting whatever numeric column happened to be first."""
    explicit = spec.resolve_measure_column(df.columns)
    if explicit is not None and pd.api.types.is_numeric_dtype(df[explicit]):
        return explicit

    nums = _numeric_columns(df)
    if not nums:
        return None
    # Prefer a rate over a raw count when the prompt asked in percentage terms.
    if spec.wants_percent:
        for c in nums:
            if is_percent_column(c):
                return c
    preference = ("failure_count", "failed", "pass_rate", "count", "cnt",
                  "total_tests", "duration_sec", "duration", "total")
    for name in preference:
        if name in nums:
            return name
    return nums[0]


def _pick_category(df: pd.DataFrame, spec: ChartSpec, exclude: Optional[str]) -> Optional[str]:
    explicit = spec.resolve_dimension_column(df.columns)
    if explicit is not None and explicit != exclude:
        return explicit
    cats = [c for c in _categorical_columns(df) if c != exclude]
    if not cats:
        return None
    preference = ("module_name", "project_name", "status", "platform_type",
                  "browser", "test_name", "build_date", "build_id")
    for name in preference:
        if name in cats:
            return name
    # Otherwise the lowest-cardinality categorical reads best as an axis.
    return min(cats, key=lambda c: df[c].nunique())


def _pick_series(df: pd.DataFrame, spec: ChartSpec, used: set) -> Optional[str]:
    """The breakdown column that splits the chart into multiple traces.

    Only an EXPLICITLY requested breakdown qualifies. Auto-splitting whenever a
    `platform_type` column happens to be present turns "failures by module"
    into a two-series grouped bar the user never asked for — twice the marks,
    a legend for a distinction that isn't the question, and half the bar length
    for each module. When no breakdown was asked for, build_plan aggregates
    over the extra column instead, which is the honest single-series answer.

    A breakdown also has to be worth drawing: 2..MAX_SERIES distinct values. One
    value is a legend that says nothing; thirty is confetti."""
    if not spec.breakdown:
        return None
    for col in ChartSpec(prompt="", dimension=spec.breakdown).dimension_columns():
        if col in df.columns and col not in used:
            n = df[col].nunique(dropna=True)
            if 2 <= n <= T.MAX_SERIES:
                return col
    return None


_MAX_LABEL_CHARS = 44


def display_label(value) -> str:
    """Shorten a category value to something an axis tick can actually show.

    Real test identifiers look like
    `Platforms/SFRA/Perks Feature/FSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend
     @fsa_storefront @fsa-earnPointsBySpend TS_40: EarnPointsBySpend`
    — 150 characters of path and tags wrapping one meaningful name. Rendered
    verbatim it either consumes half the plot width as left margin or gets
    clipped to nothing. The full value stays in the hover tooltip and the table
    view, so nothing is lost; only the tick label is abbreviated."""
    s = str(value or "").strip()
    if not s:
        return s

    # `file/path.spec.ts#Actual Test Name` — the part after '#' is the name.
    if "#" in s:
        s = s.rsplit("#", 1)[-1].strip()
    elif "/" in s and len(s) > _MAX_LABEL_CHARS:
        s = s.rsplit("/", 1)[-1].strip()

    # Playwright-style @tags are metadata, not identity.
    s = re.sub(r"\s*@[\w\-.]+", "", s).strip()
    s = re.sub(r"\s+", " ", s)

    if len(s) <= _MAX_LABEL_CHARS:
        return s or str(value)[:_MAX_LABEL_CHARS]
    return s[: _MAX_LABEL_CHARS - 1].rstrip() + "…"


def _dedupe_labels(labels: pd.Series) -> pd.Series:
    """Two different categories must never collapse to the same tick label —
    that silently merges two bars in the reader's mind. Disambiguate collisions
    that shortening introduced."""
    seen: dict = {}
    out = []
    for value in labels:
        text = str(value)
        if text in seen:
            seen[text] += 1
            out.append(f"{text} ({seen[text]})")
        else:
            seen[text] = 1
            out.append(text)
    return pd.Series(out, index=labels.index)


def _combine_labels(df: pd.DataFrame, category: str, series: Optional[str]) -> pd.Series:
    """When a module name repeats across projects, the bare module name is an
    ambiguous axis label ('Login' appearing three times). Qualify it."""
    if category == "module_name" and "project_name" in df.columns \
            and series != "project_name" and df["project_name"].nunique() > 1:
        dupes = df.groupby(category)["project_name"].nunique()
        if (dupes > 1).any():
            combined = df[category].astype(str) + " · " + df["project_name"].astype(str)
            return _dedupe_labels(combined.map(display_label))
    return _dedupe_labels(df[category].astype(str).map(display_label))


def build_plan(df: pd.DataFrame, spec: ChartSpec) -> ChartPlan:
    """Resolve roles, then shape the frame: aggregate duplicates, sort, cap
    cardinality, and fold the tail into 'Other' where the chart type is
    part-of-whole."""
    plan = ChartPlan()
    plan.source_rows = len(df)

    work = _coerce_numeric(df.dropna(how="all"))
    work = work.loc[:, [c for c in work.columns if work[c].notna().any()]]
    if work.empty:
        plan.frame = work
        return plan

    measure = _pick_measure(work, spec)
    plan.measure = measure

    if spec.chart_type in ("scatter", "bubble"):
        # Scatter needs two independent measures. Prefer the second one the
        # user actually named ("duration vs pass rate"), not just whichever
        # other numeric column came back first.
        explicit2 = spec.resolve_measure2_column(work.columns)
        if explicit2 is not None and explicit2 != measure \
                and pd.api.types.is_numeric_dtype(work[explicit2]):
            plan.measure2 = explicit2
        else:
            nums = [c for c in _numeric_columns(work) if c != measure]
            plan.measure2 = nums[0] if nums else None

    exclude = measure
    category = _pick_category(work, spec, exclude=exclude)
    plan.category = category

    used = {c for c in (measure, plan.measure2, category) if c}
    if spec.chart_type not in ("gauge", "histogram", "box", "pie", "donut", "funnel"):
        plan.series = _pick_series(work, spec, used)
        if plan.series:
            used.add(plan.series)

    # Anything else numeric/short-text is worth surfacing on hover — that is
    # free context that costs no ink.
    plan.hover_extra = [
        c for c in work.columns
        if c not in used and c != "error" and work[c].nunique() > 1
    ][:4]

    # --- shape the frame -------------------------------------------------
    if category and measure and spec.chart_type not in ("histogram", "box", "scatter", "bubble"):
        group_cols = [c for c in (category, plan.series) if c]
        if work.duplicated(subset=group_cols).any():
            agg = {measure: "sum" if not is_percent_column(measure) else "mean"}
            for c in plan.hover_extra:
                if pd.api.types.is_numeric_dtype(work[c]):
                    agg[c] = "mean" if is_percent_column(c) else "sum"
                else:
                    agg[c] = "first"
            work = work.groupby(group_cols, dropna=False, as_index=False).agg(agg)

        totals = work.groupby(category, dropna=False)[measure].sum()
        plan.total_categories = len(totals)

        # Sort order carries meaning: an explicit highest/lowest ask sorts by
        # the measure; a time axis sorts chronologically; otherwise rank by
        # magnitude, which is what makes a bar chart readable at a glance.
        if category in ("build_date", "build_id", "executed_at") or spec.dimension == "build":
            order = sorted(totals.index.tolist(), key=lambda v: str(v))
        elif spec.direction == "lowest":
            order = totals.sort_values(ascending=True).index.tolist()
        else:
            order = totals.sort_values(ascending=False).index.tolist()

        limit = min(spec.limit, _MAX_CATEGORIES)
        if len(order) > limit:
            keep = order[:limit]
            if spec.chart_type in ("pie", "donut", "treemap", "funnel", "radar"):
                # Part-of-whole: the tail MUST be represented or the shares lie.
                tail = work[~work[category].isin(keep)]
                head = work[work[category].isin(keep)].copy()
                if not tail.empty:
                    other = {category: T.OTHER_LABEL, measure: tail[measure].sum()}
                    if plan.series:
                        other[plan.series] = T.OTHER_LABEL
                    head = pd.concat([head, pd.DataFrame([other])], ignore_index=True)
                    plan.other_bucketed = True
                work = head
                order = keep + ([T.OTHER_LABEL] if plan.other_bucketed else [])
            else:
                work = work[work[category].isin(keep)]
                order = keep
                plan.truncated = True

        # A horizontal bar axis grows upward, so the FIRST category lands at the
        # bottom. Feeding it a descending ranking therefore prints the biggest
        # bar at the bottom — the exact opposite of how a ranked list reads.
        if spec.chart_type == "horizontal_bar":
            order = list(reversed(order))

        work[category] = pd.Categorical(work[category].astype(str),
                                        categories=[str(o) for o in order], ordered=True)
        work = work.sort_values(category)
        # `__label__` is the abbreviated tick label; `__full__` keeps the
        # untouched value so hover and the table view still show it in full.
        work["__full__"] = work[category].astype(str)
        work["__label__"] = _combine_labels(work, category, plan.series)
        # Pin the axis order explicitly rather than relying on trace order —
        # with several traces (grouped/stacked) plotly otherwise derives the
        # order from whichever trace mentioned a category first.
        plan.category_order = list(dict.fromkeys(work["__label__"].astype(str)))
    elif measure is not None:
        plan.total_categories = work[category].nunique() if category else 0
        if len(work) > _MAX_POINTS:
            work = work.nlargest(_MAX_POINTS, measure)
            plan.truncated = True
        if category:
            work["__full__"] = work[category].astype(str)
            work["__label__"] = _dedupe_labels(work["__full__"].map(display_label))

    plan.frame = work.reset_index(drop=True)

    if spec.filters:
        for col, val in spec.filters.items():
            plan.scope_notes.append(f"{humanize(col).lower()}: {val}")

    return plan


# ---------------------------------------------------------------------------
# Colour assignment
# ---------------------------------------------------------------------------

def _series_colors(values) -> tuple[list[str], list]:
    """Returns (colors, slots). `slots` is what the frontend uses to re-theme:
    an int index into the palette, or a 'status:<role>' string for reserved
    status colours (which are mode-invariant), or None for the Other bucket."""
    colors: list[str] = []
    slots: list = []
    use_status = T.is_status_column(values)
    for i, v in enumerate(values):
        if str(v) == T.OTHER_LABEL:
            colors.append(T.OTHER_LIGHT)
            slots.append("other")
            continue
        if use_status:
            c = T.status_color(v)
            if c:
                colors.append(c)
                slots.append(f"status:{T.status_role(v)}")
                continue
        idx = i % T.MAX_SERIES
        colors.append(T.PALETTE_LIGHT[idx])
        slots.append(idx)
    return colors, slots


def _single_series_color(plan: ChartPlan) -> tuple[str, object]:
    """One series → one colour. Colouring every bar differently when there is
    only one series burns the identity channel on information the bar length
    already carries (and is an explicit anti-pattern)."""
    if plan.category and T.is_status_column(plan.frame[plan.category].astype(str).unique()):
        return None, None  # caller will colour per-status instead
    return T.PALETTE_LIGHT[0], 0


# ---------------------------------------------------------------------------
# Hover
# ---------------------------------------------------------------------------

def _hover_template(label_title: str, measure: str, extras: list[str]) -> str:
    fmt = value_format(measure)
    unit = unit_for(measure)
    lines = [
        "<b>%{customdata[0]}</b>",
        f"{humanize(measure)}: %{{customdata[1]:{fmt}}}{unit}",
    ]
    for i, col in enumerate(extras, start=2):
        cfmt = value_format(col)
        cunit = unit_for(col)
        lines.append(f"{humanize(col)}: %{{customdata[{i}]:{cfmt}}}{cunit}")
    return "<br>".join(lines) + "<extra></extra>"


def _hover_labels(frame: pd.DataFrame, fallback) -> pd.Series:
    """Hover shows the FULL category value even when the axis tick was
    abbreviated — the tooltip has room, so nothing needs to be lost."""
    if "__full__" in frame.columns:
        return frame["__full__"].astype(str)
    return pd.Series(fallback).astype(str)


def _customdata(frame: pd.DataFrame, labels, measure: str, extras: list[str]) -> np.ndarray:
    cols = [_hover_labels(frame, labels).values, frame[measure].values]
    for col in extras:
        series = frame[col]
        cols.append(series.values if pd.api.types.is_numeric_dtype(series)
                    else series.astype(str).values)
    return np.array(cols, dtype=object).T


def _numeric_hover_extras(frame: pd.DataFrame, extras: list[str]) -> list[str]:
    """Hover formats assume numbers; a text column formatted with `,.0f`
    renders as a literal format string. Keep only what the template can format,
    plus short text columns which we format as plain strings."""
    keep = []
    for col in extras:
        if pd.api.types.is_numeric_dtype(frame[col]):
            keep.append(col)
    return keep[:3]


# ---------------------------------------------------------------------------
# Insight — the one sentence that makes a chart worth looking at
# ---------------------------------------------------------------------------

_PASS_RATE_TARGET = 95.0


def compute_insight(plan: ChartPlan, spec: ChartSpec) -> str:
    """A single data-derived takeaway, rendered as the chart's subtitle. Every
    number in it is computed from the frame being drawn — it can't drift from
    what the reader sees."""
    df, measure, category = plan.frame, plan.measure, plan.category
    if df is None or df.empty or not measure or measure not in df.columns:
        return ""

    values = pd.to_numeric(df[measure], errors="coerce").dropna()
    if values.empty:
        return ""

    labels = df["__label__"] if "__label__" in df.columns else (
        df[category].astype(str) if category else pd.Series(range(len(df)), dtype=str))

    measure_noun = humanize(measure).lower()
    if measure_noun in ("count", "total"):
        measure_noun = "records"

    try:
        # A heatmap's story is a CELL, not a row — "FSA leads" throws away the
        # column half of the very cross-section the reader asked for.
        if spec.chart_type == "heatmap":
            cats = _categorical_columns(df)
            if len(cats) >= 2:
                row_col, col_col = category or cats[0], next(c for c in cats if c != (category or cats[0]))
                hot = df.loc[values.idxmax()]
                total = float(values.sum())
                share = float(values.max()) / total * 100 if total else 0
                return (f"Hottest cell: {hot[row_col]} × {hot[col_col]} at "
                        f"{format_value(values.max(), measure)}"
                        + (f" ({share:.0f}% of all {measure_noun})." if total else "."))

        # Distribution forms: describe the spread, not a single leader — the
        # whole point of a histogram/box is the shape, and naming "the highest
        # bar" would describe the wrong thing entirely.
        if spec.chart_type == "histogram":
            median, p90 = float(values.median()), float(values.quantile(0.90))
            return (f"{len(values):,} values · median {format_value(median, measure)}, "
                    f"90th percentile {format_value(p90, measure)}, "
                    f"max {format_value(values.max(), measure)}.")

        if spec.chart_type == "box":
            q1, q3 = float(values.quantile(0.25)), float(values.quantile(0.75))
            iqr = q3 - q1
            outliers = int(((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).sum())
            return (f"Median {format_value(values.median(), measure)}, "
                    f"middle 50% between {format_value(q1, measure)} and "
                    f"{format_value(q3, measure)}"
                    + (f" · {outliers} outlier{'s' if outliers != 1 else ''}." if outliers else "."))

        if spec.chart_type in ("scatter", "bubble") and plan.measure2 \
                and plan.measure2 in df.columns:
            x = pd.to_numeric(df[measure], errors="coerce")
            y = pd.to_numeric(df[plan.measure2], errors="coerce")
            pair = pd.concat([x, y], axis=1).dropna()
            if len(pair) >= 3:
                r = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
                if not math.isnan(r):
                    strength = ("strong" if abs(r) >= 0.7 else
                                "moderate" if abs(r) >= 0.4 else "weak")
                    direction = "positive" if r > 0 else "negative"
                    return (f"{len(pair)} points · {strength} {direction} relationship "
                            f"between {humanize(measure).lower()} and "
                            f"{humanize(plan.measure2).lower()} (r = {r:.2f}).")
            return f"{len(pair)} points plotted."

        # Two groups: the gap between them is the whole story, and it beats a
        # generic "N below target" reading even for a percentage measure.
        if len(values) == 2:
            hi_idx, lo_idx = values.idxmax(), values.idxmin()
            gap = float(values.loc[hi_idx]) - float(values.loc[lo_idx])
            return (f"{labels.loc[hi_idx]} leads {labels.loc[lo_idx]} by "
                    f"{gap:.1f}{delta_unit(measure)} "
                    f"({format_value(values.loc[hi_idx], measure)} vs "
                    f"{format_value(values.loc[lo_idx], measure)}).")

        # Trend: first vs last along an ordered axis.
        if spec.chart_type in ("line", "area") and len(values) >= 3:
            first, last = float(values.iloc[0]), float(values.iloc[-1])
            delta = last - first
            word = "rose" if delta > 0 else "fell"
            if abs(delta) < 1e-9:
                return (f"{humanize(measure)} held flat at {format_value(last, measure)} "
                        f"across {len(values)} points.")
            return (f"{humanize(measure)} {word} {abs(delta):.1f}{delta_unit(measure)} "
                    f"across {len(values)} points — {format_value(first, measure)} → "
                    f"{format_value(last, measure)}.")

        # Pass-rate style: how many sit under the target, and who is worst.
        if is_percent_column(measure) and len(values) >= 2:
            below = int((values < _PASS_RATE_TARGET).sum())
            worst_idx = values.idxmin()
            worst_label = str(labels.loc[worst_idx]) if worst_idx in labels.index else "?"
            if below:
                return (f"{below} of {len(values)} below the {_PASS_RATE_TARGET:.0f}% target — "
                        f"lowest is {worst_label} at {format_value(values.loc[worst_idx], measure)}.")
            return (f"All {len(values)} are at or above the {_PASS_RATE_TARGET:.0f}% target "
                    f"(lowest {format_value(values.loc[worst_idx], measure)}).")

        # Part-of-whole: the share of the leading slice.
        if spec.chart_type in ("pie", "donut", "funnel", "treemap", "sunburst"):
            total = float(values.sum())
            if total > 0:
                top_idx = values.idxmax()
                share = float(values.loc[top_idx]) / total * 100
                top_label = str(labels.loc[top_idx]) if top_idx in labels.index else "?"
                return (f"{top_label} is {share:.1f}% of {format_value(total, measure)} "
                        f"{measure_noun} across {len(values)} groups.")

        # Ranked magnitude: leader vs the typical case is the actionable read.
        if len(values) >= 3:
            top_idx = values.idxmax()
            top_label = str(labels.loc[top_idx]) if top_idx in labels.index else "?"
            median = float(values.median())
            top_val = float(values.loc[top_idx])
            if median > 0 and top_val / median >= 1.5:
                return (f"{top_label} leads at {format_value(top_val, measure)} — "
                        f"{top_val / median:.1f}× the median of {format_value(median, measure)} "
                        f"across {len(values)} groups.")
            return (f"{top_label} is highest at {format_value(top_val, measure)}; "
                    f"median {format_value(median, measure)} across {len(values)} groups.")

        if len(values) == 1:
            return f"{humanize(measure)}: {format_value(values.iloc[0], measure)}."
    except Exception as exc:  # an insight is a bonus, never a failure mode
        logger.debug("insight computation skipped: %s", exc)
    return ""


def _scope_subtitle(plan: ChartPlan, spec: ChartSpec) -> str:
    """States what the chart is and is NOT showing, so a truncated or filtered
    chart can never be mistaken for the whole picture."""
    bits: list[str] = []
    if plan.truncated and plan.total_categories:
        direction = "lowest" if spec.direction == "lowest" else "top"
        bits.append(f"{direction} {len(plan.frame[plan.category].unique())} "
                    f"of {plan.total_categories} {humanize(plan.category).lower()}s")
    elif plan.other_bucketed:
        bits.append(f"top {spec.limit} of {plan.total_categories} shown, rest grouped as Other")
    elif plan.total_categories:
        bits.append(f"{plan.total_categories} {humanize(plan.category).lower()}s")
    bits.extend(plan.scope_notes)
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _bar_gap(plan: ChartPlan) -> float:
    n = len(plan.category_order) or len(plan.frame) or 1
    if n <= 2:
        return 0.70
    if n <= 4:
        return 0.58
    if n <= 8:
        return 0.42
    return 0.28


def _base_layout(title: str, subtitle: str, plan: ChartPlan, spec: ChartSpec) -> dict:
    c = T.CHROME_LIGHT
    layout: dict = {
        "template": "none",
        "autosize": True,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": T.FONT_STACK, "color": c["ink"], "size": 12},
        # Native subtitle rather than a paper-anchored annotation: an
        # annotation at x=0 anchors to the PLOT area while the title anchors to
        # the container, so the two silently drift out of alignment by exactly
        # the left margin. Plotly owns the alignment here instead.
        "title": {
            "text": title,
            "font": {"size": 16, "color": c["ink"], "family": T.FONT_STACK},
            "x": 0, "xref": "paper", "xanchor": "left", "y": 0.97, "yanchor": "top",
            "subtitle": {
                "text": subtitle,
                "font": {"size": 12, "color": c["ink_secondary"], "family": T.FONT_STACK},
            } if subtitle else None,
        },
        # Line/area charts direct-label their endpoint, which sits just past
        # the last point — without extra right margin the container crops it.
        "margin": {
            "l": 64,
            "r": 96 if spec.chart_type in ("line", "area") else 52,
            "t": 96 if subtitle else 68,
            "b": 72,
        },
        "hovermode": "closest",
        "hoverlabel": {
            "bgcolor": c["surface"],
            "bordercolor": c["border"],
            "font": {"family": T.FONT_STACK, "size": 12, "color": c["ink"]},
            "align": "left",
        },
        # Bar thickness is a function of how many bars there are. A fixed gap
        # turns a two-category comparison into two enormous saturated slabs —
        # loud, and the "thick block" anti-pattern. Widen the gap as the
        # category count drops so marks stay thin at any cardinality.
        "bargap": _bar_gap(plan),
        "bargroupgap": 0.08,
        "colorway": T.PALETTE_LIGHT,
        "showlegend": False,
        "annotations": [],
    }

    return layout


def _axis(title: str, chrome: dict, *, is_category: bool = False,
          percent: bool = False, unit: str = "") -> dict:
    axis = {
        "title": {"text": title, "font": {"size": 12, "color": chrome["ink_secondary"]}},
        "tickfont": {"size": 11, "color": chrome["muted"], "family": T.FONT_STACK},
        "automargin": True,
        "zeroline": False,
        "linecolor": chrome["baseline"],
        "linewidth": 1,
        "showline": True,
    }
    if is_category:
        # Vertical gridlines on a category axis are noise — the bars already
        # separate the categories.
        axis["showgrid"] = False
    else:
        axis["showgrid"] = True
        axis["gridcolor"] = chrome["grid"]
        axis["gridwidth"] = 1
        axis["griddash"] = "solid"
    if percent:
        axis["ticksuffix"] = "%"
    elif unit:
        axis["ticksuffix"] = unit
    return axis


def _target_line(fig: go.Figure, measure: str, plan: ChartPlan, horizontal: bool) -> Optional[str]:
    """A dashed threshold rule where one genuinely exists — the 95% release
    gate for pass rate, the mean for durations. This is what turns 'a row of
    bars' into 'which ones are a problem', and it is dashed precisely BECAUSE
    it is a threshold rather than a gridline."""
    c = T.CHROME_LIGHT
    values = pd.to_numeric(plan.frame[measure], errors="coerce").dropna()
    if values.empty:
        return None

    if is_percent_column(measure):
        level, label, color = _PASS_RATE_TARGET, f"{_PASS_RATE_TARGET:.0f}% target", T.STATUS_COLORS["good"]
        if values.max() < level * 0.5:
            return None
    elif is_duration_column(measure) and len(values) >= 4:
        level = float(values.mean())
        label, color = f"mean {format_value(level, measure)}", c["muted"]
    else:
        return None

    line = {"color": color, "width": 1.5, "dash": "dash"}
    if horizontal:
        fig.add_vline(x=level, line=line, annotation_text=label,
                      annotation_position="top",
                      annotation_font={"size": 11, "color": color, "family": T.FONT_STACK})
    else:
        # "top right" hangs the label off the right edge of the plot area,
        # where the container clips it. Anchor it inside on the left instead.
        fig.add_hline(y=level, line=line, annotation_text=label,
                      annotation_position="top left",
                      annotation_font={"size": 11, "color": color, "family": T.FONT_STACK})
    return label


# ---------------------------------------------------------------------------
# Per-type renderers. Each returns a figure with traces only; layout/axes are
# applied by build_figure so theming stays in exactly one place.
# ---------------------------------------------------------------------------

def _labels_of(plan: ChartPlan) -> pd.Series:
    if "__label__" in plan.frame.columns:
        return plan.frame["__label__"].astype(str)
    if plan.category:
        return plan.frame[plan.category].astype(str)
    return pd.Series([str(i + 1) for i in range(len(plan.frame))])


def _render_bars(plan: ChartPlan, spec: ChartSpec, horizontal: bool, stacked: bool) -> go.Figure:
    fig = go.Figure()
    df, measure = plan.frame, plan.measure
    extras = _numeric_hover_extras(df, plan.hover_extra)
    fmt, unit = value_format(measure), unit_for(measure)
    show_labels = len(df) <= _LABEL_BAR_THRESHOLD

    if plan.series and plan.series in df.columns:
        series_values = list(dict.fromkeys(df[plan.series].astype(str)))[:T.MAX_SERIES]
        colors, slots = _series_colors(series_values)
        for name, color, slot in zip(series_values, colors, slots):
            sub = df[df[plan.series].astype(str) == name]
            if sub.empty:
                continue
            labels = sub["__label__"].astype(str) if "__label__" in sub.columns \
                else sub[plan.category].astype(str)
            cd = _customdata(sub, labels, measure, extras)
            fig.add_trace(go.Bar(
                name=str(name),
                x=sub[measure] if horizontal else labels,
                y=labels if horizontal else sub[measure],
                orientation="h" if horizontal else "v",
                marker={"color": color, "line": {"width": 0}},
                customdata=cd,
                hovertemplate=_hover_template(humanize(plan.category or ""), measure, extras),
                meta={"slot": slot},
            ))
    else:
        labels = _labels_of(plan)
        color, slot = _single_series_color(plan)
        if color is None:
            colors, slots = _series_colors(df[plan.category].astype(str))
            marker_color, marker_slot = colors, slots
        else:
            marker_color, marker_slot = color, slot
        cd = _customdata(df, labels, measure, extras)
        fig.add_trace(go.Bar(
            name=humanize(measure),
            x=df[measure] if horizontal else labels,
            y=labels if horizontal else df[measure],
            orientation="h" if horizontal else "v",
            marker={"color": marker_color, "line": {"width": 0}},
            text=[f"{v:{fmt}}{unit}" if pd.notna(v) else "" for v in df[measure]] if show_labels else None,
            textposition="outside" if show_labels else "none",
            textfont={"size": 11, "color": T.CHROME_LIGHT["ink_secondary"], "family": T.FONT_STACK},
            cliponaxis=False,
            customdata=cd,
            hovertemplate=_hover_template(humanize(plan.category or ""), measure, extras),
            meta={"slot": marker_slot},
        ))

    fig.update_layout(barmode="stack" if stacked else "group")
    return fig


def _render_line(plan: ChartPlan, spec: ChartSpec, filled: bool) -> go.Figure:
    fig = go.Figure()
    df, measure = plan.frame, plan.measure
    extras = _numeric_hover_extras(df, plan.hover_extra)

    def _add(sub: pd.DataFrame, name: str, color: str, slot, annotate: bool):
        labels = sub["__label__"].astype(str) if "__label__" in sub.columns \
            else (sub[plan.category].astype(str) if plan.category
                  else pd.Series(range(len(sub))).astype(str))
        cd = _customdata(sub, labels, measure, extras)
        fig.add_trace(go.Scatter(
            name=name,
            x=labels, y=sub[measure],
            mode="lines+markers",
            line={"width": 2, "color": color, "shape": "linear"},
            marker={"size": 8, "color": color,
                    "line": {"width": 2, "color": T.CHROME_LIGHT["surface"]}},
            fill="tozeroy" if filled else None,
            fillcolor=_alpha(color, 0.15) if filled else None,
            customdata=cd,
            hovertemplate=_hover_template(humanize(plan.category or ""), measure, extras),
            meta={"slot": slot},
        ))
        # Direct-label the endpoint only — a number on every point is chaos.
        if annotate and len(sub) >= 2:
            last_y = sub[measure].iloc[-1]
            if pd.notna(last_y):
                fig.add_annotation(
                    x=labels.iloc[-1], y=last_y,
                    text=f"{last_y:{value_format(measure)}}{unit_for(measure)}",
                    showarrow=False, xanchor="left", xshift=8,
                    font={"size": 11, "color": color, "family": T.FONT_STACK},
                )

    if plan.series and plan.series in df.columns:
        names = list(dict.fromkeys(df[plan.series].astype(str)))[:T.MAX_SERIES]
        colors, slots = _series_colors(names)
        for name, color, slot in zip(names, colors, slots):
            sub = df[df[plan.series].astype(str) == name]
            if not sub.empty:
                _add(sub, str(name), color, slot, annotate=len(names) <= 4)
    else:
        _add(df, humanize(measure), T.PALETTE_LIGHT[0], 0, annotate=True)
    return fig


def _alpha(hex_color: str, alpha: float) -> str:
    h = str(hex_color).lstrip("#")
    if len(h) != 6:
        return f"rgba(42,120,214,{alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _render_pie(plan: ChartPlan, spec: ChartSpec, hole: float) -> go.Figure:
    df, measure = plan.frame, plan.measure
    labels = _labels_of(plan)
    colors, slots = _series_colors(df[plan.category].astype(str) if plan.category else labels)
    fig = go.Figure(go.Pie(
        labels=labels, values=df[measure],
        hole=hole,
        sort=False,
        direction="clockwise",
        marker={"colors": colors,
                "line": {"width": 2, "color": T.CHROME_LIGHT["surface"]}},
        # Plotly's default percent formatting is 3 significant digits, which
        # prints a 0.342% sliver next to an 88.8% slice. Pin it to one decimal.
        texttemplate="%{label}<br>%{percent:.1%}",
        textposition="auto",
        insidetextorientation="horizontal",
        textfont={"size": 12, "family": T.FONT_STACK},
        hovertemplate=("<b>%{label}</b><br>" + humanize(measure) +
                       ": %{value:" + value_format(measure) + "}" + unit_for(measure) +
                       "<br>Share: %{percent}<extra></extra>"),
        meta={"slots": slots},
    ))
    if hole:
        total = pd.to_numeric(df[measure], errors="coerce").sum()
        fig.add_annotation(
            text=f"<b>{format_value(total, measure)}</b><br><span style='font-size:11px'>total</span>",
            x=0.5, y=0.5, showarrow=False,
            font={"size": 20, "color": T.CHROME_LIGHT["ink"], "family": T.FONT_STACK},
            name="center-total",
        )
    return fig


def _render_scatter(plan: ChartPlan, spec: ChartSpec, bubble: bool) -> go.Figure:
    fig = go.Figure()
    df = plan.frame
    x_col, y_col = plan.measure, plan.measure2 or plan.measure
    size_col = None
    if bubble:
        nums = [c for c in _numeric_columns(df) if c not in (x_col, y_col)]
        size_col = nums[0] if nums else None

    hover_name = plan.category if plan.category else None
    groups = [(None, df)]
    if plan.series and plan.series in df.columns:
        names = list(dict.fromkeys(df[plan.series].astype(str)))[:T.MAX_SERIES]
        groups = [(n, df[df[plan.series].astype(str) == n]) for n in names]
    colors, slots = _series_colors([g[0] for g in groups] if groups[0][0] is not None else [0])

    for i, (name, sub) in enumerate(groups):
        if sub.empty:
            continue
        color = colors[i] if name is not None else T.PALETTE_LIGHT[0]
        slot = slots[i] if name is not None else 0
        labels = sub[hover_name].astype(str) if hover_name else pd.Series(
            [f"row {j+1}" for j in range(len(sub))])
        marker = {
            "color": color, "opacity": 0.85,
            "line": {"width": 2, "color": T.CHROME_LIGHT["surface"]},
        }
        if size_col:
            sizes = pd.to_numeric(sub[size_col], errors="coerce").fillna(0)
            top = sizes.max() or 1
            marker["size"] = (sizes / top * 34 + 8).tolist()
            marker["sizemode"] = "diameter"
        else:
            marker["size"] = 10
        fig.add_trace(go.Scatter(
            name=str(name) if name is not None else humanize(y_col),
            x=sub[x_col], y=sub[y_col],
            mode="markers",
            marker=marker,
            customdata=np.array([
                labels.values,
                sub[x_col].values,
                sub[y_col].values,
            ], dtype=object).T,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>" +
                f"{humanize(x_col)}: %{{customdata[1]:{value_format(x_col)}}}{unit_for(x_col)}<br>" +
                f"{humanize(y_col)}: %{{customdata[2]:{value_format(y_col)}}}{unit_for(y_col)}" +
                "<extra></extra>"
            ),
            meta={"slot": slot},
        ))
    # Scatter owns its axes (both are measures), so it has to name them itself.
    fig.update_layout(
        xaxis={"title": {"text": humanize(x_col)},
               "ticksuffix": "%" if is_percent_column(x_col) else unit_for(x_col)},
        yaxis={"title": {"text": humanize(y_col)},
               "ticksuffix": "%" if is_percent_column(y_col) else unit_for(y_col)},
    )
    return fig


def _render_heatmap(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    df, measure = plan.frame, plan.measure
    cats = _categorical_columns(df)
    row_col = plan.category or cats[0]
    col_col = next((c for c in cats if c != row_col), None)
    if col_col is None:
        raise ValueError("heatmap needs two categorical columns")

    agg = "mean" if is_percent_column(measure) else "sum"
    pivot = df.pivot_table(index=row_col, columns=col_col, values=measure,
                           aggfunc=agg, fill_value=0)
    # Rank rows by total so the heaviest rows sit together — an unordered
    # heatmap hides exactly the clustering it exists to reveal.
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]

    fmt = value_format(measure)
    text = [[f"{v:{fmt}}{unit_for(measure)}" for v in row] for row in pivot.values]
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=[str(i) for i in pivot.index],
        colorscale=T.SEQUENTIAL_LIGHT,
        text=text,
        texttemplate="%{text}",
        textfont={"size": 11, "family": T.FONT_STACK},
        xgap=2, ygap=2,
        colorbar={
            "title": {"text": humanize(measure), "font": {"size": 11}},
            "thickness": 12, "outlinewidth": 0, "len": 0.85,
            "tickfont": {"size": 10, "color": T.CHROME_LIGHT["muted"]},
        },
        hovertemplate=(f"{humanize(row_col)}: %{{y}}<br>{humanize(col_col)}: %{{x}}<br>"
                       f"{humanize(measure)}: %{{z:{fmt}}}{unit_for(measure)}<extra></extra>"),
        meta={"scale": "sequential"},
    ))
    fig.update_layout(xaxis_title=humanize(col_col), yaxis_title=humanize(row_col))
    return fig


def _render_treemap(plan: ChartPlan, spec: ChartSpec, sunburst: bool) -> go.Figure:
    df, measure = plan.frame, plan.measure
    labels = _labels_of(plan)
    path_parent = None
    if plan.series and plan.series in df.columns:
        path_parent = df[plan.series].astype(str)

    ids = labels.tolist()
    parents = path_parent.tolist() if path_parent is not None else [""] * len(labels)

    if path_parent is not None:
        # Parent nodes have to exist as their own rows for a treemap to nest.
        for parent in dict.fromkeys(parents):
            ids.append(parent)
            parents.append("")
        vals = df[measure].tolist() + [0] * (len(ids) - len(df))
        branchvalues = "remainder"
    else:
        vals = df[measure].tolist()
        branchvalues = "total"

    colors, slots = _series_colors(labels)
    cls = go.Sunburst if sunburst else go.Treemap
    fig = go.Figure(cls(
        ids=ids, labels=ids, parents=parents, values=vals,
        branchvalues=branchvalues,
        marker={"colors": colors + [T.CHROME_LIGHT["grid"]] * (len(ids) - len(colors)),
                "line": {"width": 2, "color": T.CHROME_LIGHT["surface"]}},
        textinfo="label+value",
        textfont={"size": 12, "family": T.FONT_STACK},
        hovertemplate=(f"<b>%{{label}}</b><br>{humanize(measure)}: "
                       f"%{{value:{value_format(measure)}}}{unit_for(measure)}<extra></extra>"),
        meta={"slots": slots},
    ))
    return fig


def _render_funnel(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    df, measure = plan.frame, plan.measure
    labels = _labels_of(plan)
    ordered = df.sort_values(measure, ascending=False)
    ordered_labels = labels.loc[ordered.index]
    colors, slots = _series_colors(ordered_labels)
    fig = go.Figure(go.Funnel(
        y=ordered_labels, x=ordered[measure],
        marker={"color": colors, "line": {"width": 2, "color": T.CHROME_LIGHT["surface"]}},
        textinfo="value+percent initial",
        textfont={"size": 12, "family": T.FONT_STACK},
        hovertemplate=(f"<b>%{{y}}</b><br>{humanize(measure)}: "
                       f"%{{x:{value_format(measure)}}}{unit_for(measure)}<extra></extra>"),
        meta={"slots": slots},
    ))
    return fig


def _render_histogram(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    df, measure = plan.frame, plan.measure
    values = pd.to_numeric(df[measure], errors="coerce").dropna()
    fig = go.Figure(go.Histogram(
        x=values,
        marker={"color": T.PALETTE_LIGHT[0], "line": {"width": 2, "color": T.CHROME_LIGHT["surface"]}},
        nbinsx=min(30, max(8, int(math.sqrt(len(values))) or 8)),
        hovertemplate=(f"{humanize(measure)}: %{{x}}<br>Tests: %{{y}}<extra></extra>"),
        meta={"slot": 0},
    ))
    median = float(values.median())
    fig.add_vline(
        x=median, line={"color": T.CHROME_LIGHT["muted"], "width": 1.5, "dash": "dash"},
        annotation_text=f"median {format_value(median, measure)}",
        annotation_position="top",
        annotation_font={"size": 11, "color": T.CHROME_LIGHT["muted"], "family": T.FONT_STACK},
    )
    fig.update_layout(yaxis_title="Count", xaxis_title=humanize(measure))
    return fig


def _render_box(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    df, measure = plan.frame, plan.measure
    fig = go.Figure()
    if plan.category and df[plan.category].nunique() <= T.MAX_SERIES:
        names = list(dict.fromkeys(df[plan.category].astype(str)))
        colors, slots = _series_colors(names)
        for name, color, slot in zip(names, colors, slots):
            sub = df[df[plan.category].astype(str) == name]
            fig.add_trace(go.Box(
                name=str(name), y=pd.to_numeric(sub[measure], errors="coerce"),
                marker={"color": color, "size": 6},
                line={"width": 1.5},
                boxpoints="outliers",
                meta={"slot": slot},
            ))
        fig.update_layout(showlegend=False)
    else:
        fig.add_trace(go.Box(
            name=humanize(measure), y=pd.to_numeric(df[measure], errors="coerce"),
            marker={"color": T.PALETTE_LIGHT[0], "size": 6},
            line={"width": 1.5}, boxpoints="outliers", meta={"slot": 0},
        ))
    fig.update_layout(yaxis_title=humanize(measure))
    return fig


def _render_gauge(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    """One number is not a bar chart. A single-value result gets a KPI reading
    with its threshold context, which is what the reader actually wanted."""
    df, measure = plan.frame, plan.measure
    value = float(pd.to_numeric(df[measure], errors="coerce").dropna().iloc[0])
    percent = is_percent_column(measure)

    if percent:
        axis_max = 100.0
        if value >= _PASS_RATE_TARGET:
            color = T.STATUS_COLORS["good"]
        elif value >= 80:
            color = T.STATUS_COLORS["warning"]
        else:
            color = T.STATUS_COLORS["critical"]
        steps = [
            {"range": [0, 80], "color": _alpha(T.STATUS_COLORS["critical"], 0.10)},
            {"range": [80, _PASS_RATE_TARGET], "color": _alpha(T.STATUS_COLORS["warning"], 0.12)},
            {"range": [_PASS_RATE_TARGET, 100], "color": _alpha(T.STATUS_COLORS["good"], 0.12)},
        ]
        threshold = {"line": {"color": T.STATUS_COLORS["good"], "width": 2},
                     "thickness": 0.9, "value": _PASS_RATE_TARGET}
    else:
        axis_max = max(value * 1.25, 1.0)
        color = T.PALETTE_LIGHT[0]
        steps = []
        threshold = None

    gauge = {
        "axis": {"range": [0, axis_max], "tickwidth": 1,
                 "tickcolor": T.CHROME_LIGHT["baseline"],
                 "tickfont": {"size": 11, "color": T.CHROME_LIGHT["muted"]},
                 "ticksuffix": "%" if percent else unit_for(measure)},
        "bar": {"color": color, "thickness": 0.7},
        "bgcolor": "rgba(0,0,0,0)",
        "borderwidth": 0,
        "steps": steps,
    }
    if threshold:
        gauge["threshold"] = threshold

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"font": {"size": 44, "color": T.CHROME_LIGHT["ink"], "family": T.FONT_STACK},
                "suffix": "%" if percent else unit_for(measure),
                "valueformat": value_format(measure)},
        title={"text": humanize(measure),
               "font": {"size": 13, "color": T.CHROME_LIGHT["ink_secondary"],
                        "family": T.FONT_STACK}},
        gauge=gauge,
        domain={"x": [0, 1], "y": [0, 1]},
        meta={"kpi": True},
    ))
    return fig


def _render_radar(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    df, measure = plan.frame, plan.measure
    labels = _labels_of(plan).tolist()
    values = pd.to_numeric(df[measure], errors="coerce").fillna(0).tolist()
    # Close the polygon so it reads as a shape rather than an open path.
    fig = go.Figure(go.Scatterpolar(
        r=values + values[:1], theta=labels + labels[:1],
        fill="toself",
        fillcolor=_alpha(T.PALETTE_LIGHT[0], 0.18),
        line={"color": T.PALETTE_LIGHT[0], "width": 2},
        marker={"size": 7, "color": T.PALETTE_LIGHT[0]},
        name=humanize(measure),
        hovertemplate=(f"<b>%{{theta}}</b><br>{humanize(measure)}: "
                       f"%{{r:{value_format(measure)}}}{unit_for(measure)}<extra></extra>"),
        meta={"slot": 0},
    ))
    fig.update_layout(polar={
        "bgcolor": "rgba(0,0,0,0)",
        "radialaxis": {"visible": True, "gridcolor": T.CHROME_LIGHT["grid"],
                       "linecolor": T.CHROME_LIGHT["baseline"],
                       "tickfont": {"size": 10, "color": T.CHROME_LIGHT["muted"]},
                       "ticksuffix": unit_for(measure)},
        "angularaxis": {"gridcolor": T.CHROME_LIGHT["grid"],
                        "linecolor": T.CHROME_LIGHT["baseline"],
                        "tickfont": {"size": 11, "color": T.CHROME_LIGHT["muted"]}},
    })
    return fig


def _render_waterfall(plan: ChartPlan, spec: ChartSpec) -> go.Figure:
    df, measure = plan.frame, plan.measure
    labels = _labels_of(plan).tolist()
    values = pd.to_numeric(df[measure], errors="coerce").fillna(0).tolist()
    fig = go.Figure(go.Waterfall(
        x=labels, y=values,
        measure=["relative"] * len(values),
        connector={"line": {"color": T.CHROME_LIGHT["grid"], "width": 1}},
        increasing={"marker": {"color": T.STATUS_COLORS["critical"]}},
        decreasing={"marker": {"color": T.STATUS_COLORS["good"]}},
        totals={"marker": {"color": T.PALETTE_LIGHT[0]}},
        text=[f"{v:{value_format(measure)}}{unit_for(measure)}" for v in values],
        textposition="outside",
        textfont={"size": 11, "family": T.FONT_STACK},
        meta={"slot": 0},
    ))
    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_RENDERERS = {
    "bar": lambda p, s: _render_bars(p, s, horizontal=False, stacked=False),
    "stacked_bar": lambda p, s: _render_bars(p, s, horizontal=False, stacked=True),
    "horizontal_bar": lambda p, s: _render_bars(p, s, horizontal=True, stacked=False),
    "platform_comparison": lambda p, s: _render_bars(p, s, horizontal=False, stacked=False),
    "line": lambda p, s: _render_line(p, s, filled=False),
    "area": lambda p, s: _render_line(p, s, filled=True),
    "pie": lambda p, s: _render_pie(p, s, hole=0.0),
    "donut": lambda p, s: _render_pie(p, s, hole=0.55),
    "scatter": lambda p, s: _render_scatter(p, s, bubble=False),
    "bubble": lambda p, s: _render_scatter(p, s, bubble=True),
    "heatmap": _render_heatmap,
    "treemap": lambda p, s: _render_treemap(p, s, sunburst=False),
    "sunburst": lambda p, s: _render_treemap(p, s, sunburst=True),
    "funnel": _render_funnel,
    "histogram": _render_histogram,
    "box": _render_box,
    "gauge": _render_gauge,
    "radar": _render_radar,
    "waterfall": _render_waterfall,
}

# Types that draw their own coordinate system and must not get cartesian axes.
_NON_CARTESIAN = {"pie", "donut", "treemap", "sunburst", "gauge", "radar", "funnel"}

# Cartesian, but the RENDERER decides what each axis means (a heatmap's x is
# its pivot's columns; a histogram's x is the binned measure). These get the
# theme's axis styling and nothing else.
_SELF_AXED = {"heatmap", "histogram", "box", "scatter", "bubble"}


def _style_axes_in_place(fig: go.Figure, chrome: dict, grid: bool = True) -> None:
    """Apply theme ink/grid/baseline to whatever axes the renderer already set,
    without touching their titles, ranges, or category ordering."""
    common = {
        "tickfont": {"size": 11, "color": chrome["muted"], "family": T.FONT_STACK},
        "automargin": True,
        "zeroline": False,
        "showline": True,
        "linecolor": chrome["baseline"],
        "linewidth": 1,
        "showgrid": grid,
    }
    if grid:
        common["gridcolor"] = chrome["grid"]
        common["gridwidth"] = 1
    fig.update_xaxes(**common)
    fig.update_yaxes(**common)
    fig.update_xaxes(title_font={"size": 12, "color": chrome["ink_secondary"]})
    fig.update_yaxes(title_font={"size": 12, "color": chrome["ink_secondary"]})


def make_title(spec: ChartSpec, plan: ChartPlan) -> str:
    """A real title built from the parsed intent, not a truncated echo of the
    prompt. 'show me a chart of the slowest tests pls' → 'Duration by test'."""
    measure = plan.measure
    if measure is None:
        return (spec.prompt or "Chart").strip()[:70]

    measure_label = humanize(measure)
    dim_label = humanize(plan.category) if plan.category else ""

    # Forms whose title has to name what they actually show, not "Y by X".
    if spec.chart_type in ("scatter", "bubble") and plan.measure2:
        title = f"{humanize(plan.measure2)} vs {measure_label.lower()}"
        if dim_label:
            title += f", per {dim_label.lower()}"
        return title[:1].upper() + title[1:]

    if spec.chart_type == "histogram":
        return f"Distribution of {measure_label.lower()}"

    if spec.chart_type == "box":
        return (f"{measure_label} spread by {dim_label.lower()}"
                if dim_label else f"{measure_label} spread")

    if spec.chart_type == "heatmap" and plan.series:
        return f"{measure_label} — {dim_label.lower()} × {humanize(plan.series).lower()}"

    if spec.chart_type == "gauge":
        return measure_label

    title = f"{measure_label} by {dim_label.lower()}" if dim_label else measure_label

    if spec.direction == "highest" and spec.explicit_limit:
        title = f"Top {spec.limit} — {title.lower()}"
    elif spec.direction == "lowest" and spec.explicit_limit:
        title = f"Bottom {spec.limit} — {title.lower()}"

    if plan.series:
        title += f", split by {humanize(plan.series).lower()}"
    return title[:1].upper() + title[1:]


def build_figure(df: pd.DataFrame, spec: ChartSpec,
                 fallback_title: str = "") -> tuple[go.Figure, dict]:
    """Build a themed, annotated Plotly figure from a result frame + parsed
    intent. Returns (figure, meta) where meta carries the insight sentence and
    the table-view twin.

    Raises ValueError when the frame genuinely cannot support any chart, so the
    caller can report that instead of rendering something meaningless."""
    if df is None or df.empty:
        raise ValueError("No data to chart.")

    plan = build_plan(df, spec)
    if plan.frame.empty or plan.measure is None:
        raise ValueError("No numeric column available to chart.")

    renderer = _RENDERERS.get(spec.chart_type, _RENDERERS["bar"])
    try:
        fig = renderer(plan, spec)
    except Exception as exc:
        logger.warning("renderer '%s' failed (%s); falling back to bar", spec.chart_type, exc)
        spec.chart_type = "bar"
        fig = _RENDERERS["bar"](plan, spec)

    insight = compute_insight(plan, spec)
    subtitle_scope = _scope_subtitle(plan, spec)
    # When the chart shows a SUBSET, the scope note is not optional garnish —
    # it is the difference between "the worst 15 modules" and "all modules".
    # Keep it alongside the insight rather than letting the insight hide it.
    if insight and (plan.truncated or plan.other_bucketed or plan.scope_notes):
        subtitle = f"{insight}  ·  {subtitle_scope}" if subtitle_scope else insight
    else:
        subtitle = insight or subtitle_scope
    title = make_title(spec, plan) or fallback_title or "Chart"

    layout = _base_layout(title, subtitle, plan, spec)
    fig.update_layout(**layout)

    horizontal = spec.chart_type == "horizontal_bar"
    c = T.CHROME_LIGHT
    if spec.chart_type in _SELF_AXED:
        # These renderers define their own axes (a heatmap's x is its pivot's
        # COLUMNS, not the plan's category). Applying the generic
        # measure/category pair here would overwrite the titles and — worse —
        # push the plan's category list onto the wrong axis via categoryarray,
        # which is how a 3×2 heatmap ended up with five x categories.
        _style_axes_in_place(fig, c, grid=spec.chart_type not in ("heatmap",))
    elif spec.chart_type not in _NON_CARTESIAN:
        measure_axis = _axis(
            humanize(plan.measure), c,
            percent=is_percent_column(plan.measure),
            unit=unit_for(plan.measure) if not is_percent_column(plan.measure) else "",
        )
        # The category axis title is redundant on a ranked bar: the title
        # already says "by module" and every tick IS a module name, so the
        # rotated label only steals width and collides with the ticks.
        cat_title = "" if spec.chart_type in ("bar", "horizontal_bar", "stacked_bar",
                                              "platform_comparison") \
            else (humanize(plan.category) if plan.category else "")
        category_axis = _axis(cat_title, c, is_category=True)
        if plan.category_order:
            category_axis["categoryorder"] = "array"
            category_axis["categoryarray"] = plan.category_order

        if horizontal:
            fig.update_layout(xaxis=measure_axis, yaxis=category_axis)
        else:
            fig.update_layout(xaxis=category_axis, yaxis=measure_axis)
            longest = max((len(str(v)) for v in _labels_of(plan)), default=0)
            if longest > 12 and len(plan.frame) > 4:
                fig.update_xaxes(tickangle=-35)

        _target_line(fig, plan.measure, plan, horizontal)

    # A legend is mandatory whenever more than one series carries identity, and
    # pointless when there is only one — the title already names it.
    trace_count = len(fig.data)
    if trace_count > 1 and spec.chart_type not in ("box",):
        fig.update_layout(showlegend=True, legend={
            "orientation": "h", "yanchor": "bottom", "y": 1.02,
            "xanchor": "right", "x": 1,
            "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
            "font": {"size": 11, "color": T.CHROME_LIGHT["ink_secondary"],
                     "family": T.FONT_STACK},
            "title": {"text": ""},
        })
    elif spec.chart_type in ("pie", "donut", "treemap", "sunburst", "funnel"):
        fig.update_layout(showlegend=False)  # slices are directly labelled

    meta = {
        "insight": insight,
        "scope": subtitle_scope,
        "chart_type": spec.chart_type,
        "measure": plan.measure,
        "dimension": plan.category,
        "series": plan.series,
        "row_count": plan.source_rows,
        "truncated": plan.truncated,
        "table": _table_view(plan),
        "theme": T.theme_payload(),
    }
    fig.update_layout(meta={"sentinel": meta})
    return fig, meta


def _table_view(plan: ChartPlan) -> dict:
    """The WCAG-clean twin of the chart: every plotted value as text, so no
    value is reachable only through colour or hover."""
    df = plan.frame.drop(columns=[c for c in ("__label__", "__full__")
                                  if c in plan.frame.columns])
    df = df.head(200)
    columns = [{"key": c, "label": humanize(c), "unit": unit_for(c)} for c in df.columns]
    rows = []
    for _, row in df.iterrows():
        rows.append([
            format_value(row[c], c) if pd.api.types.is_number(row[c]) else
            ("" if pd.isna(row[c]) else str(row[c]))
            for c in df.columns
        ])
    return {"columns": columns, "rows": rows}
