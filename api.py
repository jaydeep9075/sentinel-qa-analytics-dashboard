from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
import pandas as pd
import os

app = FastAPI()

# ✅ CORS (must come AFTER app creation and BEFORE routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ safer file path
BASE_DIR = os.path.dirname(__file__)
MASTER_FILE = os.path.join(BASE_DIR, "qa_analytics_master.json")


def load_data():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/kpis")
def get_kpis():
    data = load_data()
    df = pd.DataFrame(data["tests"])

    return {
        "total": len(df),
        "passed": int((df.status == "passed").sum()),
        "failed": int((df.status == "failed").sum()),
        "avg_duration": round(df.duration_sec.mean(), 2),
    }


@app.get("/status-distribution")
def status_distribution():
    data = load_data()
    df = pd.DataFrame(data["tests"])
    return df.groupby("status").size().to_dict()


@app.get("/module-stability")
def module_stability():
    data = load_data()
    return data["analytics"]["module_stability"]


@app.get("/slow-tests")
def slow_tests():
    data = load_data()
    return data["analytics"]["slow_tests"]


@app.get("/history-trend")
def history_trend():
    data = load_data()
    return data["trends"]["history-trend"]


@app.get("/failures")
def failures():
    data = load_data()
    df = pd.DataFrame(data["tests"])
    failures = df[df.status == "failed"]
    return failures.to_dict(orient="records")