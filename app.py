from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import lancedb
import duckdb
import pandas as pd
import os
import uuid
import datetime
import json
import requests
import numpy as np
import re
import io
from context_manager import SentinelContextManager

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== INITIALIZATION ==========
DB_PATH = "./sentinel_data"
os.makedirs(DB_PATH, exist_ok=True)
db = lancedb.connect(DB_PATH)
ctx_manager = SentinelContextManager()

# Ollama configuration
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:7b"
_flat_df = None

# ========== HELPER FUNCTIONS ==========
def get_table_list():
    try:
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
        print(f"Error getting table list: {e}")
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
                print("local_test_results not found")
                return pd.DataFrame()
        df_raw = con.execute(f"SELECT * FROM '{lance_file}'").df()
        con.close()
    except Exception as e:
        print(f"DuckDB error: {e}")
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
    print(f"Flattened {len(_flat_df)} individual test records")
    return _flat_df

def get_data_safely():
    df = flatten_test_data()
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    return df

def call_ollama(prompt: str, temperature: float = 0.7, timeout: int = 180) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "options": {"num_predict": 5000}
            },
            timeout=timeout
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
        return f"Error: {resp.status_code}"
    except requests.exceptions.Timeout:
        return "Error: The AI took too long to respond. Try a simpler question."
    except Exception as e:
        return f"Error: {str(e)}"

def get_failed_test_names(limit: int = None, unique: bool = False):
    df = get_data_safely()
    if df.empty:
        return []
    failed = df[df['status'] == 'failed']
    if unique:
        failed = failed.drop_duplicates(subset='test_name')
    if limit:
        failed = failed.head(limit)
    return failed['test_name'].tolist()

def get_passed_test_names(limit: int = None, unique: bool = False):
    df = get_data_safely()
    if df.empty:
        return []
    passed = df[df['status'] == 'passed']
    if unique:
        passed = passed.drop_duplicates(subset='test_name')
    if limit:
        passed = passed.head(limit)
    return passed['test_name'].tolist()

def get_all_test_names(limit: int = None, unique: bool = False):
    df = get_data_safely()
    if df.empty:
        return []
    all_tests = df
    if unique:
        all_tests = all_tests.drop_duplicates(subset='test_name')
    if limit:
        all_tests = all_tests.head(limit)
    return all_tests['test_name'].tolist()

def format_list_response(items, title, limit=None, unique=False):
    if not items:
        return f"No {title.lower()} found."
    if limit:
        return f"First {limit} {title.lower()}:\n" + "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    else:
        unique_note = " (unique)" if unique else ""
        # Return the full list (no truncation)
        return f"All {len(items)} {title.lower()}{unique_note}:\n" + "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

# ========== PYDANTIC MODELS ==========
class ChatReq(BaseModel):
    message: str

# ========== API ENDPOINTS ==========
@app.get("/")
def root():
    return {"message": "Sentinel QA API is running", "status": "ok"}

@app.get("/health")
def health_check():
    df = get_data_safely()
    tables = get_table_list()
    return {
        "status": "ok",
        "ai_provider": "ollama",
        "data_available": not df.empty,
        "data_rows": len(df) if not df.empty else 0,
        "tables_found": len(tables),
        "tables": tables
    }

@app.get("/data/status")
def data_status():
    df = get_data_safely()
    tables = get_table_list()
    if df.empty:
        return {
            "has_data": False,
            "message": "No data loaded",
            "available_tables": tables,
            "total_tables": len(tables)
        }
    status_summary = {}
    if 'status' in df.columns:
        status_counts = df['status'].value_counts()
        status_summary = {k: int(v) for k, v in status_counts.items()}
    return {
        "has_data": True,
        "total_rows": int(len(df)),
        "columns": list(df.columns),
        "status_summary": status_summary,
        "available_tables": tables,
        "sample": df.head(5).to_dict(orient='records')
    }

@app.get("/data/export")
def export_data(format: str = "json"):
    """Export all test data as JSON or CSV."""
    df = get_data_safely()
    if df.empty:
        raise HTTPException(status_code=404, detail="No data available")
    if format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=test_data.csv"})
    else:
        return JSONResponse(content=df.to_dict(orient="records"))

@app.post("/ai/chat")
async def api_chat(req: ChatReq):
    user_msg = req.message.lower()
    ctx_manager.add_message("user", user_msg)

    # --- DIRECT HANDLERS USING REGEX (NO AI) ---

    # 1. List all test names (both passed and failed)
    all_tests_patterns = [
        r'\b(list|show|get|give)\s+(all|every|the\s+full)\s+(test\s+names?|tests?)\b',
        r'all\s+test\s+names?',
        r'all\s+tests',
        r'list\s+all\s+tests',
        r'full\s+test\s+list',
        r'every\s+test'
    ]
    if any(re.search(p, user_msg) for p in all_tests_patterns):
        unique = "unique" in user_msg or "distinct" in user_msg
        limit = None
        # Extract number if user says "first X" or "top X"
        match = re.search(r'(first|top)\s+(\d+)', user_msg)
        if match:
            limit = int(match.group(2))
        names = get_all_test_names(limit, unique)
        response = format_list_response(names, "test names", limit, unique)
        ctx_manager.add_message("assistant", response)
        return {"response": response}

    # 2. List failed tests
    failed_patterns = [
        r'\b(list|show|get|give)\s+(all|every|the\s+full)?\s*(failed\s+test(?:s| cases?)?)\b',
        r'failed\s+tests?',
        r'all\s+failed',
        r'list\s+failed'
    ]
    if any(re.search(p, user_msg) for p in failed_patterns):
        unique = "unique" in user_msg or "distinct" in user_msg
        limit = None
        match = re.search(r'(first|top)\s+(\d+)', user_msg)
        if match:
            limit = int(match.group(2))
        names = get_failed_test_names(limit, unique)
        response = format_list_response(names, "failed tests", limit, unique)
        ctx_manager.add_message("assistant", response)
        return {"response": response}

    # 3. List passed tests
    passed_patterns = [
        r'\b(list|show|get|give)\s+(all|every|the\s+full)?\s*(passed\s+test(?:s| cases?)?)\b',
        r'passed\s+tests?',
        r'all\s+passed',
        r'list\s+passed'
    ]
    if any(re.search(p, user_msg) for p in passed_patterns):
        unique = "unique" in user_msg or "distinct" in user_msg
        limit = None
        match = re.search(r'(first|top)\s+(\d+)', user_msg)
        if match:
            limit = int(match.group(2))
        names = get_passed_test_names(limit, unique)
        response = format_list_response(names, "passed tests", limit, unique)
        ctx_manager.add_message("assistant", response)
        return {"response": response}

    # 4. Columns
    columns_patterns = [
        r'\b(columns|what\s+columns|list\s+columns|show\s+columns)\b'
    ]
    if any(re.search(p, user_msg) for p in columns_patterns):
        df = get_data_safely()
        if df.empty:
            return {"response": "No data loaded."}
        cols = list(df.columns)
        response = f"Columns in the data:\n" + "\n".join(f"- {col}" for col in cols)
        ctx_manager.add_message("assistant", response)
        return {"response": response}

    # 5. Full data summary
    summary_patterns = [
        r'\b(all\s+data|full\s+data|complete\s+data|data\s+summary|what\s+data)\b'
    ]
    if any(re.search(p, user_msg) for p in summary_patterns):
        df = get_data_safely()
        if df.empty:
            return {"response": "No data loaded."}
        summary = f"Total test records: {len(df)}\n"
        if 'status' in df.columns:
            status_counts = df['status'].value_counts()
            summary += "Status distribution:\n" + "\n".join(f"  {k}: {v}" for k, v in status_counts.items()) + "\n"
        if 'duration' in df.columns:
            summary += f"Duration stats: avg={df['duration'].mean():.2f}s, max={df['duration'].max():.2f}s, min={df['duration'].min():.2f}s\n"
        if 'module' in df.columns:
            top_modules = df['module'].value_counts().head(5)
            summary += "Top modules:\n" + "\n".join(f"  {k}: {v}" for k, v in top_modules.items()) + "\n"
        response = summary + "\nTo get specific lists, ask for 'all test names' or 'list failed tests'."
        ctx_manager.add_message("assistant", response)
        return {"response": response}

    # --- NORMAL AI-BASED RESPONSE (for analytical questions) ---
    df = get_data_safely()
    if df.empty:
        return {"response": "⚠️ No data found. Please check data ingestion."}

    # Build summary for AI
    summary = f"Total test records: {len(df)}\n"
    if 'status' in df.columns:
        status_counts = df['status'].value_counts()
        summary += "Status distribution:\n" + "\n".join(f"  {k}: {v}" for k, v in status_counts.items()) + "\n"
    if 'duration' in df.columns:
        summary += f"Duration stats: avg={df['duration'].mean():.2f}s, max={df['duration'].max():.2f}s, min={df['duration'].min():.2f}s\n"
    if 'module' in df.columns:
        top_modules = df['module'].value_counts().head(5)
        summary += "Top modules:\n" + "\n".join(f"  {k}: {v}" for k, v in top_modules.items()) + "\n"

    if 'status' in df.columns:
        failed = df[df['status'] == 'failed']
        if not failed.empty:
            summary += f"\nSample of {len(failed)} failed tests:\n"
            for _, row in failed.head(3).iterrows():
                summary += f"  - {row['test_name']} (duration {row['duration']:.2f}s)\n"

    prompt = f"""You are a QA analyst assistant. Use the following test data to answer the user's question.

Data Summary:
{summary}

User question: {user_msg}

Answer concisely with specific numbers and insights."""
    ai_response = call_ollama(prompt, temperature=0.3)
    ctx_manager.add_message("assistant", ai_response)
    return {"response": ai_response}

# ========== CHART AND OTHER ENDPOINTS (unchanged) ==========
@app.post("/ai/generate-chart")
async def api_gen_chart(req: ChatReq):
    df = get_data_safely()
    if df.empty:
        raise HTTPException(status_code=404, detail="No data available")

    chart_config = None
    if 'status' in df.columns:
        status_counts = df['status'].value_counts()
        chart_config = {
            "chart": {"type": "pie", "height": 350},
            "title": {"text": "Test Status Distribution", "align": "center"},
            "series": status_counts.values.tolist(),
            "labels": status_counts.index.tolist(),
            "colors": ["#00E396", "#FF4560", "#FEB019"]
        }
    elif 'duration' in df.columns:
        top_slow = df.nlargest(10, 'duration')
        chart_config = {
            "chart": {"type": "bar", "height": 350},
            "title": {"text": "Top 10 Slowest Tests", "align": "center"},
            "series": [{"name": "Duration (s)", "data": top_slow['duration'].tolist()}],
            "xaxis": {
                "categories": top_slow['test_name'].tolist(),
                "title": {"text": "Test Name"}
            },
            "yaxis": {"title": {"text": "Seconds"}}
        }
    else:
        chart_config = {
            "chart": {"type": "bar", "height": 350},
            "title": {"text": f"Data Overview ({len(df)} records)", "align": "center"},
            "series": [{"name": "Count", "data": list(range(min(20, len(df))))}],
            "xaxis": {"categories": [f"Record {i}" for i in range(min(20, len(df)))]}
        }

    new_id = str(uuid.uuid4())
    tables = get_table_list()
    if "saved_charts" in tables:
        try:
            db.open_table("saved_charts").add([{
                "id": new_id,
                "prompt": req.message,
                "chart_type": chart_config.get("chart", {}).get("type", "bar"),
                "config": json.dumps(chart_config),
                "created_at": str(datetime.datetime.now())
            }])
        except Exception as e:
            print(f"Error saving chart: {e}")
    return {"success": True, "config": chart_config, "id": new_id}

@app.get("/ai/generated-charts")
def get_charts():
    try:
        tables = get_table_list()
        if "saved_charts" in tables:
            table = db.open_table("saved_charts")
            df = table.to_pandas()
            if not df.empty:
                charts = df[df.id != "initial"].to_dict(orient="records")
                for c in charts:
                    if isinstance(c.get('config'), str):
                        try:
                            c['config'] = json.loads(c['config'])
                        except:
                            pass
                return {"charts": sorted(charts, key=lambda x: x['created_at'], reverse=True)}
    except Exception as e:
        print(f"Error getting charts: {e}")
    return {"charts": []}

@app.delete("/ai/chart/{chart_id}")
def delete_chart(chart_id: str):
    try:
        tables = get_table_list()
        if "saved_charts" in tables:
            db.open_table("saved_charts").delete(f"id = '{chart_id}'")
    except Exception as e:
        print(f"Error deleting chart: {e}")
    return {"success": True}

@app.get("/kpis")
def get_kpis():
    df = get_data_safely()
    if df.empty:
        return {"total": 0, "passed": 0, "failed": 0, "avg_duration": 0}
    status_counts = df['status'].value_counts() if 'status' in df.columns else {}
    return {
        "total": len(df),
        "passed": int(status_counts.get('passed', 0)),
        "failed": int(status_counts.get('failed', 0)),
        "avg_duration": float(df['duration'].mean()) if 'duration' in df.columns else 0
    }

@app.get("/debug/routes")
def list_routes():
    routes = []
    for route in app.routes:
        routes.append({"path": route.path, "methods": list(route.methods)})
    return {"routes": routes}

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("🚀 SENTINEL QA ANALYTICS DASHBOARD (Final)")
    print("="*70)
    print("\n📂 Scanning LanceDB...")
    tables = get_table_list()
    if tables:
        print(f"\n✅ Found {len(tables)} tables:")
        for t in tables:
            try:
                rows = db.open_table(t).count_rows()
                print(f"   📊 {t}: {rows:,} rows")
            except:
                print(f"   ❌ {t}: error")
    else:
        print("\n⚠️ No tables found")
    print(f"\n🤖 AI: Ollama ({OLLAMA_MODEL})")
    print("📍 Server: http://localhost:8000")
    print("📊 Debug routes: http://localhost:8000/debug/routes")
    print("📥 Export data: http://localhost:8000/data/export")
    print("="*70)
    uvicorn.run(app, host="0.0.0.0", port=8000)