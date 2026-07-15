import logging
import uuid
import json
import tempfile
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
from typing import Optional
from datetime import datetime, timezone
from . import config, state, data_loader, handlers, memory, llm_client
from . import token_usage_store
from .auth import authenticate_user, create_access_token, get_current_user, initialize_auth_store

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
    source_type: Optional[str] = None
    workspace_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    target_kind: str
    feedback_type: str
    prompt: Optional[str] = None
    response: Optional[str] = None
    chart_id: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    session_id: Optional[str] = None


def _normalize_workspace(workspace_id: Optional[str], current_user: Optional[dict] = None) -> str:
    if workspace_id:
        return str(workspace_id).strip().lower()
    if current_user and current_user.get("workspace_id"):
        return str(current_user["workspace_id"]).strip().lower()
    return str(getattr(config, "DEFAULT_WORKSPACE_ID", "default") or "default").strip().lower()


def _is_admin_role(role: Optional[str]) -> bool:
    return str(role or "").strip().lower() in {"admin", "cto"}


def _infer_source_type(source_path: str, explicit: Optional[str]) -> str:
    if explicit:
        return str(explicit).strip().lower()
    p = str(source_path or "").strip().lower()
    if not p:
        return "file"
    if "allure" in p and ("result" in p or p.endswith("/") or p.endswith("\\")):
        return "allure"
    return "file"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    config.validate_runtime_config()
    initialize_auth_store()
    yield
    logger.info("Shutting down...")
    if state.duck_conn:
        state.duck_conn.close()

app = FastAPI(title="Unified QA Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- PUBLIC ENDPOINTS --------------------
@app.get("/health")
async def health():
    return {"status": "ok", "data_path": str(config.DATA_BASE_PATH)}

@app.post("/auth/login")
async def login(username: str, password: str, workspace_id: Optional[str] = None):
    user = authenticate_user(username, password, workspace_id=workspace_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ws = _normalize_workspace(user.get("workspace_id"), user)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"], "workspace_id": ws}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"],
        "workspace_id": ws,
    }

@app.post("/ingest/config2")
async def ingest_from_config2(request: IngestRequest, current_user: dict = Depends(get_current_user)):
    source_path = str(request.source_path or "").strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")

    build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    source_type = _infer_source_type(source_path, request.source_type)
    workspace_id = _normalize_workspace(request.workspace_id, current_user)

    dynamic_cfg = {
        "ingestion_name": f"{workspace_id}_{source_type}",
        "sources": [
            {
                "type": source_type,
                "path": source_path,
                "params": {"path": source_path},
            }
        ],
        "output": {"base_path": str(config.DATA_BASE_PATH)},
    }

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as tf:
            json.dump(dynamic_cfg, tf, indent=2, ensure_ascii=False)
            temp_cfg_path = tf.name

        # Lazy import to keep API startup fast when ingestion isn't used.
        from universal_ingester.ingester import UniversalIngester

        ingester = UniversalIngester(data_base_path=str(config.DATA_BASE_PATH))
        ingester.run_ingestion_from_config(str(temp_cfg_path), build_id=build_id)
    except Exception as e:
        logger.exception(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        try:
            if "temp_cfg_path" in locals():
                import os
                os.remove(temp_cfg_path)
        except Exception:
            pass

    return {
        "success": True,
        "build_id": build_id,
        "source_path": source_path,
        "source_type": source_type,
        "workspace_id": workspace_id,
    }

# -------------------- PROTECTED ENDPOINTS (all require valid token) --------------------
@app.post("/chat")
async def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_role: Optional[str] = Header(None),
    x_project: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    try:
        response = await handlers.handle_chat(
            request.message, session_id, x_ingestion_id, 
            role=x_role,
            project_id=x_project,
            user_id=current_user["username"],
            workspace_id=_normalize_workspace(x_workspace_id, current_user),
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
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    session_id = x_session_id or request.session_id or str(uuid.uuid4())
    chart_json, error = await handlers.handle_chart(
        request.message, session_id, x_ingestion_id,
        role=x_role,
        project_id=x_project,
        user_id=current_user["username"],
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    if error:
        return {"error": error, "session_id": session_id}
    return {"chart": chart_json, "session_id": session_id}

@app.get("/chat/history/{session_id}")
async def get_chat_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    target_user: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    target = str(target_user or "").strip().lower()
    if target and target != str(current_user["username"]).strip().lower() and not _is_admin_role(current_user.get("role")):
        raise HTTPException(status_code=403, detail="Not allowed to access other users history")

    history = memory.get_chat_history(
        session_id,
        limit=100,
        user_id=target or current_user["username"],
        ingestion_id=normalized_ingestion_id,
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    return {"session_id": session_id, "history": history}

@app.get("/chart/history/{session_id}")
async def get_chart_history_endpoint(
    session_id: str,
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    target_user: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    target = str(target_user or "").strip().lower()
    if target and target != str(current_user["username"]).strip().lower() and not _is_admin_role(current_user.get("role")):
        raise HTTPException(status_code=403, detail="Not allowed to access other users history")

    history = memory.get_chart_history(
        session_id,
        limit=100,
        user_id=target or current_user["username"],
        ingestion_id=normalized_ingestion_id,
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
    )
    return {"session_id": session_id, "history": history}

@app.delete("/chart/{chart_id}")
async def delete_chart(
    chart_id: str,
    x_session_id: Optional[str] = Header(None),
    x_ingestion_id: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)
    if not state.lance_db or "chart_history" not in state.lance_db.table_names():
        return {"error": "Chart history not available"}
    try:
        import pandas as pd

        table = state.lance_db.open_table("chart_history")
        all_df = table.to_pandas()
        if all_df.empty:
            return {"error": "Chart not found"}

        user_key = str(current_user["username"]).strip().lower()
        ws_key = _normalize_workspace(x_workspace_id, current_user)
        if "user_id" in all_df.columns:
            owned = all_df[(all_df["user_id"] == user_key) & (all_df["id"] == chart_id)]
            if "workspace_id" in all_df.columns:
                owned = owned[owned["workspace_id"] == ws_key]
        else:
            owned = all_df[all_df["id"] == chart_id]

        if owned.empty:
            return {"error": "Chart not found or not owned by current user"}

        updated_df = all_df[all_df["id"] != chart_id]
        if len(updated_df) == 0:
            state.lance_db.drop_table("chart_history")
            empty_df = pd.DataFrame(columns=[
                "id", "workspace_id", "user_id", "ingestion_id", "session_id", "type", "prompt", "response", "config",
                "created_at", "metadata"
            ])
            state.lance_db.create_table("chart_history", empty_df)
        else:
            state.lance_db.drop_table("chart_history")
            state.lance_db.create_table("chart_history", updated_df)
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


@app.get("/data/profile")
async def data_profile(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    if not state.duck_conn:
        return {"tables": {}}

    try:
        return data_loader.get_data_profile(sample_rows=5)
    except Exception as e:
        logger.error(f"Error in /data/profile: {e}")
        return {"tables": {}, "error": str(e)}


@app.get("/data/quality")
async def data_quality(
    x_ingestion_id: str = Header(...),
    current_user: dict = Depends(get_current_user)
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    if not state.duck_conn:
        return {
            "score": 0,
            "quality": "unknown",
            "checks": [],
            "guidance": ["No active ingestion loaded"],
        }

    try:
        return data_loader.get_ingestion_quality_report()
    except Exception as e:
        logger.error(f"Error in /data/quality: {e}")
        return {
            "score": 0,
            "quality": "poor",
            "checks": [],
            "guidance": [f"Quality evaluation failed: {e}"],
        }

@app.get("/ingestions")
async def list_ingestions(current_user: dict = Depends(get_current_user)):
    """Return list of available ingestion IDs with metadata (prefer JSON summary)."""
    ingestions = []
    for path in config.DATA_BASE_PATH.iterdir():
        if path.is_dir() and (path / "lancedb").exists():
            summary_json = path / "summary.json"
            summary_text = ""
            if summary_json.exists():
                try:
                    with open(summary_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    summary_text = json.dumps(data.get("metrics", {}), indent=2)
                except Exception as e:
                    logger.warning(f"Could not read {summary_json}: {e}")
            else:
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
    
    sorted_ingestions = sorted(ingestions, key=lambda x: x["created"])
    for i, item in enumerate(sorted_ingestions):
        item["build_label"] = f"Build {i + 1}"
    
    return {"ingestions": sorted(sorted_ingestions, key=lambda x: x["created"], reverse=True)}


@app.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    x_ingestion_id: str = Header(...),
    x_session_id: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    normalized_ingestion_id = str(x_ingestion_id or "").strip()
    if state.current_ingestion_id != normalized_ingestion_id or state.duck_conn is None or state.lance_db is None:
        data_loader.init_data(normalized_ingestion_id)

    if not state.lance_db:
        raise HTTPException(status_code=500, detail="Data store not initialized")

    target_kind = str(request.target_kind or "chat").strip().lower()
    feedback_type = str(request.feedback_type or "improve").strip().lower()
    if target_kind not in {"chat", "chart", "ui"}:
        raise HTTPException(status_code=400, detail="target_kind must be chat, chart, or ui")
    if feedback_type not in {"up", "down", "improve", "positive", "negative"}:
        raise HTTPException(status_code=400, detail="feedback_type must be up, down, improve, positive, or negative")

    ok = memory.store_feedback(
        user_id=current_user["username"],
        ingestion_id=normalized_ingestion_id,
        workspace_id=_normalize_workspace(x_workspace_id, current_user),
        session_id=x_session_id or request.session_id,
        target_kind=target_kind,
        feedback_type=feedback_type,
        prompt=request.prompt,
        response=request.response,
        chart_id=request.chart_id,
        notes=request.notes,
        tags=request.tags,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Could not store feedback")

    prefs = memory.get_feedback_preferences(
        current_user["username"],
        normalized_ingestion_id,
        _normalize_workspace(x_workspace_id, current_user),
        target_kind,
    )
    return {"success": True, "preferences": prefs}

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
    resp = llm.generate(
        "Say hello in one word",
        user_id=current_user.get("username"),
        workspace_id=_normalize_workspace(None, current_user),
    )
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


@app.get("/usage/tokens")
async def token_usage(current_user: dict = Depends(get_current_user)):
    persistent = token_usage_store.get_usage(
        user_id=current_user.get("username"),
        workspace_id=_normalize_workspace(None, current_user),
    )
    return {
        "totals": persistent.get("totals", {}),
        "by_model": persistent.get("by_model", {}),
        "scope": persistent.get("scope", {}),
        "updated_at": persistent.get("updated_at", ""),
        "runtime_totals": state.token_usage,
        "runtime_by_model": state.token_usage_by_model,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)