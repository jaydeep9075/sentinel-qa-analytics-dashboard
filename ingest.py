import os
import json
import time
from collections import defaultdict

from ingestors.allure_ingestor import AllureIngestor
from ingestors.api_ingestor import APIIngestor
from ingestors.generic_ai_ingestor import GenericAIIngestor

SOURCE_PATH = r"D:\FULL_DEV_SMOKE_copy"
HISTORY_PATH = os.path.join(SOURCE_PATH, "history")
OUTPUT_FILE = "qa_analytics_master.json"

def run_pipeline():
    # 1️⃣ Initialize Ingestors
    ingestors = [
        AllureIngestor(source_path=SOURCE_PATH),
        
        # Example of plugging in a REST API:
        # APIIngestor(api_endpoint="https://api.example.com/tests", api_key="OPTIONAL_KEY"),
        
        # Example of dynamic AI mapping for an arbitrary CSV:
        # GenericAIIngestor(data_source="path/to/custom_results.csv", gemini_api_key=os.getenv("GEMINI_API_KEY"))
    ]
    
    # 2️⃣ Fetch and Merge Results
    results = []
    for ingestor in ingestors:
        print(f"Fetching data from {ingestor.__class__.__name__}...")
        ingestor_results = ingestor.fetch_results()
        results.extend(ingestor_results)
        
    if not results:
        print("⚠️ No test results found across all ingestors.")
        return

    # 3️⃣ Load Historical Trends (can be abstracted layer)
    trends = {}
    trend_files = ["history-trend.json", "categories-trend.json", "duration-trend.json", "retry-trend.json"]
    for tf in trend_files:
        path = os.path.join(HISTORY_PATH, tf)
        if os.path.exists(path):
            with open(path, 'r') as f:
                trends[tf.replace(".json","")] = json.load(f)
        else:
            trends[tf.replace(".json","")] = []

    # 4️⃣ Compute Module-Level Stats
    modules = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "duration_sum": 0})
    for t in results:
        mod_name = t["module"].split()[0] if t["module"] else "General"
        modules[mod_name]["total"] += 1
        modules[mod_name]["duration_sum"] += t.get("duration_sec", 0)
        if t["status"] == "passed":
            modules[mod_name]["passed"] += 1
        elif t["status"] == "failed":
            modules[mod_name]["failed"] += 1

    for m, stats in modules.items():
        if stats["total"] > 0:
            stats["avg_duration_sec"] = round(stats["duration_sum"] / stats["total"], 2)
            stats["failure_rate"] = round(100 * stats["failed"] / stats["total"], 2)
        else:
            stats["avg_duration_sec"] = 0
            stats["failure_rate"] = 0
        del stats["duration_sum"]

    # 5️⃣ Precompute Analytics
    test_status_map = defaultdict(list)
    for t in results:
        test_status_map[t["name"]].append(t["status"])

    flaky_tests = [name for name, statuses in test_status_map.items() if "passed" in statuses and "failed" in statuses]
    slow_tests = sorted(results, key=lambda x: x.get("duration_sec", 0), reverse=True)[:10]

    retry_map = defaultdict(list)
    for t in results:
        retry_map[t["name"]].append(t["status"])
    retry_tests = [name for name, statuses in retry_map.items() if "failed" in statuses and "passed" in statuses]

    module_stability = []
    risk_matrix = []
    for m, stats in modules.items():
        module_stability.append({
            "module": m,
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "avg_duration_sec": stats.get("avg_duration_sec", 0),
            "failure_rate": stats.get("failure_rate", 0)
        })
        risk_matrix.append({
            "module": m,
            "risk_score": round(stats.get("failure_rate", 0) * stats.get("avg_duration_sec", 0), 2)
        })

    stability_score = []
    for t_name, statuses in test_status_map.items():
        passed = statuses.count("passed")
        total = len(statuses)
        stability_score.append({
            "test": t_name,
            "stability_score": round(passed / total, 2) if total > 0 else 0
        })

    # 6️⃣ Build Master JSON
    master = {
        "metadata": {
            "env": "MULTIPLE",
            "generated_at": int(time.time() * 1000),
            "total_records": len(results)
        },
        "tests": results,
        "modules": modules,
        "trends": trends,
        "analytics": {
            "flaky_tests": flaky_tests,
            "slow_tests": slow_tests,
            "retry_impact": retry_tests,
            "module_stability": module_stability,
            "risk_matrix": risk_matrix,
            "stability_score": stability_score
        }
    }

    # 7️⃣ Write to JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=4)
    print(f"✅ Created {OUTPUT_FILE} with {len(results)} test records from multiple sources.")

if __name__ == "__main__":
    run_pipeline()