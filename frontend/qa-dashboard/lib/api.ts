const API_BASE = "http://localhost:8000";

function getSessionId(): string {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

export const sendChatMessage = async (message: string): Promise<string> => {
  const sessionId = getSessionId();
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.response;
};

export const generateChart = async (prompt: string) => {
  const sessionId = getSessionId();
  console.log("📊 Generating chart with session ID:", sessionId);
  const res = await fetch(`${API_BASE}/chart`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: prompt, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  console.log("Chart response:", data);
  if (data.error) {
    return { success: false, error: data.error };
  }
  if (!data.chart) {
    return { success: false, error: "No chart data returned" };
  }
  try {
    const chartJson = JSON.parse(data.chart);
    return { success: true, chart: chartJson };
  } catch (e) {
    console.error("Failed to parse chart JSON", data.chart);
    return { success: false, error: "Invalid chart JSON" };
  }
};

export const getSessionCharts = async () => {
  const sessionId = getSessionId();
  const res = await fetch(`${API_BASE}/chart/history/${sessionId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  console.log("📊 Chart history response:", data); // <-- add this
  return data.history.map((item: any) => ({
    id: item.id,
    prompt: item.prompt || "Chart",
    config: item.config ? JSON.parse(item.config) : null,
    created_at: item.created_at,
  }));
};

export const deleteChart = async (chartId: string) => {
  const sessionId = getSessionId();
  const res = await fetch(`${API_BASE}/chart/${chartId}`, {
    method: "DELETE",
    headers: { "X-Session-Id": sessionId },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export const getDataStatus = async () => {
  const res = await fetch(`${API_BASE}/data/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data;
};

export const checkHealth = async () => {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};