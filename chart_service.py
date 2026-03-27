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

# ========== DATA LOADING ==========
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
OLLAMA_MODEL = "qwen2.5-coder:7b"  # or any model you have

def call_ollama(prompt: str, temperature: float = 0.3, timeout: int = 120) -> str:
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
        logger.error(f"Ollama returned {resp.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return None

# ========== CHART GENERATOR ==========
class ChartGenerator:
    def __init__(self):
        self.charts_storage = "generated_charts.json"
        self.df = get_data_safely()
        self.load_charts_storage()
        logger.info(f"ChartGenerator initialized with {len(self.df)} records")

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
        try:
            # If no data, return placeholder
            if self.df.empty:
                return self._create_chart_response(prompt, self._placeholder_chart())

            # Try to generate with AI
            ai_config = self._generate_with_ollama(prompt)
            if ai_config:
                return self._create_chart_response(prompt, ai_config)

            # Fallback: data-driven chart based on prompt keywords
            fallback_config = self._data_driven_chart(prompt)
            return self._create_chart_response(prompt, fallback_config)

        except Exception as e:
            logger.exception("Unexpected error")
            # Ultimate fallback
            fallback = {
                "chart": {"type": "bar", "height": 350},
                "title": {"text": "Chart Generation Failed", "align": "center"},
                "series": [{"name": "Data", "data": [0]}],
                "xaxis": {"categories": ["Error"]}
            }
            return self._create_chart_response(prompt, fallback)

    def _create_chart_response(self, prompt, config):
        chart_id = str(uuid.uuid4())
        entry = {
            "id": chart_id,
            "prompt": prompt,
            "chart_type": config.get("chart", {}).get("type", "bar"),
            "config": config,
            "created_at": datetime.datetime.now().isoformat()
        }
        self.charts.append(entry)
        self.save_charts_storage()
        return {"success": True, "id": chart_id, "config": config}

    def _generate_with_ollama(self, prompt):
        # Build a JSON‑safe summary
        summary = {
            "total_tests": int(len(self.df)),
            "columns": list(self.df.columns),
            "status_counts": self.df['status'].value_counts().to_dict() if 'status' in self.df.columns else {},
            "duration_stats": {
                "mean": float(self.df['duration'].mean()),
                "max": float(self.df['duration'].max()),
                "min": float(self.df['duration'].min())
            } if 'duration' in self.df.columns else {},
            "sample": self._safe_sample()
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
        if not response:
            return None

        # Extract JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            return None
        try:
            config = json.loads(json_match.group())
            if "series" not in config:
                return None
            return config
        except json.JSONDecodeError:
            return None

    def _safe_sample(self):
        """Return the first 10 rows with all fields JSON‑serializable."""
        sample = self.df.head(10).to_dict(orient='records')
        for rec in sample:
            for k, v in rec.items():
                if isinstance(v, (pd.Timestamp, datetime.datetime)):
                    rec[k] = v.isoformat()
                elif isinstance(v, np.integer):
                    rec[k] = int(v)
                elif isinstance(v, np.floating):
                    rec[k] = float(v)
                elif pd.isna(v):
                    rec[k] = None
        return sample

    def _data_driven_chart(self, prompt):
        """Create a chart based on keywords in the prompt, using actual data."""
        prompt_lower = prompt.lower()
        # Determine chart type
        chart_type = 'bar'
        if 'pie' in prompt_lower:
            chart_type = 'pie'
        elif 'line' in prompt_lower:
            chart_type = 'line'

        # Determine data field
        if 'duration' in prompt_lower:
            if chart_type == 'pie':
                # For duration, pie chart doesn't make sense; fallback to bar
                chart_type = 'bar'
            top_n = 10
            if 'top' in prompt_lower:
                match = re.search(r'top\s+(\d+)', prompt_lower)
                if match:
                    top_n = int(match.group(1))
            top_slow = self.df.nlargest(top_n, 'duration')
            return {
                "chart": {"type": "bar", "height": 350},
                "title": {"text": f"Top {top_n} Slowest Tests", "align": "center"},
                "series": [{"name": "Duration (s)", "data": top_slow['duration'].tolist()}],
                "xaxis": {
                    "categories": top_slow['test_name'].tolist(),
                    "title": {"text": "Test Name"}
                },
                "yaxis": {"title": {"text": "Seconds"}}
            }
        elif 'module' in prompt_lower:
            module_counts = self.df['module'].value_counts().head(10)
            if chart_type == 'pie':
                return {
                    "chart": {"type": "pie", "height": 350},
                    "title": {"text": "Tests by Module", "align": "center"},
                    "series": module_counts.values.tolist(),
                    "labels": module_counts.index.tolist()
                }
            else:
                return {
                    "chart": {"type": "bar", "height": 350},
                    "title": {"text": "Tests by Module", "align": "center"},
                    "series": [{"name": "Tests", "data": module_counts.values.tolist()}],
                    "xaxis": {"categories": module_counts.index.tolist()}
                }
        else:
            # Default: status distribution
            status_counts = self.df['status'].value_counts()
            if chart_type == 'pie':
                return {
                    "chart": {"type": "pie", "height": 350},
                    "title": {"text": "Test Status Distribution", "align": "center"},
                    "series": status_counts.values.tolist(),
                    "labels": status_counts.index.tolist()
                }
            else:
                return {
                    "chart": {"type": chart_type, "height": 350},
                    "title": {"text": "Test Status Distribution", "align": "center"},
                    "series": [{"name": "Tests", "data": status_counts.values.tolist()}],
                    "xaxis": {"categories": status_counts.index.tolist()}
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
        logger.exception("Unhandled exception")
        # Return a fallback chart (no 500)
        fallback = {
            "success": True,
            "id": str(uuid.uuid4()),
            "config": {
                "chart": {"type": "bar", "height": 350},
                "title": {"text": "Error generating chart", "align": "center"},
                "series": [{"name": "Data", "data": [0]}],
                "xaxis": {"categories": ["Error"]}
            }
        }
        return fallback

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