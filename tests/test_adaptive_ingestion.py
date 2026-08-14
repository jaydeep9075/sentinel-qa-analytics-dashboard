import unittest

import duckdb
import pandas as pd

from services import data_loader, state


class AdaptiveIngestionTests(unittest.TestCase):
    def setUp(self):
        # duck_conn/lance_db/embedder/current_ingestion_id are contextvars
        # (see state.py) - must go through set_active_ingestion, never plain
        # assignment, or this permanently shadows the module __getattr__
        # proxy for the rest of the process (breaking it for every test that
        # runs after this one).
        self._prev = (state.current_ingestion_id, state.duck_conn, state.lance_db, state.embedder)
        state.set_active_ingestion("test", duckdb.connect(), None, None)

    def tearDown(self):
        try:
            if state.duck_conn:
                state.duck_conn.close()
        except Exception:
            pass
        state.set_active_ingestion(*self._prev)

    def test_coerce_generic_alias_mapping(self):
        src = pd.DataFrame(
            [
                {
                    "scenario": "Checkout should pass",
                    "result_text": "success",
                    "elapsed": 12.5,
                    "product": "FSA",
                    "feature": "Checkout",
                    "device": "GoogleChromeiPhoneX",
                    "exception": "",
                },
                {
                    "scenario": "Eligibility fails",
                    "result_text": "error",
                    "elapsed": 9.2,
                    "product": "FSA",
                    "feature": "Eligibility",
                    "device": "GoogleChrome",
                    "exception": "timeout",
                },
            ]
        )

        out = data_loader._coerce_generic_to_flattened_tests(src)
        self.assertEqual(len(out), 2)
        self.assertIn("test_name", out.columns)
        self.assertIn("status", out.columns)
        self.assertIn("module_name", out.columns)
        self.assertEqual(out.iloc[0]["test_name"], "Checkout should pass")
        self.assertEqual(out.iloc[0]["status"], "passed")
        self.assertEqual(out.iloc[1]["status"], "failed")
        self.assertEqual(out.iloc[0]["project_name"], "FSA")
        self.assertEqual(out.iloc[0]["module_name"], "Checkout")

    def test_ingestion_quality_report_scores_good_dataset(self):
        flat = pd.DataFrame(
            [
                {
                    "test_name": "t1",
                    "status": "passed",
                    "duration": 1.2,
                    "project_name": "FSA",
                    "module_name": "M1",
                    "platform_type": "desktop",
                },
                {
                    "test_name": "t2",
                    "status": "failed",
                    "duration": 2.2,
                    "project_name": "FSA",
                    "module_name": "M1",
                    "platform_type": "mobile",
                },
            ]
        )
        mod = pd.DataFrame(
            [
                {
                    "project_name": "FSA",
                    "module_name": "M1",
                    "platform_type": "desktop",
                    "total_tests": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "pending": 0,
                    "unknown": 0,
                    "pass_rate": 100.0,
                    "total_duration_seconds": 1.2,
                    "avg_duration_seconds": 1.2,
                }
            ]
        )
        proj = pd.DataFrame(
            [
                {
                    "project_name": "FSA",
                    "platform_type": "desktop",
                    "module_count": 1,
                    "total_tests": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "pending": 0,
                    "unknown": 0,
                    "pass_rate": 100.0,
                    "total_duration_seconds": 1.2,
                    "avg_duration_seconds": 1.2,
                }
            ]
        )

        state.duck_conn.register("flattened_tests", flat)
        state.duck_conn.register("module_metrics", mod)
        state.duck_conn.register("project_metrics", proj)

        report = data_loader.get_ingestion_quality_report()
        self.assertGreaterEqual(report["score"], 70)
        self.assertIn(report["quality"], {"good", "excellent"})
        self.assertTrue(any(c["name"] == "status normalization" for c in report["checks"]))


if __name__ == "__main__":
    unittest.main()
