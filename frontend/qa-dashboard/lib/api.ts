import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8000", // Standardized to localhost
});

// ✅ Core Analytics (Powered by LanceDB/DuckDB)
export const getKPIs = () => API.get("/kpis");
export const getStatus = () => API.get("/status-distribution");
export const getModules = () => API.get("/module-stability");
export const getSlowTests = () => API.get("/slow-tests");
export const getTrend = () => API.get("/history-trend");
export const getFailures = () => API.get("/failures");

// ✅ AI & RAG Endpoints
// Note: Backend expects { "message": string } for both chat and chart generation
export const generateChart = (prompt: string) =>
  API.post("/ai/generate-chart", { message: prompt });

export const sendChat = (message: string) =>
  API.post("/ai/chat", { message });

// ✅ Gallery Management
export const getGeneratedCharts = () => API.get("/ai/generated-charts");

export const deleteChart = (chartId: string) =>
  API.delete(`/ai/chart/${chartId}`);

export default API;