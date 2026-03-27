import json
import os
import uuid
import datetime
import logging
import requests
import pandas as pd
import numpy as np
import duckdb
import lancedb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== DATA LOADING (same as main backend) ==========
DB_PATH = "./sentinel_data"
_flat_df = None

def get_table_list():
    try:
        db = lancedb.connect(DB_PATH)
        result = db.list_tables()
        if hasattr(result, 'tables'):
            return result.tables
        elif isinstance(result, tuple):
            return result[0]
        elif isinstance(result, list):
            return result
        else:
            return list(result) if result else []
    except Exception as e:
        logger.error(f"Error getting table list: {e}")
        return []

def flatten_test_data():
    global _flat_df
    if _flat_df is not None:
        return _flat_df

    try:
        con = duckdb.connect()
        con.execute("INSTALL lance; LOAD lance;")
        lance_file = f"{DB_PATH}/local_test_results.lance"
        if not os.path.exists(lance_file):
            lance_file = f"{DB_PATH}/local_test_results"
            if not os.path.exists(lance_file):
                logger.error("local_test_results not found")
                return pd.DataFrame()
        df_raw = con.execute(f"SELECT * FROM '{lance_file}'").df()
        con.close()
    except Exception as e:
        logger.error(f"DuckDB error: {e}")
        return pd.DataFrame()

    if df_raw.empty:
        return pd.DataFrame()

    rows = []
    for _, row in df_raw.iterrows():
        tests_json = row.get('tests')
        if isinstance(tests_json, str):
            try:
                tests = json.loads(tests_json)
            except:
                continue
        elif isinstance(tests_json, list):
            tests = tests_json
        else:
            continue

        for test in tests:
            test_name = test.get('full_title', '')
            status = test.get('status', '').lower()
            duration_raw = test.get('duration', '0ms')
            if isinstance(duration_raw, str) and duration_raw.endswith('ms'):
                try:
                    duration = float(duration_raw[:-2]) / 1000.0
                except:
                    duration = 0.0
            else:
                duration = float(duration_raw) if duration_raw else 0.0

            error = test.get('error') or ''
            module = test.get('spec_file', '').split('/')[-1] if test.get('spec_file') else ''

            rows.append({
                'test_name': test_name,
                'status': status,
                'duration': duration,
                'error_message': error,
                'module': module,
                'build_id': row.get('build_id'),
                'executed_at': row.get('executed_at'),
            })

    _flat_df = pd.DataFrame(rows)
    logger.info(f"Flattened {len(_flat_df)} individual test records")
    return _flat_df

def get_data_safely():
    df = flatten_test_data()
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    return df

# ========== OLLAMA HELPER ==========
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:7b"  # Use the model you have installed

def call_ollama(prompt: str, temperature: float = 0.3, timeout: int = 120) -> str:
    """Call Ollama to generate a response."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "options": {"num_predict": 1500}
            },
            timeout=timeout
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
        return f"Error: {resp.status_code}"
    except requests.exceptions.Timeout:
        return "Error: AI took too long to respond."
    except Exception as e:
        return f"Error: {str(e)}"

# ========== CHART GENERATOR ==========
class ChartGenerator:
    def __init__(self):
        self.charts_storage = "generated_charts.json"
        self.df = get_data_safely()
        self.load_charts_storage()

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

    def generate_chart(self, prompt: str):
        if self.df.empty:
            # Return a placeholder chart
            placeholder = self._placeholder_chart()
            chart_id = str(uuid.uuid4())
            entry = {
                "id": chart_id,
                "prompt": prompt,
                "chart_type": "bar",
                "config": placeholder,
                "created_at": datetime.datetime.now().isoformat()
            }
            self.charts.append(entry)
            self.save_charts_storage()
            return {"success": True, "id": chart_id, "config": placeholder}

        # Try to use Ollama for chart generation
        chart_config = self._generate_with_ollama(prompt)
        if not chart_config:
            # Fallback to simple chart
            chart_config = self._simple_chart(prompt)

        chart_id = str(uuid.uuid4())
        entry = {
            "id": chart_id,
            "prompt": prompt,
            "chart_type": chart_config.get("chart", {}).get("type", "bar"),
            "config": chart_config,
            "created_at": datetime.datetime.now().isoformat()
        }
        self.charts.append(entry)
        self.save_charts_storage()
        return {"success": True, "id": chart_id, "config": chart_config}

    def _generate_with_ollama(self, prompt):
        # Build a summary of the data
        summary = {
            "total_tests": len(self.df),
            "columns": list(self.df.columns),
            "status_counts": self.df['status'].value_counts().to_dict() if 'status' in self.df.columns else {},
            "duration_stats": {
                "mean": self.df['duration'].mean(),
                "max": self.df['duration'].max(),
                "min": self.df['duration'].min()
            } if 'duration' in self.df.columns else {},
            "sample": self.df.head(10).to_dict(orient='records')
        }

        ai_prompt = f"""You are a data visualization expert. Based on the following test data summary, generate an ApexCharts JSON configuration for the user's request: "{prompt}"

Data Summary:
{json.dumps(summary, indent=2)}

Generate a JSON object with the following structure:
{{
    "chart": {{"type": "bar|line|pie|...", "height": 350}},
    "title": {{"text": "Chart Title", "align": "center"}},
    "series": [{{"name": "Series Name", "data": [values]}}],
    "xaxis": {{"categories": ["labels"]}},
    "yaxis": {{"title": {{"text": "Y Axis Label"}}}}
}}
For pie charts, use "series": [values] and "labels": ["labels"].

Return ONLY the JSON, no additional text."""

        response = call_ollama(ai_prompt, temperature=0.2)
        if response.startswith("Error:"):
            logger.error(f"Ollama error: {response}")
            return None

        # Extract JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            return None
        try:
            config = json.loads(json_match.group())
            # Validate minimal structure
            if "series" not in config:
                return None
            return config
        except json.JSONDecodeError:
            return None

    def _simple_chart(self, prompt):
        # Create a simple chart based on the data
        prompt_lower = prompt.lower()
        if 'pie' in prompt_lower and 'status' in self.df.columns:
            status_counts = self.df['status'].value_counts()
            return {
                "chart": {"type": "pie", "height": 350},
                "title": {"text": "Test Status Distribution", "align": "center"},
                "series": status_counts.values.tolist(),
                "labels": status_counts.index.tolist()
            }
        elif 'status' in self.df.columns:
            status_counts = self.df['status'].value_counts()
            return {
                "chart": {"type": "bar", "height": 350},
                "title": {"text": "Test Status Distribution", "align": "center"},
                "series": [{"name": "Tests", "data": status_counts.values.tolist()}],
                "xaxis": {"categories": status_counts.index.tolist()}
            }
        elif 'duration' in self.df.columns:
            top_slow = self.df.nlargest(10, 'duration')
            return {
                "chart": {"type": "bar", "height": 350},
                "title": {"text": "Top 10 Slowest Tests", "align": "center"},
                "series": [{"name": "Duration (s)", "data": top_slow['duration'].tolist()}],
                "xaxis": {
                    "categories": top_slow['test_name'].tolist() if 'test_name' in self.df.columns else [f"Test {i}" for i in range(len(top_slow))],
                    "title": {"text": "Test Name"}
                },
                "yaxis": {"title": {"text": "Seconds"}}
            }
        else:
            return {
                "chart": {"type": "bar", "height": 350},
                "title": {"text": f"Data Overview ({len(self.df)} records)", "align": "center"},
                "series": [{"name": "Count", "data": list(range(min(20, len(self.df))))}],
                "xaxis": {"categories": [f"Record {i}" for i in range(min(20, len(self.df)))]}
            }

    def _placeholder_chart(self):
        return {
            "chart": {"type": "bar", "height": 350},
            "title": {"text": "No Data Available", "align": "center"},
            "series": [{"name": "Count", "data": [0]}],
            "xaxis": {"categories": ["No data"]}
        }

    def get_all_charts(self):
        return self.charts

    def delete_chart(self, chart_id):
        self.charts = [c for c in self.charts if c["id"] != chart_id]
        self.save_charts_storage()

# ========== FASTAPI ENDPOINTS ==========
generator = ChartGenerator()

class ChartReq(BaseModel):
    message: str

@app.post("/ai/generate-chart")
async def generate_chart(req: ChartReq):
    try:
        result = generator.generate_chart(req.message)
        return result
    except Exception as e:
        logger.exception("Chart generation failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/generated-charts")
async def get_charts():
    return {"charts": generator.get_all_charts()}

@app.delete("/ai/chart/{chart_id}")
async def delete_chart(chart_id: str):
    generator.delete_chart(chart_id)
    return {"success": True}

@app.get("/health")
async def health():
    return {"status": "ok", "data_available": not generator.df.empty, "data_rows": len(generator.df)}

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🎨 CHART SERVICE (Ollama) STARTING ON PORT 8001")
    print("="*70)
    df = get_data_safely()
    print(f"Data loaded: {len(df)} records")
    uvicorn.run(app, host="0.0.0.0", port=8001)