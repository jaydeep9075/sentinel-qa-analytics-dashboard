import os
import json

SOURCE_PATH = r"D:\FULL_DEV_SMOKE_copy"
HISTORY_PATH = os.path.join(SOURCE_PATH, "history")
OUTPUT_FILE = "qa_analytics_master.json"

def parse_allure():
    container_map = {}
    results = []

    # 1. Map Containers (Tags/Names)
    for file in os.listdir(SOURCE_PATH):
        if file.endswith("-container.json"):
            with open(os.path.join(SOURCE_PATH, file), 'r', encoding='utf-8') as f:
                c = json.load(f)
                for child_uuid in c.get("children", []):
                    container_map[child_uuid] = c.get("name", "General")

    # 2. Extract Results
    for file in os.listdir(SOURCE_PATH):
        if file.endswith("-result.json"):
            with open(os.path.join(SOURCE_PATH, file), 'r', encoding='utf-8') as f:
                r = json.load(f)
                uuid = r.get("uuid")
                
                record = {
                    "test_uuid": uuid,
                    "name": r.get("name"),
                    "module": container_map.get(uuid, "General"),
                    "status": r.get("status"),
                    "duration_sec": round((r.get("stop", 0) - r.get("start", 0)) / 1000, 2),
                    "error_msg": r.get("statusDetails", {}).get("message", "No Error"),
                    "timestamp": r.get("start"),
                    "env": "DEV_SMOKE"
                }
                results.append(record)

    # 3. Load Historical Trends
    trends = {}
    trend_files = ["history-trend.json", "categories-trend.json", "duration-trend.json", "retry-trend.json"]
    for tf in trend_files:
        path = os.path.join(HISTORY_PATH, tf)
        if os.path.exists(path):
            with open(path, 'r') as f:
                trends[tf.replace(".json","")] = json.load(f)
        else:
            trends[tf.replace(".json","")] = []

    master = {
        "tests": results,
        "trends": trends
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=4)
    print(f"✅ Created {OUTPUT_FILE} with {len(results)} test records and trend data.")

if __name__ == "__main__":
    parse_allure()