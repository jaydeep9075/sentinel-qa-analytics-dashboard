"""
FastAPI routes for ingestion and RAG endpoints.
Complete REST API for the production system.
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel

from .ingestion_service import IngestionService
from .rag_service import RAGService
from .query_executor import QueryExecutor, LanceDBSearcher, ResponseFormatter
from .production_prompts import get_system_prompt, get_analysis_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analytics"])

# Dependency injection
ingestion_service = IngestionService()
rag_service = None  # Will be initialized with LanceDB connection
query_executor = None  # Will be initialized with DuckDB connection
lancedb_searcher = None  # Will be initialized with LanceDB connection


# ==================== Request Models ====================

class IngestionConfig(BaseModel):
    connector_type: str
    path: Optional[str] = None
    connection_string: Optional[str] = None
    url: Optional[str] = None
    config: dict


class QueryRequest(BaseModel):
    prompt: str
    ingestion_id: str
    session_id: Optional[str] = None


class IngestionResponse(BaseModel):
    success: bool
    message: str
    ingestion_id: Optional[str] = None
    error: Optional[str] = None


class QueryResponse(BaseModel):
    response: str
    analysis: dict
    validation: dict
    confidence: float
    execution_time_ms: float


# ==================== Ingestion Routes ====================

@router.get("/ingestion/connectors")
async def get_connectors():
    """Get available connectors and their field configurations."""
    return ingestion_service.get_connector_options()


@router.post("/ingestion/suggest")
async def suggest_fields(path: str):
    """Suggest connector type and fields based on path."""
    suggestions = ingestion_service.suggest_fields(path)
    return suggestions


@router.post("/ingestion/validate")
async def validate_config(config: IngestionConfig):
    """Validate ingestion configuration before processing."""
    is_valid, message = ingestion_service.validator.validate(
        config.connector_type,
        config.config
    )

    return {
        "valid": is_valid,
        "message": message,
        "connector_type": config.connector_type
    }


@router.post("/ingest")
async def start_ingestion(
    config: IngestionConfig,
    background_tasks: BackgroundTasks,
    x_user_id: Optional[str] = Header(None)
):
    """
    Start ingestion process.
    Returns immediately with ingestion ID, processes in background.
    """

    # Validate
    validation = ingestion_service.prepare_ingestion(
        config.connector_type,
        config.config
    )

    if not validation['success']:
        raise HTTPException(
            status_code=400,
            detail=validation['error']
        )

    # Start ingestion in background
    from datetime import datetime
    ingestion_id = f"ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    async def run_ingestion():
        """Background task: run actual ingestion."""
        try:
            logger.info(f"Starting ingestion {ingestion_id}")

            # Import here to avoid circular imports
            from .ingester import UniversalIngester

            ingester = UniversalIngester()

            # Convert config to source config format
            source_config = {
                "type": config.connector_type,
                "params": config.config
            }

            # Run ingestion
            ingester.ingest_source(source_config, ingestion_id)

            logger.info(f"Ingestion {ingestion_id} completed")

            # TODO: Update UI with completion status

        except Exception as e:
            logger.error(f"Ingestion {ingestion_id} failed: {e}")
            # TODO: Notify user of failure

    background_tasks.add_task(run_ingestion)

    return IngestionResponse(
        success=True,
        message=f"Ingestion started (ID: {ingestion_id})",
        ingestion_id=ingestion_id
    )


@router.get("/ingestion/{ingestion_id}/status")
async def get_ingestion_status(ingestion_id: str):
    """Get status of ongoing/completed ingestion."""
    # TODO: Implement status tracking
    return {
        "ingestion_id": ingestion_id,
        "status": "in_progress",  # or "completed", "failed"
        "progress": 0,  # 0-100
        "message": "Processing..."
    }


# ==================== RAG / Query Routes ====================

@router.post("/query")
async def handle_query(
    request: QueryRequest,
    x_user_id: Optional[str] = Header(None)
):
    """
    Handle user query with full RAG pipeline.

    Flow:
    1. Analyze prompt
    2. Search LanceDB for context
    3. Build & execute DuckDB query
    4. Validate response
    5. Return with confidence score
    """

    if not rag_service:
        raise HTTPException(
            status_code=503,
            detail="RAG service not initialized"
        )

    try:
        import time
        start_time = time.time()

        # 1. RAG service handles: analysis + LLM generation + validation
        rag_result = rag_service.generate_response(
            request.prompt,
            data_type="allure_test"  # TODO: Detect from ingestion_id
        )

        execution_time = (time.time() - start_time) * 1000

        return QueryResponse(
            response=rag_result['response'],
            analysis=rag_result['analysis'],
            validation=rag_result['validation'],
            confidence=rag_result['validation'].get('confidence', 0),
            execution_time_ms=execution_time
        )

    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/analyze")
async def analyze_query(
    request: QueryRequest,
    x_user_id: Optional[str] = Header(None)
):
    """
    Analyze query WITHOUT executing.
    Returns intent, entities, filters, confidence.
    """

    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        analysis = rag_service.analyzer.analyze(
            request.prompt,
            data_type="allure_test"
        )

        return {
            "prompt": request.prompt,
            "analysis": analysis,
            "confidence": analysis.get('confidence', 0)
        }

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/execute")
async def execute_query(
    analysis: dict,
    x_user_id: Optional[str] = Header(None)
):
    """
    Execute query from analysis WITHOUT LLM response.
    Returns raw database results.
    """

    if not query_executor:
        raise HTTPException(status_code=503, detail="Query executor not initialized")

    try:
        # Execute query
        exec_result = query_executor.execute(analysis)

        if not exec_result['success']:
            raise HTTPException(
                status_code=400,
                detail=exec_result.get('error', 'Query execution failed')
            )

        # Format as natural language
        response_text = ResponseFormatter.format_response(
            analysis.get('intent', 'summary'),
            exec_result['results'],
            analysis
        )

        return {
            "query": exec_result['query'],
            "results": exec_result['results'],
            "result_count": exec_result['result_count'],
            "execution_time_ms": exec_result['execution_time_ms'],
            "formatted_response": response_text
        }

    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Response History Routes ====================

@router.get("/history/{ingestion_id}")
async def get_query_history(
    ingestion_id: str,
    session_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(None)
):
    """Get query history for an ingestion."""
    # TODO: Implement history tracking
    return {
        "ingestion_id": ingestion_id,
        "session_id": session_id or "all",
        "queries": []
    }


@router.post("/feedback")
async def submit_feedback(
    ingestion_id: str,
    query_id: str,
    rating: int,  # 1-5
    comment: Optional[str] = None,
    x_user_id: Optional[str] = Header(None)
):
    """Submit feedback on query response for quality improvement."""
    # TODO: Implement feedback storage & analytics
    return {
        "success": True,
        "message": "Feedback recorded"
    }


# ==================== Health & Status Routes ====================

@router.get("/health")
async def health_check():
    """Check if system is healthy and ready."""
    return {
        "status": "ok",
        "components": {
            "ingestion_service": "ok",
            "rag_service": "ok" if rag_service else "not_initialized",
            "query_executor": "ok" if query_executor else "not_initialized",
            "lancedb": "ok" if lancedb_searcher else "not_initialized"
        }
    }


@router.get("/stats")
async def get_system_stats(x_user_id: Optional[str] = Header(None)):
    """Get system statistics."""
    # TODO: Implement stats tracking
    return {
        "total_ingestions": 0,
        "total_queries": 0,
        "avg_query_time_ms": 0,
        "avg_response_confidence": 0,
        "uptime_hours": 0
    }


# ==================== Initialization ====================

def initialize_routes(lancedb_conn, duckdb_conn, schema_info):
    """
    Initialize routes with database connections.
    Call this during app startup.
    """

    global rag_service, query_executor, lancedb_searcher

    try:
        logger.info("Initializing API routes...")

        # Initialize RAG service
        rag_service = RAGService(lancedb_conn, schema_info)
        logger.info("✓ RAG service initialized")

        # Initialize query executor
        query_executor = QueryExecutor(duckdb_conn)
        logger.info("✓ Query executor initialized")

        # Initialize LanceDB searcher
        lancedb_searcher = LanceDBSearcher(lancedb_conn)
        logger.info("✓ LanceDB searcher initialized")

        logger.info("✓ All routes initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize routes: {e}")
        return False
