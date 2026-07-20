"""Build summary generation (summary.md + summary.json).

This is domain logic for QA test data (Allure), extracted from the
universal ingestion engine — the engine stays data-source independent and
calls this as a post-ingestion step. Output format is unchanged so the
dashboard, build-trends page and data_loader keep working.
"""

import json
import logging
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def parse_duration(val):
    """Robust duration parser: '43758ms', '88ms', '1.5s', numeric seconds."""
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith('ms'):
            try:
                return float(val[:-2]) / 1000.0
            except Exception:
                pass
        match = re.match(r'^([\d.]+)\s*(ms|s|m|h)?$', val)
        if match:
            num = float(match.group(1))
            unit = match.group(2) or 's'
            if unit == 'ms':
                return num / 1000.0
            elif unit == 'm':
                return num * 60.0
            elif unit == 'h':
                return num * 3600.0
            return num
    return None


def collect_parser_insights(lance_db) -> dict:
    insights = {
        "total_sources": 0,
        "strategies": {},
        "avg_confidence": 0.0,
        "ai_fallback_used": 0,
    }
    if not lance_db or "sources" not in lance_db.table_names():
        return insights
    try:
        df_sources = lance_db.open_table("sources").to_pandas()
        if df_sources.empty:
            return insights

        strategies = {}
        confidences = []
        ai_count = 0
        for _, row in df_sources.iterrows():
            raw_meta = row.get("metadata", "{}")
            try:
                meta = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
            except Exception:
                meta = {}
            strategy = str(meta.get("parser_strategy", "unknown"))
            strategies[strategy] = strategies.get(strategy, 0) + 1
            conf = meta.get("parser_confidence")
            if isinstance(conf, (int, float)):
                confidences.append(float(conf))
            if strategy == "ai-structured-fallback":
                ai_count += 1

        insights["total_sources"] = int(len(df_sources))
        insights["strategies"] = strategies
        insights["avg_confidence"] = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        insights["ai_fallback_used"] = ai_count
        return insights
    except Exception as exc:
        logger.warning(f"Failed to collect parser insights: {exc}")
        return insights


def generate_summary(lance_db, data_base_path, build_id: str, total_rows: int, ingestion_report: dict = None):
    """Generate summary.md and summary.json from structured_test_results.
    Handles both old format (JSON 'tests' column) and new normalized format.
    Pass rate calculated as passed/(passed+failed) to match Allure behavior."""
    summary_md_path = data_base_path / build_id / "summary.md"
    summary_json_path = data_base_path / build_id / "summary.json"

    metrics = {
        "total_tests": 0,
        "executed_tests": 0,
        "skipped_tests": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
        "module_count": 0,
        "avg_duration_sec": 0.0,
        "total_duration_sec": 0.0,
        "most_common_error": "",
        "slowest_tests": [],
        "modules": {},
        "projects": {}
    }

    lines = [
        f"# Ingestion Summary: {build_id}",
        "",
        f"**Ingested at:** {datetime.now(timezone.utc).isoformat()}",
        f"**Total records ingested:** {total_rows}",
        "",
    ]

    parser_insights = collect_parser_insights(lance_db)
    tables_in_db = lance_db.table_names()
    logger.info(f"Tables in DB: {tables_in_db}")

    def _write_json(extra=None):
        json_data = {
            "build_id": build_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "total_records_ingested": total_rows,
            "metrics": metrics,
            "tables": tables_in_db,
            "parser_insights": parser_insights,
        }
        if ingestion_report:
            json_data["ingestion_report"] = ingestion_report
        if extra:
            json_data.update(extra)
        with open(summary_json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON summary written to {summary_json_path}")

    if "structured_test_results" not in tables_in_db:
        lines.append("## ⚠️ Test Metrics")
        lines.append("No `structured_test_results` table found.")
        lines.append("")
        lines.append("## 🧠 Parser Insights")
        lines.append(f"- Total sources: {parser_insights.get('total_sources', 0)}")
        lines.append(f"- Avg parser confidence: {parser_insights.get('avg_confidence', 0.0)}")
        lines.append(f"- AI fallback used: {parser_insights.get('ai_fallback_used', 0)}")
        lines.append("\n## 📁 Tables in this ingestion")
        for t in tables_in_db:
            lines.append(f"- `{t}`")
        summary_md_path.write_text("\n".join(lines), encoding='utf-8')
        _write_json()
        return

    try:
        df_results = lance_db.open_table("structured_test_results").to_pandas()
        logger.info(f"structured_test_results rows: {len(df_results)}")

        all_tests = []

        if 'tests' in df_results.columns:
            # OLD FORMAT: JSON blob in 'tests' column
            logger.info("Using old format: extracting tests from 'tests' JSON column")
            for tests_raw in df_results['tests'].dropna():
                if isinstance(tests_raw, str):
                    try:
                        tests_data = json.loads(tests_raw)
                    except Exception as e:
                        logger.warning(f"Failed to parse tests JSON: {e}")
                        continue
                elif isinstance(tests_raw, np.ndarray):
                    tests_data = tests_raw.tolist()
                else:
                    tests_data = tests_raw

                if isinstance(tests_data, list):
                    all_tests.extend(tests_data)
                elif isinstance(tests_data, dict):
                    found = False
                    for key in ['test_cases', 'tests', 'cases', 'results', 'items', 'data']:
                        if key in tests_data and isinstance(tests_data[key], list):
                            all_tests.extend(tests_data[key])
                            found = True
                            break
                    if not found:
                        all_tests.append(tests_data)
        else:
            # NEW FORMAT: normalized columns (one row per test)
            logger.info("Using new normalized format: converting rows to test objects")
            records = df_results.to_dict(orient="records")
            for row in records:
                test_obj = {}
                test_obj['full_title'] = row.get('test_name') or row.get('full_name') or row.get('name') or ''
                test_obj['name'] = row.get('test_name') or row.get('name') or ''
                test_obj['status'] = row.get('status', '')
                test_obj['duration'] = row.get('duration', '0ms')
                test_obj['error'] = row.get('error_message', '')
                test_obj['spec_file'] = row.get('spec_file', '')
                test_obj['description'] = row.get('description', '')
                test_obj['project_name'] = row.get('project_name', 'unknown')
                test_obj['module_name'] = row.get('module_name', 'unknown')
                test_obj['platform_type'] = row.get('platform_type', 'desktop')

                labels_val = row.get('labels', {})
                if isinstance(labels_val, str):
                    try:
                        test_obj['labels'] = json.loads(labels_val)
                    except Exception:
                        test_obj['labels'] = {}
                else:
                    test_obj['labels'] = labels_val

                tags_val = row.get('tags', [])
                if isinstance(tags_val, str):
                    try:
                        test_obj['tags'] = json.loads(tags_val)
                    except Exception:
                        test_obj['tags'] = []
                else:
                    test_obj['tags'] = tags_val

                test_obj['uuid'] = row.get('id', '')
                test_obj['history_id'] = row.get('history_id', '')
                test_obj['duration_seconds'] = row.get('duration_seconds', 0)
                all_tests.append(test_obj)

        logger.info(f"Extracted {len(all_tests)} individual test records")

        if not all_tests:
            lines.append("## ⚠️ Test Metrics")
            lines.append("No test records found in table.")
            summary_md_path.write_text("\n".join(lines), encoding='utf-8')
            _write_json()
            return

        df_tests = pd.DataFrame(all_tests)

        # --- Flexible column detection ---
        test_name_col = next((c for c in ['full_title', 'title', 'test_name', 'name'] if c in df_tests.columns), None)
        status_col = next((c for c in ['status', 'state', 'outcome', 'result'] if c in df_tests.columns), None)
        duration_col = next((c for c in ['duration', 'duration_ms', 'time'] if c in df_tests.columns), None)
        error_col = next((c for c in ['error', 'error_message', 'message'] if c in df_tests.columns), None)

        logger.info(f"Detected columns: name={test_name_col}, status={status_col}, duration={duration_col}, error={error_col}")

        if not (status_col and test_name_col and duration_col):
            lines.append("## ⚠️ Test Metrics")
            lines.append(f"Missing required columns. Found: name={test_name_col}, status={status_col}, duration={duration_col}")
            summary_md_path.write_text("\n".join(lines), encoding='utf-8')
            _write_json()
            return

        if 'duration_seconds' in df_tests.columns:
            df_tests['duration_seconds'] = pd.to_numeric(df_tests['duration_seconds'], errors='coerce')
        else:
            df_tests['duration_seconds'] = df_tests[duration_col].apply(parse_duration)
        valid_durations = df_tests['duration_seconds'].dropna()

        # --- Calculate metrics (Allure-style pass rate) ---
        total_tests = len(df_tests)
        status_series = df_tests[status_col].astype(str).str.lower()
        passed = status_series.eq('passed').sum()
        failed = status_series.isin(['failed', 'broken', 'error']).sum()
        skipped = status_series.isin(['skipped', 'pending', 'unknown']).sum()
        executed_tests = passed + failed
        pass_rate = (passed / executed_tests * 100) if executed_tests > 0 else 0.0

        avg_duration = valid_durations.mean() if len(valid_durations) > 0 else 0.0
        total_duration = valid_durations.sum() if len(valid_durations) > 0 else 0.0

        slowest = []
        if not df_tests.empty and len(valid_durations) > 0:
            df_valid = df_tests[df_tests['duration_seconds'].notna()].copy()
            if not df_valid.empty:
                df_top = df_valid.nlargest(15, 'duration_seconds')
                slowest = [
                    {"name": str(row[test_name_col]), "duration_sec": round(row['duration_seconds'], 2)}
                    for _, row in df_top.iterrows()
                ]

        common_error = ""
        if error_col and error_col in df_tests.columns:
            failed_mask = status_series.isin(['failed', 'broken', 'error'])
            errors = df_tests.loc[failed_mask, error_col].dropna()
            error_strings = []
            for err in errors:
                if isinstance(err, dict):
                    msg = err.get('message', '') or str(err)
                else:
                    msg = str(err)
                if msg and msg.strip() and msg != '{}' and msg != 'nan':
                    error_strings.append(msg.strip())
            if error_strings:
                common_error = pd.Series(error_strings).mode().iloc[0][:200]

        metrics.update({
            "total_tests": int(total_tests),
            "executed_tests": int(executed_tests),
            "skipped_tests": int(skipped),
            "passed": int(passed),
            "failed": int(failed),
            "pass_rate": round(pass_rate, 2),
            "avg_duration_sec": round(avg_duration, 2),
            "total_duration_sec": round(total_duration, 2),
            "most_common_error": common_error,
            "slowest_tests": slowest,
        })

        module_metrics = {}
        if "structured_test_module_metrics" in tables_in_db:
            df_module = lance_db.open_table("structured_test_module_metrics").to_pandas()
            for _, row in df_module.iterrows():
                module_name = str(row.get("module_name", "unknown")) or "unknown"
                module_metrics[module_name] = {
                    "project_name": str(row.get("project_name", "unknown")),
                    "platform_type": str(row.get("platform_type", "desktop")),
                    "tests_per_module": int(row.get("total_tests", 0) or 0),
                    "passed": int(row.get("passed", 0) or 0),
                    "failed": int(row.get("failed", 0) or 0),
                    "skipped": int(row.get("skipped", 0) or 0),
                    "pending": int(row.get("pending", 0) or 0),
                    "unknown": int(row.get("unknown", 0) or 0),
                    "pass_rate": float(row.get("pass_rate", 0.0) or 0.0),
                    "total_execution_time_sec": float(row.get("total_duration_seconds", 0.0) or 0.0),
                    "avg_execution_time_sec": float(row.get("avg_duration_seconds", 0.0) or 0.0),
                }
        elif "module_name" in df_tests.columns:
            # Fallback: compute from test-level table if module table is unavailable.
            if "project_name" not in df_tests.columns:
                df_tests["project_name"] = "unknown"
            if "platform_type" not in df_tests.columns:
                df_tests["platform_type"] = "desktop"
            df_module = df_tests.copy()
            df_module["normalized_status"] = status_series
            grouped_module = df_module.groupby(["module_name", "project_name", "platform_type"], dropna=False)
            for (module_name, project_name, platform_type), grp in grouped_module:
                statuses = grp["normalized_status"].astype(str).str.lower()
                passed_m = int(statuses.eq("passed").sum())
                failed_m = int(statuses.isin(["failed", "broken", "error"]).sum())
                skipped_m = int(statuses.isin(["skipped"]).sum())
                pending_m = int(statuses.isin(["pending"]).sum())
                unknown_m = int(statuses.isin(["unknown"]).sum())
                executed_m = passed_m + failed_m
                total_m = int(len(grp))
                module_metrics[str(module_name)] = {
                    "project_name": str(project_name),
                    "platform_type": str(platform_type),
                    "tests_per_module": total_m,
                    "passed": passed_m,
                    "failed": failed_m,
                    "skipped": skipped_m,
                    "pending": pending_m,
                    "unknown": unknown_m,
                    "pass_rate": round((passed_m / executed_m * 100), 2) if executed_m else 0.0,
                    "total_execution_time_sec": round(float(grp["duration_seconds"].sum()), 2),
                    "avg_execution_time_sec": round(float(grp["duration_seconds"].mean()), 2) if total_m else 0.0,
                }

        project_metrics = {}
        if "structured_test_project_metrics" in tables_in_db:
            df_project = lance_db.open_table("structured_test_project_metrics").to_pandas()
            for _, row in df_project.iterrows():
                project_name = str(row.get("project_name", "unknown"))
                key = f"{project_name}:{str(row.get('platform_type', 'desktop'))}"
                project_metrics[key] = {
                    "project_name": project_name,
                    "platform_type": str(row.get("platform_type", "desktop")),
                    "module_count": int(row.get("module_count", 0) or 0),
                    "total_tests": int(row.get("total_tests", 0) or 0),
                    "passed": int(row.get("passed", 0) or 0),
                    "failed": int(row.get("failed", 0) or 0),
                    "skipped": int(row.get("skipped", 0) or 0),
                    "pass_rate": float(row.get("pass_rate", 0.0) or 0.0),
                    "total_execution_time_sec": float(row.get("total_duration_seconds", 0.0) or 0.0),
                }

        metrics["modules"] = module_metrics
        metrics["projects"] = project_metrics
        metrics["module_count"] = len(module_metrics)

        lines.append("## 📊 Test Metrics")
        lines.append(f"- **Total number of tests:** {total_tests}")
        lines.append(f"- **Executed tests:** {executed_tests} (passed + failed)")
        lines.append(f"- **Skipped/Pending tests:** {skipped}")
        lines.append(f"- **Passed tests:** {passed}")
        lines.append(f"- **Failed tests:** {failed}")
        lines.append(f"- **Pass rate (executed only):** {pass_rate:.2f}%")
        lines.append(f"- **Average duration:** {avg_duration:.2f} seconds")
        lines.append(f"- **Total duration:** {total_duration:.2f} seconds")
        lines.append(f"- **Most common failure reason:** {common_error if common_error else '(no error messages captured)'}")

        if slowest:
            lines.append("\n### 🐢 Top 15 Slowest Tests")
            lines.append("| Test Name | Duration (seconds) |")
            lines.append("|-----------|--------------------|")
            for item in slowest:
                name = item["name"]
                dur = item["duration_sec"]
                display_name = name[:80] + "..." if len(name) > 80 else name
                lines.append(f"| {display_name} | {dur:.2f} |")
        else:
            lines.append("\n### 🐢 Top 15 Slowest Tests\nNo duration data available.")

    except Exception as e:
        logger.error(f"Error generating summary: {e}", exc_info=True)
        lines.append("\n## ⚠️ Test Metrics")
        lines.append(f"Error computing metrics: {str(e)}")

    lines.append("\n## 📁 Tables in this ingestion")
    for t in tables_in_db:
        lines.append(f"- `{t}`")

    summary_md_path.write_text("\n".join(lines), encoding='utf-8')
    logger.info(f"Markdown summary written to {summary_md_path}")
    _write_json()
