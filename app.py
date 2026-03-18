from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import pandas as pd
import os
from typing import List, Optional
from ai_chart_generator import generator

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ChartRequest(BaseModel):
    prompt: str

class ChartResponse(BaseModel):
    success: bool
    chart_id: Optional[str] = None
    config: Optional[dict] = None
    error: Optional[str] = None

# File paths
BASE_DIR = os.path.dirname(__file__)
MASTER_FILE = os.path.join(BASE_DIR, "qa_analytics_master.json")

def load_data():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Original endpoints
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

# New AI endpoints
@app.post("/ai/generate-chart", response_model=ChartResponse)
async def generate_chart(request: ChartRequest):
    """Generate a chart based on user prompt"""
    try:
        result = generator.generate_chart(request.prompt)
        return ChartResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/generated-charts")
async def get_generated_charts():
    """Get all generated charts"""
    try:
        charts = generator.get_all_charts()
        return {"charts": charts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/ai/chart/{chart_id}")
async def delete_chart(chart_id: str):
    """Delete a generated chart"""
    try:
        generator.delete_chart(chart_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)