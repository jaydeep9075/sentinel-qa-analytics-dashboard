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
  return { chart: data.chart };
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
  const res = await fetch(`${API_BASE}/chart/${chartId}`, {
    method: "DELETE",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  return res.json();
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

export async function getTokenUsage() {
  const key = withCacheKey("tokenUsage", "global");
  const cached = cacheGet<Record<string, unknown>>(key);
  if (cached) return cached;

  const res = await timedFetch(
    `${API_BASE}/usage/tokens`,
    {
    cache: "no-store",
    headers: getAuthHeaders(),
    },
    "api:token-usage",
  );
  const data = await res.json();
  cacheSet(key, data, 12000);
  return data;
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
  token_usage?: {
    totals?: {
      total_tokens?: number;
      prompt_tokens?: number;
      completion_tokens?: number;
      calls?: number;
    };
  };
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
      status: { has_data: false, total_rows: 0, status_summary: { passed: 0, failed: 0, skipped: 0 } },
      quality: { score: 0, quality: "unknown", guidance: ["No ingestion selected"], checks: [] },
      token_usage: { totals: { total_tokens: 0, prompt_tokens: 0, completion_tokens: 0, calls: 0 } },
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