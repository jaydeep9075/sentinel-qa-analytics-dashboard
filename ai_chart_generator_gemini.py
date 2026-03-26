import json
import pandas as pd
import numpy as np
import uuid
import os
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ==============================
# Modern Gemini AI Imports
# ==============================
try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("Please install the latest google-genai package: pip install google-genai")

# ==============================
# AI Chart Generator Class
# ==============================
class AIChartGenerator:
    def __init__(self, master_file_path: str):
        self.master_file_path = master_file_path
        self.charts_storage = "generated_charts.json"
        self.data = self.load_data()
        self.df = self.prepare_dataframe()

        # === Hardcoded Gemini API key ===
        self.gemini_api_key = "AIzaSyBTvl5EsJblAJrJiuSWJAKeWOcfRDQxczA"
 
        self.use_gemini = bool(self.gemini_api_key)

        if self.use_gemini:
            try:
                self.client = genai.Client(api_key=self.gemini_api_key)
                self.model_id = "gemini-2.0-flash"
                print(f"✅ Gemini AI initialized successfully (Model: {self.model_id})")
            except Exception as e:
                print(f"⚠️ Failed to initialize Gemini: {e}")
                self.use_gemini = False

        self.load_charts_storage()

    def load_data(self) -> Dict:
        if os.path.exists(self.master_file_path):
            with open(self.master_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"tests": []}

    def prepare_dataframe(self) -> pd.DataFrame:
        df = pd.DataFrame(self.data.get("tests", []))
        if not df.empty and "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"], unit='ms')
        return df

    def load_charts_storage(self):
        if os.path.exists(self.charts_storage):
            try:
                with open(self.charts_storage, 'r') as f:
                    self.charts = json.load(f)
            except:
                self.charts = []
        else:
            self.charts = []

    def save_charts_storage(self):
        with open(self.charts_storage, 'w') as f:
            json.dump(self.charts, f, indent=2)

    # --- AI Methods ---
    def generate_chart(self, prompt: str) -> Dict[str, Any]:
        if not self.use_gemini:
            return {"success": False, "error": "AI not configured"}
        try:
            columns = list(self.df.columns)
            ai_prompt = f"""
DataFrame columns: {columns}
User request: "{prompt}"
Write a Python function `create_chart(df)` returning an ApexCharts JSON object.
The JSON must have 'type', 'series', and 'options'.
Return ONLY the python code.
"""
            response = self.client.models.generate_content(model=self.model_id, contents=ai_prompt)
            code = response.text.replace("```python", "").replace("```", "").strip()

            local_vars = {}
            exec(code, {'pd': pd, 'np': np}, local_vars)
            chart_config = local_vars['create_chart'](self.df)

            chart_id = str(uuid.uuid4())
            entry = {"id": chart_id, "prompt": prompt, "config": chart_config, "created_at": datetime.now().isoformat()}
            self.charts.append(entry)
            self.save_charts_storage()
            return {"success": True, "chart_id": chart_id, "config": chart_config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def generate_chat_response(self, message: str) -> str:
        if not self.use_gemini:
            return "AI disabled."

        summary = {
            "total": len(self.df),
            "passed": int((self.df['status'] == 'passed').sum()) if 'status' in self.df.columns else 0,
            "failed": int((self.df['status'] == 'failed').sum()) if 'status' in self.df.columns else 0,
            "modules": self.df['module'].unique().tolist() if 'module' in self.df.columns else []
        }

        prompt = f"Data Summary: {json.dumps(summary)}\nUser Question: {message}\nAnswer concisely as a QA assistant."

        try:
            res = self.client.models.generate_content(model=self.model_id, contents=prompt)
            return res.text
        except Exception as e:
            return f"Error: {e}"

# ==============================
# FastAPI Endpoints
# ==============================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MASTER_FILE = "qa_analytics_master.json"
generator = AIChartGenerator(MASTER_FILE)

class ChartReq(BaseModel):
    prompt: str

class ChatReq(BaseModel):
    message: str

@app.post("/ai/generate-chart")
async def api_gen_chart(req: ChartReq):
    return generator.generate_chart(req.prompt)

@app.post("/ai/chat")
async def api_chat(req: ChatReq):
    return {"response": generator.generate_chat_response(req.message)}

@app.get("/ai/generated-charts")
async def get_all_charts():
    return {"charts": generator.charts}

@app.delete("/ai/chart/{chart_id}")
async def delete_chart(chart_id: str):
    generator.charts = [c for c in generator.charts if c["id"] != chart_id]
    generator.save_charts_storage()
    return {"success": True}

@app.get("/ai/status")
async def get_status():
    return {"mode": "gemini" if generator.use_gemini else "demo", "total_charts": len(generator.charts)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
