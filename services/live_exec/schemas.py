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
    id: str = Field(max_length=2000)
    title: str = Field(max_length=2000)
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
    # A reporter batches at most a few dozen events per second. A request
    # carrying tens of thousands is either a client bug or someone probing,
    # and either way it is a single request that can pin the event loop and
    # the SQLite writer for seconds. Rejecting it costs a well-behaved
    # client nothing.
    events: list[ExecutionEvent] = Field(max_length=2000)


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
    # How many tests the runner resolved before starting. Without it the
    # dashboard can only count tests it has already seen, so "12 done" has
    # no denominator and there is no progress bar or ETA to show - which is
    # the first question anyone watching a run actually asks. Optional so a
    # framework that cannot know its total up front still reports fine.
    total_tests: Optional[int] = None
    # Joins several processes into one run. A suite split with
    # `--shard=1/4`, or a CI matrix with one job per browser, is four
    # separate runner processes reporting the same logical run - without a
    # shared id the dashboard shows four quarter-runs and no total. Runners
    # send a stable string (the CI build id is the obvious one) and the
    # store attaches them to the same row. Deliberately opt-in: silently
    # merging two unrelated jobs that happen to share a build id would be a
    # worse failure than not merging at all.
    external_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunStatusUpdate(BaseModel):
    status: Literal["passed", "failed", "cancelled"]


class LiveFrameIn(BaseModel):
    worker_id: int
    frame: str  # base64 JPEG, no data: URI prefix
