from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EventType = Literal[
    "run.started",
    "run.finished",
    "test.started",
    "test.finished",
    "test.log",
    "test.attachment",
    "worker.heartbeat",
]

RunStatus = Literal["running", "passed", "failed", "cancelled"]
TestStatus = Literal["running", "passed", "failed", "skipped", "retried"]


class TestInfo(BaseModel):
    id: str
    title: str
    file: Optional[str] = None
    status: Optional[TestStatus] = None
    duration_ms: Optional[int] = None
    retry: int = 0
    error: Optional[str] = None


class ExecutionEvent(BaseModel):
    event_type: EventType
    ts: str
    worker_id: Optional[int] = None
    test: Optional[TestInfo] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    events: list[ExecutionEvent]


class RunCreate(BaseModel):
    framework: str = "playwright"
    name: Optional[str] = None
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    environment: Optional[str] = None
    ci_provider: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    build_url: Optional[str] = None
    worker_count: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunStatusUpdate(BaseModel):
    status: Literal["passed", "failed", "cancelled"]


class LiveFrameIn(BaseModel):
    worker_id: int
    frame: str  # base64 JPEG, no data: URI prefix
