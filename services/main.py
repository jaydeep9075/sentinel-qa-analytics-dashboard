import logging
import uuid
import json
import pandas as pd
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
from typing import Optional
from datetime import datetime, timezone
from . import config, state, data_loader, handlers, memory, llm_client
from .auth import authenticate_user, create_access_token, get_current_user
from universal_ingester.ingester import UniversalIngester

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChartRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class IngestRequest(BaseModel):
    source_path: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
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

# -------------------- PUBLIC ENDPOINTS --------------------
@app.get("/health")
async def health():
    return {"status": "ok", "data_path": str(config.DATA_BASE_PATH)}

@app.post("/auth/login")
async def login(username: str, password: str):
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user["username"], "role": user["role"]})
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}

@app.post("/ingest/config2")
async def ingest_from_config2(request: IngestRequest):
    source_path = str(request.source_path or "").strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")

    config2_path = config.BASE_DIR / "config2.json"
    if not config2_path.exists():
        raise HTTPException(status_code=404, detail="config2.json not found")

    try:
        with open(config2_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        logger.exception(f"Failed to read config2.json: {e}")
        raise HTTPException(status_code=500, detail="Failed to read config2.json")

    if not isinstance(cfg.get("sources"), list) or len(cfg["sources"]) == 0:
        raise HTTPException(status_code=400, detail="Invalid config2.json: sources missing")

    cfg["sources"][0]["path"] = source_path
    with open(config2_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

    build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    try:
        ingester = UniversalIngester(data_base_path=str(config.DATA_BASE_PATH))
        ingester.run_ingestion_from_config(str(config2_path), build_id=build_id)
    except Exception as e:
        logger.exception(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    return {
        "success": True,
        "build_id": build_id,
        "source_path": source_path,
        "triggered_by": current_user.get("username"),
    }

# -------------------- PROTECTED ENDPOINTS (all require valid token) --------------------
@app.post("/chat")
async def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    try:
        response = await handlers.handle_chat(
            request.message, session_id, x_ingestion_id, 
            role=x_role, project_id=x_project
        )
        return {"response": response, "session_id": session_id}
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        return {"response": f"An error occurred: {str(e)}", "session_id": session_id}

@app.post("/chart")
async def chart(
    request: ChartRequest,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    chart_json, error = await handlers.handle_chart(
        request.message, session_id, x_ingestion_id,
        role=x_role, project_id=x_project
    )
    if error:
        return {"error": error, "session_id": session_id}
    return {"chart": chart_json, "session_id": session_id}

@app.get("/chat/history/{session_id}")
async def get_chat_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    history = memory.get_chat_history(session_id, limit=100)
    return {"session_id": session_id, "history": history}

@app.get("/chart/history/{session_id}")
async def get_chart_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    history = memory.get_chart_history(session_id, limit=100)
    return {"session_id": session_id, "history": history}

@app.delete("/chart/{chart_id}")
async def delete_chart(
    chart_id: str,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    if not state.lance_db or "chart_history" not in state.lance_db.table_names():
        return {"error": "Chart history not available"}
    try:
        table = state.lance_db.open_table("chart_history")
        df = table.to_pandas()
        df = df[df["id"] != chart_id]
        if len(df) == 0:
            state.lance_db.drop_table("chart_history")
            empty_df = pd.DataFrame(columns=[
                "id", "session_id", "type", "prompt", "response", "config",
                "created_at", "metadata"
            ])
            state.lance_db.create_table("chart_history", empty_df)
        else:
            state.lance_db.drop_table("chart_history")
            state.lance_db.create_table("chart_history", df)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error deleting chart: {e}")
        return {"error": str(e)}

@app.get("/debug/data")
async def debug_data(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
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
async def data_status(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
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

@app.get("/ingestions")
async def list_ingestions(current_user: dict = Depends(get_current_user)):
    """Return list of available ingestion IDs with metadata (prefer JSON summary)."""
    ingestions = []
    for path in config.DATA_BASE_PATH.iterdir():
        if path.is_dir() and (path / "lancedb").exists():
            # Try to read summary.json first
            summary_json = path / "summary.json"
            summary_text = ""
            if summary_json.exists():
                try:
                    with open(summary_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Convert metrics to a readable string or keep as JSON string
                    summary_text = json.dumps(data.get("metrics", {}), indent=2)
                except Exception as e:
                    logger.warning(f"Could not read {summary_json}: {e}")
            else:
                # Fallback to markdown with UTF-8 (though we prefer JSON)
                summary_md = path / "summary.md"
                if summary_md.exists():
                    try:
                        summary_text = summary_md.read_text(encoding='utf-8')
                    except Exception:
                        summary_text = ""
            
            ingestions.append({
                "id": path.name,
                "summary": summary_text,
                "created": path.stat().st_mtime
            })
    
    # Sort by creation time (oldest first)
    sorted_ingestions = sorted(ingestions, key=lambda x: x["created"])
    for i, item in enumerate(sorted_ingestions):
        item["build_label"] = f"Build {i + 1}"
    
    return {"ingestions": sorted(sorted_ingestions, key=lambda x: x["created"], reverse=True)}

@app.get("/projects")
async def list_projects(current_user: dict = Depends(get_current_user)):
    if state.project_manager is None:
        from .project_manager import ProjectManager
        state.project_manager = ProjectManager()
    return {"projects": state.project_manager.list_projects()}

@app.get("/roles")
async def list_roles(current_user: dict = Depends(get_current_user)):
    if state.role_manager is None:
        from .role_manager import RoleManager
        state.role_manager = RoleManager()
    return {"roles": state.role_manager.list_roles()}

@app.get("/test/llm")
async def test_llm(current_user: dict = Depends(get_current_user)):
    llm = llm_client.LLMClient()
    resp = llm.generate("Say hello in one word")
    return {"llm_response": resp}

@app.get("/test/sql")
async def test_sql(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    if state.duck_conn:
        try:
            result = state.duck_conn.execute("SELECT COUNT(*) FROM flattened_tests").fetchone()
            return {"count": result[0]}
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": "duck_conn not initialized"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)