"""
Tests for the deterministic chart pipeline: chart_spec.parse/reconcile and
chart_builder.build_figure.

The point of these is that the chart ANSWERS THE PROMPT. A figure that renders
without raising is not the bar — a bar chart of the wrong measure renders
perfectly. So most of these assert on what was parsed and what ended up on each
axis, not merely that a figure came back.
"""

import json
import unittest

import numpy as np
import pandas as pd

from services import chart_spec, chart_builder
from services import chart_theme as T


def _modules_frame(n=17):
    rng = np.random.default_rng(11)
    return pd.DataFrame({
        "module_name": [f"Module{i:02d}" for i in range(n)],
        "project_name": ["FSA"] * (n // 2) + ["HSA"] * (n - n // 2),
        "platform_type": [("desktop", "mobile")[i % 2] for i in range(n)],
        "total_tests": rng.integers(20, 200, n),
        "failed": rng.integers(0, 40, n),
        "pass_rate": np.round(rng.uniform(55, 100, n), 2),
        "avg_duration_seconds": np.round(rng.uniform(0.5, 45, n), 2),
    })


STATUS_FRAME = pd.DataFrame({"status": ["passed", "failed", "skipped", "pending"],
                             "count": [3120, 284, 96, 12]})

PLATFORM_FRAME = pd.DataFrame({"platform_type": ["desktop", "mobile"],
                               "pass_rate": [93.4, 78.2], "total_tests": [1800, 1712]})

TREND_FRAME = pd.DataFrame({
    "build_date": ["2026-07-01", "2026-07-08", "2026-07-15", "2026-07-22"],
    "pass_rate": [88.1, 89.4, 87.0, 92.3],
    "total_tests": [3100, 3140, 3150, 3204],
})


class ChartSpecParsingTests(unittest.TestCase):

    def test_explicit_chart_types_are_honoured(self):
        cases = {
            "pie chart of status": "pie",
            "donut of status": "donut",
            "heatmap of failures": "heatmap",
            "scatter of duration vs pass rate": "scatter",
            "treemap of failures": "treemap",
            "histogram of durations": "histogram",
            "box plot of duration": "box",
            "funnel chart of stages": "funnel",
            "radar chart of pass rate": "radar",
            "stacked bar of failures": "stacked_bar",
            "line chart of pass rate": "line",
        }
        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt):
                spec = chart_spec.parse(prompt)
                self.assertEqual(spec.chart_type, expected)
                self.assertTrue(spec.explicit_type)

    def test_top_n_is_extracted_with_direction(self):
        spec = chart_spec.parse("top 5 modules by failed tests")
        self.assertEqual(spec.limit, 5)
        self.assertEqual(spec.direction, "highest")
        self.assertTrue(spec.explicit_limit)

        spec = chart_spec.parse("bottom 3 modules by pass rate")
        self.assertEqual(spec.limit, 3)
        self.assertEqual(spec.direction, "lowest")

    def test_worst_overrides_top_in_top_5_worst(self):
        # "top 5 worst" means the bottom 5, not the top 5.
        spec = chart_spec.parse("top 5 worst modules by pass rate")
        self.assertEqual(spec.direction, "lowest")
        self.assertEqual(spec.limit, 5)

    def test_slowest_means_highest_duration(self):
        spec = chart_spec.parse("10 slowest tests")
        self.assertEqual(spec.measure, "duration")
        self.assertEqual(spec.direction, "highest")
        self.assertEqual(spec.limit, 10)

        spec = chart_spec.parse("5 fastest tests")
        self.assertEqual(spec.direction, "lowest")

    def test_measure_and_dimension_are_parsed(self):
        spec = chart_spec.parse("failures by module")
        self.assertEqual(spec.measure, "failed")
        self.assertEqual(spec.dimension, "module")

        spec = chart_spec.parse("pass rate per project")
        self.assertEqual(spec.measure, "pass_rate")
        self.assertEqual(spec.dimension, "project")

    def test_longest_measure_keyword_wins(self):
        # "pass rate" must beat the bare word "pass"/"passed" inside it.
        self.assertEqual(chart_spec.parse("what is the pass rate").measure, "pass_rate")

    def test_comparison_does_not_become_a_filter(self):
        # "mobile vs desktop" names both values; reading it as
        # WHERE platform_type='mobile' would answer a narrower question.
        spec = chart_spec.parse("mobile vs desktop pass rate")
        self.assertNotIn("platform_type", spec.filters)

        spec = chart_spec.parse("pass rate by platform")
        self.assertNotIn("platform_type", spec.filters)

    def test_single_platform_mention_is_a_filter(self):
        spec = chart_spec.parse("failures by module on mobile")
        self.assertEqual(spec.filters.get("platform_type"), "mobile")

    def test_status_used_as_measure_is_not_a_filter(self):
        # "failed" here is the thing being counted, not a row restriction.
        spec = chart_spec.parse("top 5 modules by failed tests")
        self.assertNotIn("status", spec.filters)

    def test_status_used_as_restriction_is_a_filter(self):
        spec = chart_spec.parse("show only failed tests by module")
        self.assertEqual(spec.filters.get("status"), "failed")

    def test_breakdown_requires_an_explicit_second_dimension(self):
        # An unrequested split doubles the marks and answers a question nobody
        # asked; the renderer should aggregate instead.
        self.assertIsNone(chart_spec.parse("failures by module").breakdown)
        self.assertEqual(
            chart_spec.parse("failures by module and platform").breakdown, "platform")

    def test_scatter_keeps_both_named_measures_in_order(self):
        spec = chart_spec.parse("scatter of duration vs pass rate")
        self.assertEqual(spec.measure, "duration")
        self.assertEqual(spec.measure2, "pass_rate")

    def test_cross_build_phrasing_implies_a_time_axis(self):
        spec = chart_spec.parse("how has pass rate trended over builds")
        self.assertTrue(spec.is_cross_build)
        self.assertEqual(spec.chart_type, "line")
        self.assertEqual(spec.dimension, "build")


class ChartSpecReconcileTests(unittest.TestCase):

    def test_scatter_without_two_measures_downgrades(self):
        df = pd.DataFrame({"module_name": ["a", "b"], "failed": [1, 2]})
        spec = chart_spec.reconcile(chart_spec.parse("scatter of failures"), df)
        self.assertEqual(spec.chart_type, "bar")

    def test_heatmap_without_two_categoricals_downgrades(self):
        df = pd.DataFrame({"module_name": ["a", "b"], "failed": [1, 2]})
        spec = chart_spec.reconcile(chart_spec.parse("heatmap of failures"), df)
        self.assertEqual(spec.chart_type, "bar")

    def test_single_value_becomes_a_kpi_not_a_one_bar_chart(self):
        df = pd.DataFrame({"pass_rate": [91.7]})
        spec = chart_spec.reconcile(chart_spec.parse("overall pass rate"), df)
        self.assertEqual(spec.chart_type, "gauge")

    def test_many_categories_lie_down(self):
        spec = chart_spec.reconcile(chart_spec.parse("failures by module"), _modules_frame(30))
        self.assertEqual(spec.chart_type, "horizontal_bar")

    def test_explicitly_named_pie_survives_high_cardinality(self):
        # The user named it, so the builder buckets the tail into "Other"
        # rather than silently substituting a different chart type.
        spec = chart_spec.reconcile(
            chart_spec.parse("pie chart of failures by module"), _modules_frame(30))
        self.assertEqual(spec.chart_type, "pie")


class ChartBuilderTests(unittest.TestCase):

    def _build(self, prompt, df):
        spec = chart_spec.reconcile(chart_spec.parse(prompt), df)
        fig, meta = chart_builder.build_figure(df, spec)
        return spec, fig, json.loads(fig.to_json()), meta

    def test_every_chart_type_renders(self):
        rng = np.random.default_rng(3)
        tests = pd.DataFrame({
            "test_name": [f"t{i}" for i in range(40)],
            "duration_sec": np.round(rng.uniform(0.2, 60, 40), 2),
            "platform_type": rng.choice(["desktop", "mobile"], 40).tolist(),
        })
        heat = pd.DataFrame({
            "project_name": ["FSA", "FSA", "HSA", "HSA"],
            "platform_type": ["desktop", "mobile"] * 2,
            "failed": [12, 30, 4, 18],
        })
        cases = [
            ("failures by module", _modules_frame()),
            ("pie chart of status", STATUS_FRAME),
            ("donut of status", STATUS_FRAME),
            ("mobile vs desktop pass rate", PLATFORM_FRAME),
            ("pass rate trend over builds", TREND_FRAME),
            ("area chart of pass rate over time", TREND_FRAME),
            ("overall pass rate", pd.DataFrame({"pass_rate": [91.7]})),
            ("10 slowest tests", tests),
            ("heatmap of failures by project and platform", heat),
            ("scatter of duration vs pass rate by module", _modules_frame()),
            ("histogram of durations", tests),
            ("box plot of duration by platform", tests),
            ("treemap of failures by module", _modules_frame()),
            ("funnel chart of status", STATUS_FRAME),
            ("radar chart of pass rate by module", _modules_frame(6)),
            ("stacked bar of failures by module and platform", _modules_frame()),
        ]
        for prompt, df in cases:
            with self.subTest(prompt=prompt):
                _spec, _fig, payload, meta = self._build(prompt, df)
                self.assertTrue(payload["data"], "figure has no traces")
                self.assertTrue(payload["layout"]["title"]["text"])
                self.assertTrue(meta["insight"], "no insight computed")

    def test_top_n_actually_limits_the_rendered_categories(self):
        _spec, _fig, payload, _meta = self._build("top 5 modules by failed tests", _modules_frame())
        plotted = payload["data"][0]
        axis = plotted["y"] if plotted.get("orientation") == "h" else plotted["x"]
        self.assertEqual(len(set(axis)), 5)

    def test_horizontal_bar_puts_the_largest_at_the_top(self):
        # A category axis grows upward, so the ranking has to be reversed for
        # the chart to read top-down like the list it represents.
        _spec, fig, _payload, _meta = self._build("top 5 modules by failed tests", _modules_frame())
        # Read off the figure, not its JSON: plotly 6 base64-encodes numeric
        # arrays as {dtype, bdata}, so indexing the JSON gives key names.
        trace = fig.data[0]
        self.assertEqual(trace.orientation, "h")
        values = list(trace.x)
        self.assertEqual(values, sorted(values), "largest value should be drawn last (top)")

    def test_measure_matches_what_was_asked_for(self):
        df = _modules_frame()
        _spec, _fig, _payload, meta = self._build("pass rate by module", df)
        self.assertEqual(meta["measure"], "pass_rate")
        _spec, _fig, _payload, meta = self._build("failures by module", df)
        self.assertEqual(meta["measure"], "failed")

    def test_status_columns_use_the_reserved_status_palette(self):
        _spec, _fig, payload, _meta = self._build("pie chart of status", STATUS_FRAME)
        colors = payload["data"][0]["marker"]["colors"]
        self.assertEqual(colors[0], T.STATUS_COLORS["good"])      # passed
        self.assertEqual(colors[1], T.STATUS_COLORS["critical"])  # failed
        self.assertEqual(colors[2], T.STATUS_COLORS["warning"])   # skipped

    def test_single_series_uses_one_colour(self):
        # Colouring each bar differently burns the identity channel on
        # information the bar length already carries.
        _spec, _fig, payload, _meta = self._build("failures by module", _modules_frame())
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["marker"]["color"], T.PALETTE_LIGHT[0])

    def test_pass_rate_chart_carries_a_target_line(self):
        _spec, _fig, payload, _meta = self._build("pass rate by module", _modules_frame())
        shapes = payload["layout"].get("shapes", [])
        self.assertTrue(any(s.get("line", {}).get("dash") == "dash" for s in shapes),
                        "expected a dashed 95% target rule")

    def test_truncation_is_disclosed_in_the_subtitle(self):
        _spec, _fig, payload, _meta = self._build("pass rate by module", _modules_frame(40))
        subtitle = payload["layout"]["title"].get("subtitle", {}).get("text", "")
        self.assertIn("of 40", subtitle,
                      "a truncated chart must say it is showing a subset")

    def test_part_of_whole_buckets_the_tail_rather_than_dropping_it(self):
        df = _modules_frame(30)
        _spec, fig, _payload, _meta = self._build("pie chart of failures by module", df)
        labels = list(fig.data[0].labels)
        self.assertIn(T.OTHER_LABEL, labels)
        charted = sum(float(v) for v in fig.data[0].values)
        self.assertAlmostEqual(charted, float(df["failed"].sum()), places=4,
                               msg="pie slices must sum to the true total")

    def test_percentage_gaps_are_reported_in_points(self):
        _spec, _fig, _payload, meta = self._build("mobile vs desktop pass rate", PLATFORM_FRAME)
        self.assertIn("pts", meta["insight"])

    def test_every_figure_carries_a_table_view_and_both_themes(self):
        _spec, _fig, payload, meta = self._build("failures by module", _modules_frame())
        sentinel = payload["layout"]["meta"]["sentinel"]
        self.assertTrue(sentinel["table"]["rows"])
        self.assertTrue(sentinel["table"]["columns"])
        self.assertIn("light", sentinel["theme"])
        self.assertIn("dark", sentinel["theme"])
        self.assertEqual(len(sentinel["theme"]["dark"]["palette"]), T.MAX_SERIES)

    def test_traces_carry_a_slot_for_client_side_retheming(self):
        _spec, _fig, payload, _meta = self._build(
            "stacked bar of failures by module and platform", _modules_frame())
        for trace in payload["data"]:
            self.assertIn("meta", trace)
            self.assertIn("slot", trace["meta"])

    def test_empty_frame_raises_rather_than_rendering_nothing(self):
        spec = chart_spec.parse("failures by module")
        with self.assertRaises(ValueError):
            chart_builder.build_figure(pd.DataFrame(), spec)

    def test_frame_with_no_numeric_column_raises(self):
        df = pd.DataFrame({"module_name": ["a", "b"], "note": ["x", "y"]})
        spec = chart_spec.parse("failures by module")
        with self.assertRaises(ValueError):
            chart_builder.build_figure(df, spec)

    def test_object_typed_numbers_are_still_treated_as_a_measure(self):
        # DuckDB DECIMAL columns arrive as objects; if they aren't coerced the
        # measure silently disqualifies itself and the chart plots the wrong
        # column (or nothing).
        df = pd.DataFrame({"module_name": ["a", "b", "c"],
                           "failed": pd.Series(["3", "9", "5"], dtype=object)})
        spec = chart_spec.reconcile(chart_spec.parse("failures by module"), df)
        _fig, meta = chart_builder.build_figure(df, spec)
        self.assertEqual(meta["measure"], "failed")


class LabelShorteningTests(unittest.TestCase):
    """Real test identifiers are ~150-char spec paths with tags. Rendered raw
    they eat the plot width; the tick has to be abbreviated while the full
    value stays reachable in hover and the table."""

    LONG = ("Platforms/SFRA/Perks Feature/FSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend "
            "@fsa_storefront @fsa-earnPointsBySpend @fsa-flaky-group TS_40: EarnPointsBySpend "
            "@earnPointsBySpend")

    def test_takes_the_name_after_the_spec_path(self):
        label = chart_builder.display_label(self.LONG)
        self.assertNotIn("Platforms/SFRA", label)
        self.assertNotIn("@", label)
        self.assertLessEqual(len(label), 44)

    def test_short_labels_pass_through_unchanged(self):
        self.assertEqual(chart_builder.display_label("Checkout Tests"), "Checkout Tests")

    def test_collisions_are_disambiguated(self):
        # Two distinct categories must never render as the same tick, or the
        # reader merges two bars into one.
        df = pd.DataFrame({
            "test_name": ["a/b.spec.ts#Login @one", "c/d.spec.ts#Login @two"],
            "failed": [3, 7],
        })
        spec = chart_spec.reconcile(chart_spec.parse("failures by test"), df)
        fig, _meta = chart_builder.build_figure(df, spec)
        ticks = list(fig.data[0].y if fig.data[0].orientation == "h" else fig.data[0].x)
        self.assertEqual(len(set(ticks)), 2, f"labels collided: {ticks}")

    def test_hover_keeps_the_full_value(self):
        df = pd.DataFrame({"test_name": [self.LONG, "short/x.spec.ts#Other"],
                           "duration_sec": [12.0, 3.0]})
        spec = chart_spec.reconcile(chart_spec.parse("slowest tests"), df)
        fig, _meta = chart_builder.build_figure(df, spec)
        hovered = [str(row[0]) for row in fig.data[0].customdata]
        self.assertIn(self.LONG, hovered)

    def test_table_view_excludes_internal_columns(self):
        df = _modules_frame()
        spec = chart_spec.reconcile(chart_spec.parse("failures by module"), df)
        _fig, meta = chart_builder.build_figure(df, spec)
        keys = [c["key"] for c in meta["table"]["columns"]]
        self.assertNotIn("__label__", keys)
        self.assertNotIn("__full__", keys)


class HumanizeTests(unittest.TestCase):

    def test_column_labels(self):
        self.assertEqual(chart_builder.humanize("module_name"), "Module")
        self.assertEqual(chart_builder.humanize("pass_rate"), "Pass rate")
        self.assertEqual(chart_builder.humanize("some_custom_field"), "Some custom field")

    def test_percentage_deltas_use_points(self):
        self.assertEqual(chart_builder.delta_unit("pass_rate"), " pts")
        self.assertEqual(chart_builder.delta_unit("duration_sec"), "s")
        self.assertEqual(chart_builder.delta_unit("failed"), "")


if __name__ == "__main__":
    unittest.main()
