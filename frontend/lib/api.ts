import { getSessionId } from "./session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const workspaceId = typeof window !== "undefined" ? localStorage.getItem("workspace_id") : null;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (workspaceId) headers["x-workspace-id"] = workspaceId;
  return headers;
}

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  return res.json();
}

export async function getDataStatus(ingestionId: string) {
  const res = await fetch(`${API_BASE}/data/status`, {
    cache: "no-store",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  return res.json();
}

export async function listIngestions() {
  const res = await fetch(`${API_BASE}/ingestions`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch ingestions");
  return res.json();
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

  const res = await fetch(`${API_BASE}/chart`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message: prompt, session_id: sessionId }),
  });
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
  const res = await fetch(`${API_BASE}/chart/history/${sessionId}`, {
    cache: "no-store",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  return res.json();
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
  const res = await fetch(`${API_BASE}/usage/tokens`, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });
  return res.json();
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