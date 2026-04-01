import os
import json
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
db = None
duck_conn = None
test_cases_df = None
test_results_df = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db, duck_conn, test_cases_df, test_results_df
    logger.info("Starting up...")
    init_database()
    yield
    # Shutdown
    logger.info("Shutting down...")
    if duck_conn:
        duck_conn.close()

app = FastAPI(title="Sentinel QA Chat Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration - FIXED PATH to look for data in parent directory
DB_PATH = "../data"  # Changed from "./data" to "../data" since we're in services folder
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

class ChatRequest(BaseModel):
    message: str

def init_database():
    """Initialize LanceDB and DuckDB connections"""
    global db, duck_conn, test_cases_df, test_results_df
    
    db_path = Path(DB_PATH)
    if not db_path.exists():
        logger.warning(f"Data path {DB_PATH} not found")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Looking for data at: {db_path.absolute()}")
        return
    
    # Connect to LanceDB
    db = lancedb.connect(str(db_path))
    
    # Connect to DuckDB
    duck_conn = duckdb.connect()
    
    # Get tables using the correct method
    try:
        if hasattr(db, 'table_names'):
            tables = db.table_names()
        else:
            tables = db.list_tables()
        
        logger.info(f"Available tables: {tables}")
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        tables = []
    
    # Load tables into DuckDB
    try:
        if "test_cases" in tables:
            test_cases_df = db.open_table("test_cases").to_pandas()
            duck_conn.register("test_cases", test_cases_df)
            logger.info(f"✅ Loaded {len(test_cases_df)} test cases")
        
        if "test_results" in tables:
            test_results_df = db.open_table("test_results").to_pandas()
            logger.info(f"✅ Loaded {len(test_results_df)} test results")
            
            # Flatten test results directly in Python instead of DuckDB
            flatten_test_results_python()
            
    except Exception as e:
        logger.error(f"Error loading data: {e}")

def flatten_test_results_python():
    """Flatten test results using Python (more reliable than DuckDB for complex JSON)"""
    global test_results_df, duck_conn
    
    try:
        if test_results_df is None or test_results_df.empty:
            logger.warning("No test results to flatten")
            return
        
        rows = []
        total_tests = 0
        passed_count = 0
        failed_count = 0
        
        for idx, row in test_results_df.iterrows():
            tests = row.get('tests')
            
            # Parse tests field
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
                        try:
                            duration = float(duration_raw[:-2]) / 1000
                        except:
                            duration = 0
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
                    'result_id': row.get('id'),
                    'build_id': row.get('build_id'),
                    'project_id': row.get('project_id'),
                    'organization_id': row.get('organization_id'),
                    'executed_at': row.get('executed_at'),
                    'test_name': test_name,
                    'status': status,
                    'duration': duration,
                    'error_message': error,
                    'module': module
                })
                
                total_tests += 1
                if status == 'passed':
                    passed_count += 1
                elif status == 'failed':
                    failed_count += 1
        
        # Create DataFrame from flattened data
        if rows:
            flattened_df = pd.DataFrame(rows)
            logger.info(f"✅ Flattened {total_tests} test records from {len(test_results_df)} results")
            logger.info(f"   Passed: {passed_count}, Failed: {failed_count}")
            logger.info(f"   Columns: {list(flattened_df.columns)}")
            
            # Register flattened data in DuckDB
            duck_conn.register("flattened_tests", flattened_df)
            logger.info("✅ Registered flattened_tests in DuckDB")
            
            # Store for quick access
            global flattened_tests_df
            flattened_tests_df = flattened_df
        else:
            logger.warning("No test records could be flattened")
            
    except Exception as e:
        logger.error(f"Error flattening test results: {e}")
        import traceback
        traceback.print_exc()

def call_ollama(prompt: str, temperature: float = 0.3, timeout: int = 300) -> str:
    """Call Ollama API for AI responses with increased timeout"""
    try:
        logger.info(f"Calling Ollama with prompt length: {len(prompt)}")
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "options": {"num_predict": 2000}  # Increased for better responses
            },
            timeout=timeout  # Increased to 300 seconds
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            logger.info(f"Ollama response length: {len(result)}")
            return result
        else:
            logger.error(f"Ollama error: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Ollama timeout after {timeout} seconds")
        return None
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        return None

def get_data_context() -> str:
    """Get current data context for AI"""
    context = []
    
    try:
        # Test cases summary
        if test_cases_df is not None and not test_cases_df.empty:
            context.append(f"Total Test Cases: {len(test_cases_df)}")
            if 'priority' in test_cases_df.columns:
                priorities = test_cases_df['priority'].value_counts()
                context.append(f"Priority Distribution: {dict(priorities)}")
            if 'module_name' in test_cases_df.columns:
                modules = test_cases_df['module_name'].value_counts().head(5)
                context.append(f"Top 5 Modules: {dict(modules)}")
        
        # Test results summary from flattened data
        if duck_conn:
            try:
                # Check if flattened_tests exists
                result = duck_conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = 'flattened_tests'
                """).fetchone()
                
                if result and result[0] > 0:
                    stats = duck_conn.execute("""
                        SELECT 
                            COUNT(*) as total,
                            SUM(CASE WHEN LOWER(status) = 'passed' THEN 1 ELSE 0 END) as passed,
                            SUM(CASE WHEN LOWER(status) = 'failed' THEN 1 ELSE 0 END) as failed,
                            AVG(duration) as avg_duration
                        FROM flattened_tests
                    """).fetchone()
                    
                    if stats and stats[0] > 0:
                        context.append(f"Test Executions: {stats[0]}")
                        context.append(f"Passed: {stats[1]}, Failed: {stats[2]}")
                        if stats[3]:
                            context.append(f"Average Duration: {stats[3]:.2f}s")
                        
                        # Get recent failures
                        recent_failures = duck_conn.execute("""
                            SELECT test_name, error_message 
                            FROM flattened_tests 
                            WHERE LOWER(status) = 'failed' 
                            LIMIT 5
                        """).fetchall()
                        
                        if recent_failures:
                            context.append("\nRecent Failures:")
                            for name, error in recent_failures:
                                error_msg = error[:100] if error else 'No error message'
                                context.append(f"  - {name}: {error_msg}")
            except Exception as e:
                logger.error(f"Error querying flattened_tests: {e}")
    
    except Exception as e:
        logger.error(f"Error getting data context: {e}")
    
    return "\n".join(context)

@app.get("/health")
async def health():
    """Health check endpoint"""
    # Check if flattened_tests exists in DuckDB
    has_flattened = False
    if duck_conn:
        try:
            result = duck_conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'flattened_tests'
            """).fetchone()
            has_flattened = result and result[0] > 0
        except:
            pass
    
    return {
        "status": "ok",
        "data_loaded": test_cases_df is not None and not test_cases_df.empty,
        "test_cases": len(test_cases_df) if test_cases_df is not None else 0,
        "test_results": len(test_results_df) if test_results_df is not None else 0,
        "flattened_data": has_flattened,
        "data_path": str(Path(DB_PATH).absolute())
    }

@app.get("/data/status")
async def data_status():
    """Get data status"""
    if test_cases_df is None or test_cases_df.empty:
        return {
            "has_data": False,
            "message": "No data loaded. Please run ingester.py first.",
            "data_path": str(Path(DB_PATH).absolute())
        }
    
    # Get test results summary
    summary = {}
    if duck_conn:
        try:
            # Check if flattened_tests exists
            result = duck_conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'flattened_tests'
            """).fetchone()
            
            if result and result[0] > 0:
                stats = duck_conn.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN LOWER(status) = 'passed' THEN 1 ELSE 0 END) as passed,
                        SUM(CASE WHEN LOWER(status) = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM flattened_tests
                """).fetchone()
                
                summary = {
                    "total_tests": stats[0] if stats else 0,
                    "passed": stats[1] if stats else 0,
                    "failed": stats[2] if stats else 0
                }
        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            pass
    
    return {
        "has_data": True,
        "test_cases": len(test_cases_df),
        "test_results": len(test_results_df) if test_results_df is not None else 0,
        "summary": summary,
        "data_path": str(Path(DB_PATH).absolute())
    }

@app.post("/ai/chat")
async def chat(request: ChatRequest):
    """AI chat endpoint"""
    user_message = request.message.lower()
    logger.info(f"Received chat message: {user_message[:100]}...")
    
    # Get data context
    data_context = get_data_context()
    
    # Build prompt
    prompt = f"""You are a QA analytics assistant. Use the following data to answer questions.

Current Data Context:
{data_context}

User Question: {user_message}

Provide a concise, helpful answer with specific numbers and insights from the data.
If asking about test names, list them clearly.
If asking about failures, include error messages when available.
"""
    
    # Try AI response first with increased timeout
    ai_response = call_ollama(prompt, timeout=300)
    
    if ai_response:
        logger.info("Returning AI response")
        return {"response": ai_response}
    
    # Fallback responses based on patterns
    if "failed" in user_message or "failure" in user_message:
        if duck_conn:
            try:
                failures = duck_conn.execute("""
                    SELECT test_name, error_message 
                    FROM flattened_tests 
                    WHERE LOWER(status) = 'failed' 
                    LIMIT 10
                """).fetchall()
                
                if failures:
                    response = f"Found {len(failures)} failed tests:\n"
                    for name, error in failures:
                        response += f"\n• {name}"
                        if error:
                            response += f"\n  Error: {error[:150]}"
                    return {"response": response}
            except:
                pass
    
    elif "passed" in user_message:
        if duck_conn:
            try:
                passed = duck_conn.execute("""
                    SELECT COUNT(*) 
                    FROM flattened_tests 
                    WHERE LOWER(status) = 'passed'
                """).fetchone()
                
                if passed:
                    return {"response": f"✅ {passed[0]} tests have passed successfully."}
            except:
                pass
    
    elif "duration" in user_message or "slow" in user_message:
        if duck_conn:
            try:
                slow_tests = duck_conn.execute("""
                    SELECT test_name, duration
                    FROM flattened_tests 
                    WHERE duration > 0
                    ORDER BY duration DESC 
                    LIMIT 5
                """).fetchall()
                
                if slow_tests:
                    response = "Top 5 slowest tests:\n"
                    for name, duration in slow_tests:
                        response += f"\n• {name}: {duration:.2f}s"
                    return {"response": response}
            except:
                pass
    
    # Default fallback
    return {"response": "I can help you analyze your test data. Try asking about:\n• Failed tests\n• Pass rate\n• Slowest tests\n• Test names\n• Module statistics"}

@app.get("/debug/routes")
async def list_routes():
    """List all available routes"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "methods": list(route.methods)
        })
    return {"routes": routes}

@app.get("/debug/data")
async def debug_data():
    """Debug endpoint to check data loading"""
    flattened_exists = False
    flattened_count = 0
    
    if duck_conn:
        try:
            result = duck_conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'flattened_tests'
            """).fetchone()
            flattened_exists = result and result[0] > 0
            
            if flattened_exists:
                flattened_count = duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()[0]
        except:
            pass
    
    return {
        "data_path": str(Path(DB_PATH).absolute()),
        "data_path_exists": Path(DB_PATH).exists(),
        "test_cases_loaded": test_cases_df is not None,
        "test_cases_count": len(test_cases_df) if test_cases_df is not None else 0,
        "test_results_loaded": test_results_df is not None,
        "test_results_count": len(test_results_df) if test_results_df is not None else 0,
        "flattened_data_exists": flattened_exists,
        "flattened_data_count": flattened_count,
        "duckdb_tables": duck_conn.execute("SHOW TABLES").fetchall() if duck_conn else []
    }

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖 SENTINEL QA CHAT SERVICE")
    print("="*70)
    print(f"\nCurrent directory: {os.getcwd()}")
    print(f"Looking for data at: {Path(DB_PATH).absolute()}")
    print("\nStarting chat service on port 8000...")
    print(f"📍 API: http://localhost:8000")
    print(f"📍 Debug endpoints:")
    print(f"   GET /health - Health check")
    print(f"   GET /debug/data - Debug data loading")
    print(f"   GET /debug/routes - List all routes")
    print(f"🤖 AI Model: {OLLAMA_MODEL}")
    print(f"📊 Data Path: {DB_PATH}")
    print("="*70)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)