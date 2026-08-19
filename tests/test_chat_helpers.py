"""
Tests for the chat-path helpers that decide what the answering model sees.

These are where wrong answers come from: a decision object that failed to parse
gets thrown away and replaced by a keyword-matched query for a simpler
question, and aggregates computed over a 50-row window get presented as totals
over 400 rows.
"""

import json
import unittest

import numpy as np
import pandas as pd

from services import handlers


class ExtractJsonObjectTests(unittest.TestCase):

    def test_plain_object(self):
        got = handlers._extract_json_object('{"action":"sql","data":"SELECT 1"}')
        self.assertEqual(got, {"action": "sql", "data": "SELECT 1"})

    def test_fenced_object(self):
        got = handlers._extract_json_object('```json\n{"action":"answer","data":"hi"}\n```')
        self.assertEqual(got["action"], "answer")

    def test_nested_objects_survive(self):
        # The old `\{[^{}]+\}` pattern could not match this at all, so a
        # multi-query decision silently degraded to a single fallback query.
        raw = ('{"action":"sql_multi","data":[{"label":"A","sql":"SELECT 1"},'
               '{"label":"B","sql":"SELECT 2"}]}')
        got = handlers._extract_json_object(raw)
        self.assertEqual(got["action"], "sql_multi")
        self.assertEqual(len(got["data"]), 2)
        self.assertEqual(got["data"][1]["sql"], "SELECT 2")

    def test_object_with_prose_around_it(self):
        raw = 'Here you go:\n{"action":"sql","data":"SELECT 1"}\nHope that helps.'
        self.assertEqual(handlers._extract_json_object(raw)["action"], "sql")

    def test_braces_inside_string_values_do_not_confuse_it(self):
        raw = '{"action":"answer","data":"use {placeholder} syntax"}'
        got = handlers._extract_json_object(raw)
        self.assertEqual(got["data"], "use {placeholder} syntax")

    def test_escaped_quotes_inside_sql(self):
        raw = '{"action":"sql","data":"SELECT * FROM t WHERE name = \\"x\\""}'
        got = handlers._extract_json_object(raw)
        self.assertIsNotNone(got)
        self.assertEqual(got["action"], "sql")

    def test_returns_none_for_non_json(self):
        self.assertIsNone(handlers._extract_json_object("just some prose"))
        self.assertIsNone(handlers._extract_json_object(""))
        self.assertIsNone(handlers._extract_json_object(None))


class DatasetFactsTests(unittest.TestCase):

    def _frame(self, n=200):
        rng = np.random.default_rng(5)
        return pd.DataFrame({
            "module_name": [f"M{i % 20}" for i in range(n)],
            "status": rng.choice(["passed", "failed"], n).tolist(),
            "failed": rng.integers(0, 50, n),
        })

    def test_reports_the_full_row_count_not_the_visible_window(self):
        facts = handlers._dataset_facts(self._frame(200))
        self.assertIn("Total rows in the full result: 200", facts)

    def test_warns_when_the_sample_is_partial(self):
        facts = handlers._dataset_facts(self._frame(200))
        self.assertIn("only the first 50 rows", facts)

    def test_no_truncation_warning_for_small_results(self):
        facts = handlers._dataset_facts(self._frame(10))
        self.assertNotIn("only the first", facts)

    def test_aggregates_cover_every_row(self):
        df = self._frame(200)
        facts = handlers._dataset_facts(df)
        # The sum must be the true sum, not the sum of the first 50 rows.
        self.assertIn(f"sum={df['failed'].sum():,.2f}", facts)
        self.assertIn(f"max={df['failed'].max():,.2f}", facts)

    def test_names_the_row_holding_the_extreme(self):
        facts = handlers._dataset_facts(self._frame(200))
        self.assertIn("highest:", facts)
        self.assertIn("lowest:", facts)

    def test_categorical_distribution_is_included(self):
        facts = handlers._dataset_facts(self._frame(200))
        self.assertIn("status distribution:", facts)

    def test_all_unique_column_is_skipped(self):
        # A column where every value is distinct carries no distribution.
        df = pd.DataFrame({"test_name": [f"t{i}" for i in range(20)],
                           "duration": range(20)})
        self.assertNotIn("test_name distribution", handlers._dataset_facts(df))

    def test_empty_frame_yields_nothing(self):
        self.assertEqual(handlers._dataset_facts(pd.DataFrame()), "")


class SpecDirectiveTests(unittest.TestCase):
    """The directives block is what keeps the SQL and the rendered chart
    answering the same question."""

    def _directives(self, prompt):
        from services import chart_spec
        return handlers._spec_sql_directives(chart_spec.parse(prompt))

    def test_top_n_becomes_an_explicit_order_and_limit(self):
        text = self._directives("top 5 modules by failed tests")
        self.assertIn("ORDER BY <measure> DESC LIMIT 5", text)

    def test_bottom_n_orders_ascending(self):
        self.assertIn("ASC LIMIT 3", self._directives("bottom 3 modules by pass rate"))

    def test_filters_are_stated_as_where_clauses(self):
        text = self._directives("failures by module on mobile")
        self.assertIn("WHERE platform_type = 'mobile'", text)

    def test_comparison_does_not_emit_a_filter(self):
        text = self._directives("mobile vs desktop pass rate")
        self.assertNotIn("WHERE platform_type", text)

    def test_shape_requirements_are_stated_per_form(self):
        self.assertIn("TWO numeric columns", self._directives("scatter of duration vs pass rate"))
        self.assertIn("TWO categorical columns", self._directives("heatmap of failures"))
        self.assertIn("ONE categorical column", self._directives("pie chart of status"))


class NeedsLlmValidationTests(unittest.TestCase):
    """The validation pass is a second full LLM round-trip on every answer.

    Skipping it is a latency decision with an accuracy cost, so the gate has
    to be wrong only in the safe direction: it may run the validator
    unnecessarily, but it must never wave through an answer carrying a figure
    the data does not support."""

    def setUp(self):
        self.df = pd.DataFrame(
            {
                "module_name": ["Checkout", "Login", "Search"],
                "failed_count": [89, 41, 12],
                "pass_rate": [78.2, 93.4, 99.1],
            }
        )
        self.facts = handlers._dataset_facts(self.df)

    def _needs(self, draft):
        return handlers._needs_llm_validation(draft, self.df, self.facts)

    def test_fully_grounded_answer_skips_the_round_trip(self):
        self.assertFalse(
            self._needs("Checkout reported **89 failures** at a **78.2%** pass rate.")
        )

    def test_a_number_absent_from_the_data_is_validated(self):
        self.assertTrue(self._needs("Checkout reported **147 failures**."))

    def test_superlatives_are_always_validated(self):
        # Ordering claims are the validator's stated most-common error class
        # and cannot be checked from the figures alone.
        self.assertTrue(self._needs("Checkout is the **worst** module."))
        self.assertTrue(self._needs("Login has the **highest** pass rate."))

    def test_superlative_substrings_do_not_trigger_it(self):
        # "topology"/"bestseller" contain superlatives only as substrings.
        self.assertFalse(self._needs("The topology view lists **89** entries."))

    def test_small_integers_are_treated_as_list_markers(self):
        self.assertFalse(self._needs("Modules affected: 1. Checkout 2. Login 3. Search"))

    def test_derived_differences_between_data_values_are_grounded(self):
        # 93.4 - 78.2 = 15.2 is arithmetic on given values, not a new claim.
        # It still routes to the validator here because "leads" is a
        # comparison claim - but the number itself must not be what flags it.
        grounded = handlers._grounded_numbers(self.df, self.facts)
        self.assertIn(15.2, grounded)

    def test_an_empty_draft_needs_no_validation(self):
        self.assertFalse(self._needs(""))

    def test_an_empty_result_always_validates(self):
        self.assertTrue(
            handlers._needs_llm_validation("Anything at all.", pd.DataFrame(), "")
        )


class RenderAndStoreContractTests(unittest.TestCase):
    """_render_and_store now reports the id of the chart it stored.

    That id is what lets the browser show a freshly generated figure straight
    away and still recognise it as the same chart when the history list
    arrives, rather than rendering it twice or waiting for the refetch before
    showing anything at all."""

    def setUp(self):
        from services import chart_spec

        self.df = pd.DataFrame(
            {"module_name": ["Checkout", "Login"], "failed": [89, 41]}
        )
        self.spec = chart_spec.parse("bar chart of failed tests by module")
        self.stored = []
        self.learned = []

        self._real_store = handlers.memory.store_chart
        self._real_learn = handlers.memory.learn_from_interaction
        handlers.memory.store_chart = lambda *a, **k: (
            self.stored.append((a, k)) or "chart-abc-123"
        )
        handlers.memory.learn_from_interaction = lambda *a, **k: self.learned.append(a)

    def tearDown(self):
        handlers.memory.store_chart = self._real_store
        handlers.memory.learn_from_interaction = self._real_learn

    def test_returns_chart_json_error_and_id(self):
        chart_json, error, chart_id = handlers._render_and_store(
            self.df, self.spec, "failed tests by module", "sess",
            "SELECT 1", "user", "ingest-1", "ws",
        )
        self.assertIsNone(error)
        self.assertEqual(chart_id, "chart-abc-123")
        self.assertIn("data", json.loads(chart_json))

    def test_the_chart_itself_is_stored_before_returning(self):
        # The id can only be handed to the browser if the write already
        # happened - this one must NOT be deferred to the background.
        handlers._render_and_store(
            self.df, self.spec, "failed tests by module", "sess",
            "SELECT 1", "user", "ingest-1", "ws",
        )
        self.assertEqual(len(self.stored), 1)

    def test_a_failed_store_still_returns_a_usable_chart(self):
        handlers.memory.store_chart = lambda *a, **k: None
        chart_json, error, chart_id = handlers._render_and_store(
            self.df, self.spec, "failed tests by module", "sess",
            "SELECT 1", "user", "ingest-1", "ws",
        )
        self.assertIsNone(error)
        self.assertIsNone(chart_id)
        self.assertTrue(chart_json)


class BackgroundPersistenceTests(unittest.TestCase):
    def test_without_a_running_loop_the_write_still_happens(self):
        # Deferring is a latency optimisation, never a licence to lose the
        # write. Called outside an event loop (tests, scripts) it must fall
        # back to running inline rather than silently dropping the data.
        calls = []
        handlers._persist_in_background(lambda x: calls.append(x), "payload")
        self.assertEqual(calls, ["payload"])

    def test_a_failing_write_does_not_propagate(self):
        def boom():
            raise RuntimeError("lancedb is down")

        handlers._persist_in_background(boom)  # must not raise


if __name__ == "__main__":
    unittest.main()
