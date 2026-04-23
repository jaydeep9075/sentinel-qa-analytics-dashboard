import { getSessionId } from "./session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}

export async function getDataStatus(ingestionId: string) {
  const res = await fetch(`${API_BASE}/data/status`, {
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
  if (data.error) {
    return { success: false, error: data.error };
  }
  return { success: true, chart: data.chart };
}

export async function getChatHistory(sessionId: string, ingestionId: string) {
  const res = await fetch(`${API_BASE}/chat/history/${sessionId}`, {
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  return res.json();
}

export async function getChartHistory(sessionId: string, ingestionId: string) {
  const res = await fetch(`${API_BASE}/chart/history/${sessionId}`, {
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  const data = await res.json();
  console.log("📊 getChartHistory raw response:", data);
  return data;
}

export async function deleteChart(chartId: string, ingestionId: string) {
  const res = await fetch(`${API_BASE}/chart/${chartId}`, {
    method: "DELETE",
    headers: { "x-ingestion-id": ingestionId, ...getAuthHeaders() },
  });
  return res.json();
}