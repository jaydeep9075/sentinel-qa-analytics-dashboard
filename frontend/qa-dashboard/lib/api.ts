// lib/api.ts

export const MAIN_API_BASE = "http://localhost:8000";
export const CHART_API_BASE = "http://localhost:8001";

export const fetcher = (url: string) => fetch(url).then((res) => res.json());

// Chat endpoints
export const sendChatMessage = async (message: string) => {
  const res = await fetch(`${MAIN_API_BASE}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.response;
};

// Chart endpoints
export const generateChart = async (prompt: string) => {
  const res = await fetch(`${CHART_API_BASE}/ai/generate-chart`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: prompt }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export const getGeneratedCharts = async () => {
  const res = await fetch(`${CHART_API_BASE}/ai/generated-charts`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export const deleteChart = async (chartId: string) => {
  const res = await fetch(`${CHART_API_BASE}/ai/chart/${chartId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

// Data endpoints
export const getDataStatus = async () => {
  const res = await fetch(`${MAIN_API_BASE}/data/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export const checkHealth = async () => {
  const res = await fetch(`${MAIN_API_BASE}/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};
