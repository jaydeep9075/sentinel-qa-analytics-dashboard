import os
import json
from ingestors.base import BaseIngestor

class AllureIngestor(BaseIngestor):
    def __init__(self, source_path: str):
        self.source_path = source_path
        
    def fetch_results(self):
        container_map = {}
        results = []
        
        if not os.path.exists(self.source_path):
            print(f"Directory not found: {self.source_path}")
            return []

        # 1️⃣ Map Containers (Tags/Names)
        for file in os.listdir(self.source_path):
            if file.endswith("-container.json"):
                with open(os.path.join(self.source_path, file), 'r', encoding='utf-8') as f:
                    try:
                        c = json.load(f)
                    except: continue
                    for child_uuid in c.get("children", []):
                        container_map[child_uuid] = c.get("name", "General")

        # 2️⃣ Extract Test Results
        for file in os.listdir(self.source_path):
            if file.endswith("-result.json"):
                with open(os.path.join(self.source_path, file), 'r', encoding='utf-8') as f:
                    try:
                        r = json.load(f)
                    except: continue
                    uuid = r.get("uuid")
                    record = {
                        "uuid": uuid,
                        "name": r.get("name", "Unknown"),
                        "module": container_map.get(uuid, "General"),
                        "status": r.get("status", "unknown"),
                        "duration_sec": round((r.get("stop", 0) - r.get("start", 0)) / 1000, 2),
                        "error_msg": r.get("statusDetails", {}).get("message", "No Error") if r.get("statusDetails") else "No Error",
                        "timestamp": r.get("start", 0),
                        "env": r.get("environment", "DEV_SMOKE"), # or custom from allure
                        "tags": [t.get("name") for t in r.get("labels", []) if t.get("name")]
                    }
                    results.append(record)
                    
        return results
