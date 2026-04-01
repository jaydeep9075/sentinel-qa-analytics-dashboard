import os
import json
import uuid
import datetime
import logging
import re
import pandas as pd
import numpy as np
import lancedb
import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
import requests
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
charts = []
flattened_df = None
duck_conn = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global charts, flattened_df, duck_conn
    logger.info("Starting up...")
    init_database()
    load_charts()
    yield
    # Shutdown
    logger.info("Shutting down...")
    if duck_conn:
        duck_conn.close()

app = FastAPI(title="Sentinel QA Chart Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration - FIXED PATH
DB_PATH = "../data"  # Changed from "./data" to "../data" since we're in services folder
CHARTS_FILE = "generated_charts.json"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

class ChartRequest(BaseModel):
    message: str

def clean_for_json(obj):
    """Recursively clean objects for JSON serialization"""
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif pd.isna(obj):
        return None
    return obj

def init_database():
    """Initialize data from LanceDB"""
    global flattened_df, duck_conn
    
    db_path = Path(DB_PATH)
    if not db_path.exists():
        logger.warning(f"Data path {DB_PATH} not found")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Looking for data at: {db_path.absolute()}")
        flattened_df = pd.DataFrame()
        return
    
    try:
        db = lancedb.connect(str(db_path))
        
        # Get tables using the correct method
        if hasattr(db, 'table_names'):
            tables = db.table_names()
        else:
            tables = db.list_tables()
            
        logger.info(f"Available tables: {tables}")
        
        # Initialize DuckDB for SQL queries
        duck_conn = duckdb.connect()
        
        if "test_cases" in tables:
            test_cases = db.open_table("test_cases").to_pandas()
            duck_conn.register("test_cases", test_cases)
            logger.info(f"✅ Loaded {len(test_cases)} test cases")
        
        if "test_results" in tables:
            test_results = db.open_table("test_results").to_pandas()
            duck_conn.register("test_results", test_results)
            logger.info(f"✅ Loaded {len(test_results)} test results")
            
            # Flatten test results
            rows = []
            for _, row in test_results.iterrows():
                tests = row.get('tests')
                if isinstance(tests, str):
                    try:
                        tests = json.loads(tests)
                    except:
                        continue
                elif not isinstance(tests, list):
                    continue
                
                for test in tests:
                    test_name = test.get('full_title', '')
                    status = test.get('status', '').lower()
                    duration_raw = test.get('duration', '0')
                    
                    # Parse duration
                    if isinstance(duration_raw, str):
                        if duration_raw.endswith('ms'):
                            duration = float(duration_raw[:-2]) / 1000
                        else:
                            try:
                                duration = float(duration_raw) if duration_raw else 0
                            except:
                                duration = 0
                    else:
                        duration = float(duration_raw) if duration_raw else 0
                    
                    error = test.get('error', '')
                    module = test.get('spec_file', '').split('/')[-1] if test.get('spec_file') else ''
                    
                    rows.append({
                        'test_name': test_name,
                        'status': status,
                        'duration': duration,
                        'error_message': error,
                        'module': module,
                        'build_id': row.get('build_id'),
                        'executed_at': row.get('executed_at')
                    })
            
            flattened_df = pd.DataFrame(rows)
            logger.info(f"✅ Loaded {len(flattened_df)} flattened test records")
            
            if not flattened_df.empty:
                # Replace NaN with None for JSON serialization
                flattened_df = flattened_df.replace({np.nan: None, np.inf: None, -np.inf: None})
                logger.info(f"   Columns: {list(flattened_df.columns)}")
                logger.info(f"   Statuses: {flattened_df['status'].value_counts().to_dict()}")
                
                # Register flattened data in DuckDB
                duck_conn.register("flattened_tests", flattened_df)
                logger.info("✅ Registered flattened_tests in DuckDB")
        else:
            logger.warning("No test_results table found")
            flattened_df = pd.DataFrame()
            
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        flattened_df = pd.DataFrame()

def load_charts():
    """Load saved charts from file"""
    global charts
    
    if os.path.exists(CHARTS_FILE):
        try:
            with open(CHARTS_FILE, 'r') as f:
                charts = json.load(f)
            logger.info(f"Loaded {len(charts)} saved charts")
        except:
            charts = []
    else:
        charts = []

def save_charts():
    """Save charts to file with JSON serialization"""
    # Clean charts before saving
    clean_charts = []
    for chart in charts:
        clean_chart = clean_for_json(chart)
        clean_charts.append(clean_chart)
    
    with open(CHARTS_FILE, 'w') as f:
        json.dump(clean_charts, f, indent=2)

def call_ollama(prompt: str, temperature: float = 0.2) -> str:
    """Call Ollama for chart generation"""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "options": {"num_predict": 2000}
            },
            timeout=300
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        return None
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return None

def generate_chart_with_ai(prompt: str) -> dict:
    """Use AI to generate chart configuration"""
    if flattened_df.empty:
        return create_placeholder_chart("No Data Available")
    
    # Prepare data summary for AI with clean values
    try:
        status_counts = flattened_df['status'].value_counts().to_dict() if 'status' in flattened_df.columns else {}
        duration_stats = {}
        if 'duration' in flattened_df.columns:
            duration_stats = {
                "mean": float(flattened_df['duration'].mean()) if not pd.isna(flattened_df['duration'].mean()) else 0,
                "max": float(flattened_df['duration'].max()) if not pd.isna(flattened_df['duration'].max()) else 0,
                "min": float(flattened_df['duration'].min()) if not pd.isna(flattened_df['duration'].min()) else 0
            }
        
        summary = {
            "total_records": len(flattened_df),
            "columns": list(flattened_df.columns),
            "status_counts": status_counts,
            "duration_stats": duration_stats,
            "sample_data": flattened_df.head(10).replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient='records')
        }
    except Exception as e:
        logger.error(f"Error preparing summary: {e}")
        summary = {"total_records": len(flattened_df)}
    
    ai_prompt = f"""You are a data visualization expert. Create an ApexCharts JSON configuration based on the user request.

User Request: "{prompt}"

Data Summary:
{json.dumps(summary, indent=2, default=str)}

Generate a valid ApexCharts configuration JSON with this structure:
{{
    "chart": {{"type": "bar|line|pie|area|heatmap", "height": 350}},
    "title": {{"text": "Chart Title", "align": "center"}},
    "series": [{{"name": "Series Name", "data": [values]}}],
    "xaxis": {{"categories": ["labels"]}},
    "yaxis": {{"title": {{"text": "Y Axis Label"}}}},
    "colors": ["#00E396", "#FF4560", "#FEB019"]
}}

For pie charts, use:
{{
    "chart": {{"type": "pie", "height": 350}},
    "title": {{"text": "Pie Chart Title", "align": "center"}},
    "series": [value1, value2, ...],
    "labels": ["Label1", "Label2", ...]
}}

Return ONLY the JSON, no other text."""

    response = call_ollama(ai_prompt, temperature=0.2)
    
    if not response:
        return None
    
    # Extract JSON from response
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if not json_match:
        return None
    
    try:
        config = json.loads(json_match.group())
        
        # Validate required fields
        if "series" not in config:
            return None
        
        # Ensure chart type is set
        if "chart" not in config:
            config["chart"] = {"type": "bar", "height": 350}
        elif "type" not in config["chart"]:
            config["chart"]["type"] = "bar"
        
        # Clean NaN values from config
        config = clean_for_json(config)
        
        return config
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return None

def generate_data_driven_chart(prompt: str) -> dict:
    """Fallback: generate chart based on keywords and actual data"""
    prompt_lower = prompt.lower()
    
    if flattened_df.empty:
        return create_placeholder_chart("No Data Available")
    
    # Determine chart type
    chart_type = 'bar'
    if 'pie' in prompt_lower:
        chart_type = 'pie'
    elif 'line' in prompt_lower:
        chart_type = 'line'
    elif 'heatmap' in prompt_lower:
        chart_type = 'heatmap'
    
    # Duration-based charts
    if 'duration' in prompt_lower or 'slow' in prompt_lower or 'time' in prompt_lower:
        if 'duration' in flattened_df.columns:
            top_n = 10
            match = re.search(r'top\s+(\d+)', prompt_lower)
            if match:
                top_n = int(match.group(1))
            
            # Filter out NaN durations
            valid_durations = flattened_df[flattened_df['duration'].notna()]
            top_slow = valid_durations.nlargest(top_n, 'duration')
            
            if len(top_slow) > 0:
                return clean_for_json({
                    "chart": {"type": "bar", "height": 350},
                    "title": {"text": f"Top {top_n} Slowest Tests", "align": "center"},
                    "series": [{"name": "Duration (seconds)", "data": top_slow['duration'].tolist()}],
                    "xaxis": {
                        "categories": top_slow['test_name'].tolist(),
                        "title": {"text": "Test Name"}
                    },
                    "yaxis": {"title": {"text": "Seconds"}},
                    "colors": ["#FF4560"]
                })
    
    # Status distribution
    elif 'status' in prompt_lower or 'pass' in prompt_lower or 'fail' in prompt_lower:
        if 'status' in flattened_df.columns:
            status_counts = flattened_df['status'].value_counts()
            
            if chart_type == 'pie':
                return clean_for_json({
                    "chart": {"type": "pie", "height": 350},
                    "title": {"text": "Test Status Distribution", "align": "center"},
                    "series": status_counts.values.tolist(),
                    "labels": status_counts.index.tolist(),
                    "colors": ["#00E396", "#FF4560", "#FEB019"]
                })
            else:
                return clean_for_json({
                    "chart": {"type": "bar", "height": 350},
                    "title": {"text": "Test Status Distribution", "align": "center"},
                    "series": [{"name": "Tests", "data": status_counts.values.tolist()}],
                    "xaxis": {"categories": status_counts.index.tolist()},
                    "colors": ["#00E396", "#FF4560"]
                })
    
    # Module-based charts
    elif 'module' in prompt_lower:
        if 'module' in flattened_df.columns:
            module_counts = flattened_df['module'].value_counts().head(10)
            
            if chart_type == 'pie':
                return clean_for_json({
                    "chart": {"type": "pie", "height": 350},
                    "title": {"text": "Tests by Module", "align": "center"},
                    "series": module_counts.values.tolist(),
                    "labels": module_counts.index.tolist()
                })
            else:
                return clean_for_json({
                    "chart": {"type": "bar", "height": 350},
                    "title": {"text": "Tests by Module", "align": "center"},
                    "series": [{"name": "Test Count", "data": module_counts.values.tolist()}],
                    "xaxis": {"categories": module_counts.index.tolist()}
                })
    
    # Default: show status distribution if available
    elif 'status' in flattened_df.columns:
        status_counts = flattened_df['status'].value_counts()
        return clean_for_json({
            "chart": {"type": "pie", "height": 350},
            "title": {"text": "Test Status Distribution", "align": "center"},
            "series": status_counts.values.tolist(),
            "labels": status_counts.index.tolist(),
            "colors": ["#00E396", "#FF4560", "#FEB019"]
        })
    
    # Ultimate fallback
    else:
        return create_placeholder_chart(f"Data Overview ({len(flattened_df)} Records)")

def create_placeholder_chart(title: str) -> dict:
    """Create a placeholder chart when no data is available"""
    return clean_for_json({
        "chart": {"type": "bar", "height": 350},
        "title": {"text": title, "align": "center"},
        "series": [{"name": "No Data", "data": [0]}],
        "xaxis": {"categories": ["No data available"]}
    })

# ========== FRONTEND COMPATIBLE ENDPOINTS ==========
@app.post("/ai/generate-chart")
async def generate_chart_frontend(request: ChartRequest):
    """Generate chart based on user prompt - Frontend compatible endpoint"""
    try:
        logger.info(f"Received chart request: {request.message}")
        
        # Try AI generation first
        ai_config = generate_chart_with_ai(request.message)
        
        if ai_config:
            config = ai_config
        else:
            # Fallback to data-driven generation
            config = generate_data_driven_chart(request.message)
        
        # Save chart
        chart_id = str(uuid.uuid4())
        chart_entry = {
            "id": chart_id,
            "prompt": request.message,
            "chart_type": config.get("chart", {}).get("type", "bar"),
            "config": config,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        charts.insert(0, chart_entry)
        save_charts()
        
        return {
            "success": True,
            "id": chart_id,
            "config": config
        }
        
    except Exception as e:
        logger.exception("Chart generation error")
        # Return a fallback chart instead of error
        fallback = create_placeholder_chart("Error Generating Chart")
        return {
            "success": True,
            "id": str(uuid.uuid4()),
            "config": fallback
        }

@app.get("/ai/generated-charts")
async def get_generated_charts_frontend():
    """Get all generated charts - Frontend compatible endpoint"""
    # Clean charts for JSON
    clean_charts = clean_for_json(charts)
    return {"charts": clean_charts}

@app.delete("/ai/chart/{chart_id}")
async def delete_chart_frontend(chart_id: str):
    """Delete a specific chart - Frontend compatible endpoint"""
    global charts
    charts = [c for c in charts if c["id"] != chart_id]
    save_charts()
    return {"success": True}

# ========== ADDITIONAL DEBUG ENDPOINTS ==========
@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "ok",
        "data_available": not flattened_df.empty,
        "total_records": len(flattened_df) if not flattened_df.empty else 0,
        "tables_found": True
    }

@app.get("/data/summary")
async def data_summary():
    """Get data summary for debugging"""
    if flattened_df.empty:
        return {"has_data": False}
    
    # Clean NaN values
    status_dist = flattened_df['status'].value_counts().to_dict() if 'status' in flattened_df.columns else {}
    
    result = {
        "has_data": True,
        "total_records": len(flattened_df),
        "status_distribution": status_dist,
        "unique_tests": flattened_df['test_name'].nunique() if 'test_name' in flattened_df.columns else 0
    }
    
    if 'duration' in flattened_df.columns:
        valid_durations = flattened_df[flattened_df['duration'].notna()]
        if len(valid_durations) > 0:
            result["duration_stats"] = {
                "mean": float(valid_durations['duration'].mean()),
                "max": float(valid_durations['duration'].max()),
                "min": float(valid_durations['duration'].min())
            }
    
    return clean_for_json(result)

if __name__ == "__main__":
    print("\n" + "="*70)
    print("📊 SENTINEL QA CHART SERVICE")
    print("="*70)
    print(f"\nCurrent directory: {os.getcwd()}")
    print(f"Looking for data at: {Path(DB_PATH).absolute()}")
    print("\nStarting chart service on port 8001...")
    print(f"📍 API: http://localhost:8001")
    print(f"📍 Frontend Endpoints:")
    print(f"   POST /ai/generate-chart - Generate chart")
    print(f"   GET /ai/generated-charts - List charts")
    print(f"   DELETE /ai/chart/{{id}} - Delete chart")
    print(f"📍 Debug Endpoints:")
    print(f"   GET /health - Health check")
    print(f"   GET /data/summary - Data summary")
    print(f"🤖 AI Model: {OLLAMA_MODEL}")
    print(f"📊 Data Path: {DB_PATH}")
    print("="*70)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)