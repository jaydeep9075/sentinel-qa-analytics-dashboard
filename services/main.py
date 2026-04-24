import logging
import uuid
import pandas as pd
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
from typing import Optional
from . import config, state, data_loader, handlers, memory, llm_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChartRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    data_loader.init_data()
    logger.info(f"LanceDB path: {config.DATA_PATH}")
    yield
    logger.info("Shutting down...")
    if state.duck_conn:
        state.duck_conn.close()

app = FastAPI(title="Unified QA Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health
@app.get("/health")
async def health():
    return {"status": "ok", "data_available": state.lance_db is not None, "data_path": str(config.DATA_PATH)}

# Chat
@app.post("/chat")
async def chat(request: ChatRequest, x_session_id: Optional[str] = Header(None)):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    try:
        response = await handlers.handle_chat(request.message, session_id)
        return {"response": response, "session_id": session_id}
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        return {"response": f"An error occurred: {str(e)}", "session_id": session_id}

# Chart
@app.post("/chart")
async def chart(request: ChartRequest, x_session_id: Optional[str] = Header(None)):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    chart_json, error = await handlers.handle_chart(request.message, session_id)
    if error:
        return {"error": error, "session_id": session_id}
    # Note: store_chart is now called inside handle_chart, so we don't need to call it again here.
    return {"chart": chart_json, "session_id": session_id}

# History
@app.get("/chat/history/{session_id}")
async def get_chat_history_endpoint(session_id: str):
    history = memory.get_chat_history(session_id, limit=100)
    return {"session_id": session_id, "history": history}

@app.get("/chart/history/{session_id}")
async def get_chart_history_endpoint(session_id: str):
    history = memory.get_chart_history(session_id, limit=100)
    return {"session_id": session_id, "history": history}

# Delete chart
@app.delete("/chart/{chart_id}")
async def delete_chart(chart_id: str, x_session_id: Optional[str] = Header(None)):
    """Delete a specific chart by ID (only if it belongs to the session)."""
    if not state.lance_db or "chart_history" not in state.lance_db.table_names():
        return {"error": "Chart history not available"}
    try:
        table = state.lance_db.open_table("chart_history")
        df = table.to_pandas()
        # Filter out the chart with the given id
        df = df[df["id"] != chart_id]
        if len(df) == 0:
            # Table would be empty; drop and recreate empty
            state.lance_db.drop_table("chart_history")
            empty_df = pd.DataFrame(columns=[
                "id", "session_id", "type", "prompt", "response", "config",
                "created_at", "metadata"
            ])
            state.lance_db.create_table("chart_history", empty_df)
        else:
            # Overwrite the table with filtered data
            state.lance_db.drop_table("chart_history")
            state.lance_db.create_table("chart_history", df)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error deleting chart: {e}")
        return {"error": str(e)}

# Debug
@app.get("/debug/data")
async def debug_data():
    data = {}
    if state.duck_conn:
        tables = state.duck_conn.execute("SHOW TABLES").fetchall()
        data["tables"] = [t[0] for t in tables]
        if "flattened_tests" in data["tables"]:
            sample = state.duck_conn.execute("SELECT * FROM flattened_tests LIMIT 5").df()
            data["flattened_tests_sample"] = sample.to_dict(orient="records")
            data["flattened_tests_count"] = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()[0]
    return data

@app.get("/data/status")
async def data_status():
    if not state.duck_conn:
        return {"has_data": False, "total_rows": 0}
    try:
        count = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()[0]
        passed = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests WHERE status='passed'").fetchone()[0]
        failed = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests WHERE status='failed'").fetchone()[0]
        return {
            "has_data": count > 0,
            "total_rows": count,
            "status_summary": {
                "passed": passed,
                "failed": failed,
            }
        }
    except Exception as e:
        logger.error(f"Error in /data/status: {e}")
        return {"has_data": False, "total_rows": 0}

# Test endpoints (optional)
@app.get("/test/llm")
async def test_llm():
    llm = llm_client.LLMClient()
    resp = llm.generate("Say hello in one word")
    return {"llm_response": resp}

@app.get("/test/sql")
async def test_sql():
    if state.duck_conn:
        try:
            result = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()
            return {"count": result[0]}
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": "duck_conn not initialized"}

if __name__ == "__main__":
    if not config.DATA_PATH.exists():
        print(f"ERROR: Data path {config.DATA_PATH} not found.")
    else:
        print("\n" + "="*70)
        print("🚀 Unified QA Service")
        print("="*70)
        print(f"LLM Provider: {config.LLM_PROVIDER}")
        print(f"Model: {config.LLM_MODEL}")
        print(f"Data Path: {config.DATA_PATH}")
        print("="*70)
        uvicorn.run(app, host="0.0.0.0", port=8000)