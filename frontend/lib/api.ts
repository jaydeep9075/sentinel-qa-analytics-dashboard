import { getSessionId } from "./session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PERF_DEBUG_FLAG = "qa_perf_debug";

type CacheEntry<T> = {
  data: T;
  expiresAt: number;
};

const memoryCache = new Map<string, CacheEntry<unknown>>();

function nowMs(): number {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

function isPerfLoggingEnabled(): boolean {
  if (typeof window === "undefined") return false;
  if (process.env.NODE_ENV !== "production") return true;
  return localStorage.getItem(PERF_DEBUG_FLAG) === "1";
}

function logPerf(event: string, durationMs: number, details?: Record<string, unknown>): void {
  if (!isPerfLoggingEnabled()) return;
  console.debug(`[perf] ${event} ${durationMs.toFixed(1)}ms`, details || {});
}

async function timedFetch(input: string, init: RequestInit, event: string): Promise<Response> {
  const started = nowMs();
  const response = await fetch(input, init);
  const durationMs = nowMs() - started;
  const serverMs = response.headers.get("x-server-timing-ms");
  logPerf(event, durationMs, {
    ok: response.ok,
    status: response.status,
    server_ms: serverMs ? Number(serverMs) : null,
  });
  return response;
}

function cacheGet<T>(key: string): T | null {
  const now = Date.now();
  const mem = memoryCache.get(key) as CacheEntry<T> | undefined;
  if (mem && mem.expiresAt > now) {
    logPerf("cache:memory-hit", 0, { key });
    return mem.data;
  }
  if (mem) memoryCache.delete(key);

  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry<T>;
    if (!parsed?.expiresAt || parsed.expiresAt <= now) {
      sessionStorage.removeItem(key);
      return null;
    }
    memoryCache.set(key, parsed as CacheEntry<unknown>);
    logPerf("cache:session-hit", 0, { key });
    return parsed.data;
  } catch {
    return null;
  }
}

function cacheSet<T>(key: string, data: T, ttlMs: number): void {
  const entry: CacheEntry<T> = {
    data,
    expiresAt: Date.now() + Math.max(0, ttlMs),
  };
  memoryCache.set(key, entry as CacheEntry<unknown>);
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // Ignore cache storage errors.
  }
}

function withCacheKey(base: string, scope: string): string {
  return `qa_cache:${base}:${scope}`;
}

/**
 * Forget everything cached about one build, plus the build list.
 *
 * Deleting a build server-side doesn't reach the browser's caches. Without
 * this, the dashboard keeps rendering the deleted build's overview, charts
 * and quality panel from sessionStorage until each entry's TTL expires — the
 * data is gone but the UI still shows it, which looks like the delete
 * silently failed.
 *
 * Matches by key suffix rather than listing every cache name, so a cache
 * added later is covered without anyone having to remember to update this.
 */
export function purgeIngestionCache(ingestionId: string): void {
  const scope = String(ingestionId || "").trim();

  for (const key of Array.from(memoryCache.keys())) {
    if (!key.startsWith("qa_cache:")) continue;
    if ((scope && key.endsWith(`:${scope}`)) || key.endsWith(":global")) {
      memoryCache.delete(key);
    }
  }

  if (typeof window === "undefined") return;
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (!key.startsWith("qa_cache:")) continue;
      if ((scope && key.endsWith(`:${scope}`)) || key.endsWith(":global")) {
        sessionStorage.removeItem(key);
      }
    }
  } catch {
    // Storage may be unavailable (private mode, quota); the memory cache is
    // already cleared, which is the part that affects the current page.
  }
}

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const workspaceId = typeof window !== "undefined" ? localStorage.getItem("workspace_id") : null;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (workspaceId) headers["x-workspace-id"] = workspaceId;
  return headers;
}

export async function checkHealth() {
  const key = withCacheKey("health", "global");
  const cached = cacheGet<Record<string, unknown>>(key);
  if (cached) return cached;

  const res = await timedFetch(`${API_BASE}/health`, { cache: "no-store" }, "api:health");
  const data = await res.json();
  cacheSet(key, data, 5000);
  return data;
}

export async function getDataStatus(ingestionId: string) {
  const key = withCacheKey("status", ingestionId || "none");
  const cached = cacheGet<Record<string, unknown>>(key);
  if (cached) return cached;

  const res = await timedFetch(
    `${API_BASE}/data/status`,
    {
    cache: "no-store",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
    },
    "api:data-status",
  );
  const data = await res.json();
  cacheSet(key, data, 12000);
  return data;
}

export async function getDataQuality(ingestionId: string) {
  const key = withCacheKey("quality", ingestionId || "none");
  const cached = cacheGet<Record<string, unknown>>(key);
  if (cached) return cached;

  const res = await timedFetch(
    `${API_BASE}/data/quality`,
    {
    cache: "no-store",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
    },
    "api:data-quality",
  );
  const data = await res.json();
  cacheSet(key, data, 20000);
  return data;
}

export function readCachedIngestions(): { ingestions?: unknown[] } | null {
  return cacheGet<{ ingestions?: unknown[] }>(withCacheKey("ingestions", "global"));
}

export async function listIngestions(forceRefresh = false) {
  const key = withCacheKey("ingestions", "global");
  if (!forceRefresh) {
    const cached = cacheGet<Record<string, unknown>>(key);
    if (cached) return cached;
  }

  const res = await timedFetch(
    `${API_BASE}/ingestions`,
    { headers: getAuthHeaders() },
    "api:ingestions",
  );
  if (!res.ok) throw new Error("Failed to fetch ingestions");
  const data = await res.json();
  cacheSet(key, data, 20000);
  return data;
}

export async function sendChatMessage(
  message: string,
  ingestionId: string,
  role?: string | null,
  project?: string | null,
) {
  const sessionId = getSessionId();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-ingestion-id": ingestionId,
    "x-session-id": sessionId,
    ...getAuthHeaders(),
  };
  if (role) headers["x-role"] = role;
  if (project) headers["x-project"] = project;

  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  const data = await res.json();
  return data.response;
}

export async function generateChart(
  prompt: string,
  ingestionId: string,
  role?: string | null,
  project?: string | null,
) {
  const sessionId = getSessionId();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-ingestion-id": ingestionId,
    "x-session-id": sessionId,
    ...getAuthHeaders(),
  };
  if (role) headers["x-role"] = role;
  if (project) headers["x-project"] = project;

  const res = await timedFetch(
    `${API_BASE}/chart`,
    {
    method: "POST",
    headers,
    body: JSON.stringify({ message: prompt, session_id: sessionId }),
    },
    "api:chart",
  );
  const data = await res.json();
  if (!res.ok || data.error) {
    throw new Error(data?.error || data?.detail || "Failed to generate chart");
  }
  // The freshly-stored chart is now the newest row in this build's history,
  // so any cached copy of that history is stale by definition. Dropping it
  // here is what stops a revalidation moments later from replaying a list
  // that predates the chart the user is currently looking at.
  invalidateChartHistoryCache(ingestionId);
  return { chart: data.chart, chartId: data.chart_id as string | undefined };
}

/** Drop the cached chart history for one build (all sessions). */
export function invalidateChartHistoryCache(ingestionId: string): void {
  const scope = String(ingestionId || "").trim();
  const prefix = `qa_cache:chartHistory:${scope}`;

  for (const key of Array.from(memoryCache.keys())) {
    if (key.startsWith(prefix)) memoryCache.delete(key);
  }
  if (typeof window === "undefined") return;
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i -= 1) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith(prefix)) sessionStorage.removeItem(key);
    }
  } catch {
    // Ignore storage access errors.
  }
}

export async function getChatHistory(sessionId: string, ingestionId: string) {
  const res = await fetch(`${API_BASE}/chat/history/${sessionId}`, {
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  return res.json();
}

export async function getChartHistory(sessionId: string, ingestionId: string) {
  const key = withCacheKey("chartHistory", `${ingestionId}:${sessionId}`);
  const cached = cacheGet<Record<string, unknown>>(key);
  if (cached) return cached;

  const res = await timedFetch(
    `${API_BASE}/chart/history/${sessionId}`,
    {
    cache: "no-store",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
    },
    "api:chart-history",
  );
  const data = await res.json();
  cacheSet(key, data, 10000);
  return data;
}

export async function deleteChart(chartId: string, ingestionId: string) {
  const res = await fetch(`${API_BASE}/chart/${encodeURIComponent(chartId)}`, {
    method: "DELETE",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  const data = await res.json().catch(() => ({}));

  // The delete endpoint answers failures with 200 + {"error": "..."} rather
  // than a status code, so `res.ok` alone would report every failure as a
  // success and the caller would quietly leave the chart on screen.
  if (!res.ok || data?.error) {
    throw new Error(data?.error || data?.detail || "Failed to delete chart");
  }

  // Without this the 10s history cache replays the pre-delete list on the
  // very next revalidation, so the chart reappears a moment after it is
  // removed — which is what "delete does nothing" actually looked like.
  invalidateChartHistoryCache(ingestionId);
  return data;
}

export async function ingestFromConfigPath(sourcePath: string) {
  const res = await fetch(`${API_BASE}/ingest/config2`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ source_path: sourcePath }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || data?.error || "Failed to ingest build");
  }
  return data;
}

export interface ConnectorField {
  name: string;
  type: "text" | "select" | "checkbox" | "textarea" | "number";
  label: string;
  placeholder?: string;
  required: boolean;
  help?: string;
  default?: unknown;
  options?: { value: string; label: string }[];
  validation?: string;
}

export interface ConnectorOption {
  id: string;
  name: string;
  description: string;
  fields: ConnectorField[];
  formats: string[];
  auto_detect: boolean;
}

async function parseJsonOrThrow<T>(res: Response, fallback: string): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data?.detail as string) || (data?.error as string) || fallback);
  }
  return data as T;
}

export async function getConnectorOptions(): Promise<{ connectors: ConnectorOption[] }> {
  const res = await fetch(`${API_BASE}/ingest/connectors`, { headers: getAuthHeaders() });
  return parseJsonOrThrow<{ connectors: ConnectorOption[] }>(res, "Failed to load connector options");
}

export interface UploadResult {
  staged_path: string;
  filename: string;
  bytes: number;
}

/**
 * Uploads a file for ingestion, reporting real byte-level progress.
 *
 * Uses XMLHttpRequest rather than fetch because `fetch` still has no
 * cross-browser upload-progress event - the wizard's progress bar would
 * otherwise have to be a decorative fake, which is worse than no bar at
 * all for the multi-hundred-MB archives this endpoint accepts.
 *
 * onProgress receives 0..1, or null when the browser reports the transfer
 * as non-computable (no Content-Length on the request body), so the caller
 * can fall back to an indeterminate bar instead of showing a stuck 0%.
 */
export function uploadIngestFile(
  file: File,
  connectorType: string,
  onProgress?: (fraction: number | null) => void,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("connector_type", connectorType);
  form.append("file", file);

  return new Promise<UploadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/ingest/upload-file`);
    Object.entries(getAuthHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v));

    xhr.upload.onprogress = (e) => {
      if (!onProgress) return;
      onProgress(e.lengthComputable && e.total > 0 ? e.loaded / e.total : null);
    };
    // onerror fires only for transport-level failures - the request never
    // reached a responding server. In practice that is almost always the
    // backend being down, so name it and name the address, rather than
    // leaving the user to guess between "server", "network" and "my file".
    xhr.onerror = () =>
      reject(
        new Error(
          `Upload failed — no response from the backend at ${API_BASE}. ` +
            `Check that it is running (its /health endpoint should answer).`,
        ),
      );
    xhr.ontimeout = () => reject(new Error("Upload timed out — the backend stopped responding"));
    xhr.onabort = () => reject(new Error("Upload cancelled"));
    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(xhr.responseText) as Record<string, unknown>;
      } catch {
        // Non-JSON body (a proxy's HTML 502 page, say) — fall through to the
        // status-based message below rather than throwing a parse error.
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1);
        resolve(data as unknown as UploadResult);
        return;
      }
      reject(new Error(
        (data.detail as string) || (data.error as string) || `Upload failed (HTTP ${xhr.status})`,
      ));
    };
    xhr.send(form);
  });
}

export interface TestConnectionResult {
  success: boolean;
  message?: string;
  tables?: string[];
  table_count?: number;
  status_code?: number;
  content_type?: string;
  is_json?: boolean;
  preview?: string;
}

export async function testConnection(
  connectorType: string,
  config: Record<string, unknown>,
): Promise<TestConnectionResult> {
  const res = await fetch(`${API_BASE}/ingest/test-connection`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ connector_type: connectorType, config }),
  });
  return parseJsonOrThrow<TestConnectionResult>(res, "Connection test failed");
}

export interface BuildIngestPayload {
  connector_type: string;
  config: Record<string, unknown>;
  display_name?: string;
}

export async function startBuildIngestion(
  payload: BuildIngestPayload,
): Promise<{ success: boolean; build_id: string; connector_type: string; status: string }> {
  const res = await fetch(`${API_BASE}/ingest/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ success: boolean; build_id: string; connector_type: string; status: string }>(
    res, "Failed to start ingestion",
  );
}

export interface IngestStatus {
  build_id: string;
  status: "running" | "completed" | "failed";
  error: string | null;
  started_at: string;
  finished_at: string | null;
  /** Pipeline stage reported by the ingester. Optional: an older backend,
   *  or a job whose status file predates phase tracking, omits these. */
  phase?: "queued" | "connecting" | "fetching" | "processing" | "indexing" | "summarizing" | "completed";
  phase_detail?: string;
  rows?: number;
}

export async function getIngestStatus(buildId: string): Promise<IngestStatus> {
  const res = await fetch(`${API_BASE}/ingest/status/${encodeURIComponent(buildId)}`, {
    headers: getAuthHeaders(),
  });
  return parseJsonOrThrow<IngestStatus>(res, "Failed to fetch ingestion status");
}

/** Business read of one build, computed server-side from the same
 *  in-memory aggregates the status block uses (see _get_insights_payload). */
export interface DashboardInsights {
  has_data?: boolean;
  /** Go / no-go call for this build. */
  readiness?: {
    verdict?: "ready" | "at_risk" | "blocked" | "unknown";
    label?: string;
    detail?: string;
  };
  pass_rate?: number;
  /** How much of the product the failures actually touch. */
  blast_radius?: {
    impacted?: number;
    total?: number;
    top_area?: string;
    top_area_failures?: number;
  };
  /** The single defect signature that explains the most failures. */
  top_failure?: { signature?: string; count?: number; share?: number };
  /** What the suite costs, split into elapsed time vs machine time. */
  runtime?: {
    /** Critical path: how long the run actually took end to end. */
    wall_clock_seconds?: number;
    /** True when the run was parallel, so wall_clock_seconds is a floor. */
    wall_clock_estimated?: boolean;
    /** Every test duration added together - machine time, not elapsed time. */
    total_seconds?: number;
    avg_seconds?: number;
    failed_seconds?: number;
    slowest_area?: string;
    workers?: number;
    hosts?: number;
  };
  coverage?: { skipped?: number; skipped_rate?: number };
}

export interface DashboardOverview {
  connected?: boolean;
  ingestion_id?: string;
  status?: {
    has_data?: boolean;
    total_rows?: number;
    status_summary?: { passed?: number; failed?: number; skipped?: number };
  };
  quality?: {
    score?: number;
    quality?: string;
    guidance?: string[];
    checks?: { name?: string; passed?: boolean; detail?: string }[];
  };
  insights?: DashboardInsights;
  server_time?: string;
}

export function readCachedDashboardOverview(ingestionId: string): DashboardOverview | null {
  if (!ingestionId) return null;
  return cacheGet<DashboardOverview>(withCacheKey("overview", ingestionId));
}

export async function getDashboardOverview(
  ingestionId: string,
  options?: { forceRefresh?: boolean; includeQuality?: boolean },
): Promise<DashboardOverview> {
  if (!ingestionId) {
    return {
      connected: true,
      status: { has_data: false, total_rows: 0, status_summary: { passed: 0, failed: 0 } },
      quality: { score: 0, quality: "unknown", guidance: ["No ingestion selected"], checks: [] },
    };
  }

  const key = withCacheKey("overview", ingestionId);
  if (!options?.forceRefresh) {
    const cached = cacheGet<DashboardOverview>(key);
    if (cached) return cached;
  }

  const includeQuality = Boolean(options?.includeQuality);
  const res = await timedFetch(
    `${API_BASE}/dashboard/overview?include_quality=${includeQuality ? "true" : "false"}`,
    {
      cache: "no-store",
      headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
    },
    "api:dashboard-overview",
  );
  if (!res.ok) {
    throw new Error("Failed to fetch dashboard overview");
  }
  const data = (await res.json()) as DashboardOverview;
  cacheSet(key, data, 15000);
  return data;
}

export async function prefetchDashboardQuality(ingestionId: string): Promise<void> {
  if (!ingestionId) return;
  try {
    await getDataQuality(ingestionId);
  } catch {
    // Ignore transient quality prefetch failures.
  }
}

export async function submitFeedback(
  ingestionId: string,
  payload: {
    target_kind: "chat" | "chart" | "ui";
    feedback_type: "up" | "down" | "improve" | "positive" | "negative";
    prompt?: string;
    response?: string;
    chart_id?: string;
    notes?: string;
    tags?: string[];
    session_id?: string;
  },
) {
  const sessionId = payload.session_id || getSessionId();
  const res = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-ingestion-id": ingestionId,
      "x-session-id": sessionId,
      ...getAuthHeaders(),
    },
    body: JSON.stringify(payload),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || data?.error || "Failed to submit feedback");
  }
  return data;
}