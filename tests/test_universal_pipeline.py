"""Tests for the generalized ingestion pipeline (core modules + engine)."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Keep tests fast and deterministic: no embedding model, no AI calls.
os.environ["INGEST_EMBED_STRUCTURED"] = "never"

import pandas as pd

from universal_ingester.core.normalizer import normalize_payload
from universal_ingester.core.chunking import chunk_text
from universal_ingester.core.report import IngestionReport
from universal_ingester.core.storage import LanceStorage, sanitize_columns, compute_row_hashes


class NormalizerTests(unittest.TestCase):
    def test_preserves_all_record_arrays(self):
        payload = {
            "run_id": 1,
            "tests": [{"name": "t1"}, {"name": "t2"}],
            "warnings": [{"code": "W1"}],
        }
        res = normalize_payload(payload, "report")
        self.assertIn("report_tests", res.tables)
        self.assertIn("report_warnings", res.tables)  # old pipeline dropped this
        self.assertIn("report", res.tables)
        self.assertEqual(len(res.tables["report_tests"]), 2)
        self.assertEqual(len(res.tables["report_warnings"]), 1)

    def test_nested_arrays_become_child_tables_with_parent_links(self):
        payload = [
            {"name": "t1", "steps": [{"a": 1}, {"a": 2}, {"a": 3}]},
            {"name": "t2", "steps": [{"a": 4}]},
        ]
        res = normalize_payload(payload, "tests")
        self.assertIn("tests_steps", res.tables)
        steps = res.tables["tests_steps"]
        self.assertEqual(len(steps), 4)  # all items, not just the first
        self.assertIn("_parent_id", steps.columns)
        parents = set(res.tables["tests"]["_record_id"])
        self.assertTrue(set(steps["_parent_id"]).issubset(parents))

    def test_deep_nesting_and_mixed_types(self):
        payload = [
            {"id": 1, "info": {"a": {"b": {"c": "deep"}}}, "val": 10},
            {"id": "2", "val": "not-a-number", "extra_key": True},
        ]
        res = normalize_payload(payload, "mixed")
        df = res.tables["mixed"]
        self.assertEqual(len(df), 2)
        self.assertIn("info_a_b_c", df.columns)
        self.assertIn("extra_key", df.columns)  # dynamic key tolerated

    def test_scalar_arrays_kept_as_json(self):
        res = normalize_payload([{"name": "x", "tags": ["a", "b"]}], "d")
        df = res.tables["d"]
        self.assertEqual(json.loads(df.iloc[0]["tags"]), ["a", "b"])


class ChunkingTests(unittest.TestCase):
    def test_short_text_single_chunk(self):
        chunks = chunk_text("hello world")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_count"], 1)

    def test_long_text_chunks_with_indexes(self):
        text = "\n\n".join(f"Paragraph {i}. " + ("word " * 80) for i in range(10))
        chunks = chunk_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertEqual([c["chunk_index"] for c in chunks], list(range(len(chunks))))
        self.assertTrue(all(c["chunk_count"] == len(chunks) for c in chunks))

    def test_empty_text(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text(None), [])


class StorageTests(unittest.TestCase):
    def setUp(self):
        import lancedb
        self.tmp = tempfile.mkdtemp(prefix="lance_test_")
        self.db = lancedb.connect(self.tmp)
        self.report = IngestionReport("build_1")
        self.storage = LanceStorage(self.db, self.report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_metadata_columns_added(self):
        df = pd.DataFrame([{"a": 1}, {"a": 2}])
        stored = self.storage.write_structured("structured_t", df, "build_1", "src_1")
        self.assertEqual(stored, 2)
        out = self.db.open_table("structured_t").to_pandas()
        for col in ["build_id", "_source_id", "_ingested_at", "_content_hash", "_schema_version"]:
            self.assertIn(col, out.columns)
        self.assertTrue((out["build_id"] == "build_1").all())

    def test_dedup_same_build(self):
        df = pd.DataFrame([{"a": 1}, {"a": 2}])
        self.assertEqual(self.storage.write_structured("structured_t", df, "build_1", "s"), 2)
        # Re-ingesting identical rows into the same build is a no-op.
        self.assertEqual(self.storage.write_structured("structured_t", df.copy(), "build_1", "s"), 0)
        # A different build keeps its own copies (trend comparisons need them).
        self.assertEqual(self.storage.write_structured("structured_t", df.copy(), "build_2", "s"), 2)
        self.assertEqual(self.db.open_table("structured_t").count_rows(), 4)

    def test_schema_evolution_new_column_preserved(self):
        self.storage.write_structured("structured_t", pd.DataFrame([{"a": 1}]), "build_1", "s")
        # Second batch has a new column the table doesn't know about.
        stored = self.storage.write_structured(
            "structured_t", pd.DataFrame([{"a": 2, "brand_new": "kept"}]), "build_1", "s"
        )
        self.assertEqual(stored, 1)
        out = self.db.open_table("structured_t").to_pandas()
        extras = [json.loads(x) for x in out["_extra_json"].dropna() if x]
        self.assertTrue(any(e.get("brand_new") == "kept" for e in extras))

    def test_schema_evolution_missing_column_nullfilled(self):
        self.storage.write_structured("structured_t", pd.DataFrame([{"a": 1, "b": "x"}]), "build_1", "s")
        stored = self.storage.write_structured("structured_t", pd.DataFrame([{"a": 2}]), "build_1", "s")
        self.assertEqual(stored, 1)
        out = self.db.open_table("structured_t").to_pandas()
        self.assertEqual(len(out), 2)

    def test_type_conflict_coerced(self):
        self.storage.write_structured("structured_t", pd.DataFrame([{"a": 1.5}]), "build_1", "s")
        stored = self.storage.write_structured(
            "structured_t", pd.DataFrame([{"a": "not-a-number"}]), "build_1", "s"
        )
        self.assertEqual(stored, 1)  # coerced to null, not crashed

    def test_sanitize_columns(self):
        df = pd.DataFrame([{"a.b": 1, "c-d e": 2, "f(g)": 3}])
        out = sanitize_columns(df)
        self.assertEqual(list(out.columns), ["a_b", "c_d_e", "f_g"])

    def test_row_hash_stability(self):
        df1 = pd.DataFrame([{"a": 1, "id": "uuid-1"}])
        df2 = pd.DataFrame([{"a": 1, "id": "uuid-2"}])  # volatile id differs
        self.assertEqual(compute_row_hashes(df1).iloc[0], compute_row_hashes(df2).iloc[0])


class EngineEndToEndTests(unittest.TestCase):
    """Raw JSON file → normalized tables → LanceDB, no embeddings/AI."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingest_e2e_")
        self.data_dir = Path(self.tmp) / "data"
        self.src = Path(self.tmp) / "nested.json"
        self.src.write_text(json.dumps({
            "meta": {"suite": "smoke", "ci": True},
            "results": [
                {"name": "t1", "status": "passed", "checks": [{"ok": True}, {"ok": False}]},
                {"name": "t2", "status": "failed"},
            ],
            "failures": [{"name": "t2", "reason": "timeout"}],
        }), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_raw_json_full_pipeline(self):
        from universal_ingester.ingester import UniversalIngester

        ing = UniversalIngester(data_base_path=str(self.data_dir))
        total = ing.ingest_source({"type": "file", "path": str(self.src)}, "build_x")
        self.assertGreater(total, 0)

        tables = ing.lance_db.table_names()
        # Every record array became a table — including the second one.
        self.assertIn("structured_nested_results", tables)
        self.assertIn("structured_nested_failures", tables)
        self.assertIn("structured_nested_results_checks", tables)
        self.assertIn("sources", tables)

        # Report written and consistent.
        report_path = self.data_dir / "build_x" / "ingestion_report.json"
        self.assertTrue(report_path.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["overall_status"], "completed")
        self.assertGreater(report["totals"]["rows_stored"], 0)

        # Summary still written in the legacy format.
        summary_path = self.data_dir / "build_x" / "summary.json"
        self.assertTrue(summary_path.exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["build_id"], "build_x")
        self.assertIn("metrics", summary)

    def test_malformed_dataset_does_not_abort_run(self):
        from universal_ingester.ingester import UniversalIngester
        import duckdb
        import lancedb

        ing = UniversalIngester(data_base_path=str(self.data_dir))
        ingestion_folder = self.data_dir / "build_y"
        ingestion_folder.mkdir(parents=True, exist_ok=True)

        ing.lance_db = lancedb.connect(str(ingestion_folder / "lancedb"))
        ing.duck_db = duckdb.connect()
        ing.report = IngestionReport("build_y")
        ing.storage = LanceStorage(ing.lance_db, ing.report)

        good = {"name": "good", "type": "raw", "data": [{"a": 1}], "metadata": {}}
        bad = {"name": "bad", "type": "structured", "data": object(), "metadata": {}}  # will explode

        total = 0
        for ds in [bad, good]:
            ing.report.dataset_started(ds["name"], "test")
            try:
                total += ing._ingest_dataset(ds, "test", "build_y")
            except Exception as exc:
                ing.report.dataset_failed(ds["name"], exc)

        self.assertEqual(total, 1)
        report = ing.report.to_dict()
        self.assertEqual(report["datasets"]["bad"]["status"], "failed")
        self.assertEqual(report["datasets"]["good"]["status"], "completed")
        self.assertEqual(report["overall_status"], "partial")


if __name__ == "__main__":
    unittest.main()
