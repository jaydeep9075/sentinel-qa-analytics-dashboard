import os
import json
import time
from collections import defaultdict, Counter

SOURCE_PATH = r"D:\FULL_DEV_SMOKE_copy"
HISTORY_PATH = os.path.join(SOURCE_PATH, "history")
OUTPUT_FILE = "qa_analytics_master.json"

def parse_allure():
    container_map = {}
    results = []

    # 1️⃣ Map Containers (Tags/Names)
    for file in os.listdir(SOURCE_PATH):
        if file.endswith("-container.json"):
            with open(os.path.join(SOURCE_PATH, file), 'r', encoding='utf-8') as f:
                c = json.load(f)
                for child_uuid in c.get("children", []):
                    container_map[child_uuid] = c.get("name", "General")

    # 2️⃣ Extract Test Results
    for file in os.listdir(SOURCE_PATH):
        if file.endswith("-result.json"):
            with open(os.path.join(SOURCE_PATH, file), 'r', encoding='utf-8') as f:
                r = json.load(f)
                uuid = r.get("uuid")
                record = {
                    "uuid": uuid,
                    "name": r.get("name"),
                    "module": container_map.get(uuid, "General"),
                    "status": r.get("status"),
                    "duration_sec": round((r.get("stop", 0) - r.get("start", 0)) / 1000, 2),
                    "error_msg": r.get("statusDetails", {}).get("message", "No Error"),
                    "timestamp": r.get("start"),
                    "env": "DEV_SMOKE",
                    "tags": r.get("tags", [])
                }
                results.append(record)

    # 3️⃣ Load Historical Trends
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
        mod_name = t["module"].split()[0]  # take first word as main module
        modules[mod_name]["total"] += 1
        modules[mod_name]["duration_sum"] += t["duration_sec"]
        if t["status"] == "passed":
            modules[mod_name]["passed"] += 1
        else:
            modules[mod_name]["failed"] += 1

    # Compute average duration and failure rate
    for m, stats in modules.items():
        stats["avg_duration_sec"] = round(stats["duration_sum"] / stats["total"], 2)
        stats["failure_rate"] = round(100 * stats["failed"] / stats["total"], 2)
        del stats["duration_sum"]

    # 5️⃣ Precompute Analytics
    # Flaky tests: appeared in both passed and failed
    test_status_map = defaultdict(list)
    for t in results:
        test_status_map[t["name"]].append(t["status"])

    flaky_tests = [name for name, statuses in test_status_map.items() if "passed" in statuses and "failed" in statuses]

    # Slow tests: top 10 by duration
    slow_tests = sorted(results, key=lambda x: x["duration_sec"], reverse=True)[:10]

    # Retry impact: tests that pass only after retry (status failed first, then passed)
    retry_map = defaultdict(list)
    for t in results:
        retry_map[t["name"]].append(t["status"])
    retry_tests = [name for name, statuses in retry_map.items() if statuses.count("failed") > 0 and "passed" in statuses]

    # Module stability list
    module_stability = []
    for m, stats in modules.items():
        module_stability.append({
            "module": m,
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "avg_duration_sec": stats["avg_duration_sec"],
            "failure_rate": stats["failure_rate"]
        })

    # Risk matrix: failure_rate * avg_duration_sec
    risk_matrix = []
    for m, stats in modules.items():
        risk_matrix.append({
            "module": m,
            "risk_score": round(stats["failure_rate"] * stats["avg_duration_sec"], 2)
        })

    # Stability score per test: ratio of passed runs to total runs
    stability_score = []
    for t_name, statuses in test_status_map.items():
        passed = statuses.count("passed")
        total = len(statuses)
        stability_score.append({
            "test": t_name,
            "stability_score": round(passed / total, 2)
        })

    # 6️⃣ Build Master JSON
    master = {
        "metadata": {
            "env": "DEV_SMOKE",
            "generated_at": int(time.time() * 1000),
            "source_path": SOURCE_PATH
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
    print(f"✅ Created {OUTPUT_FILE} with {len(results)} test records, module stats, and analytics.")

if __name__ == "__main__":
    parse_allure()