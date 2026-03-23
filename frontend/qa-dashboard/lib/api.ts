import axios from "axios";

const API = axios.create({
  baseURL: "http://127.0.0.1:8000/",
});

// Original endpoints
export const getKPIs = () => API.get("/kpis");
export const getStatus = () => API.get("/status-distribution");
export const getModules = () => API.get("/module-stability");
export const getSlowTests = () => API.get("/slow-tests");
export const getTrend = () => API.get("/history-trend");
export const getFailures = () => API.get("/failures");

// New AI endpoints
export const generateChart = (prompt: string) =>
  API.post("/ai/generate-chart", { prompt });

export const sendChat = (message: string) =>
  API.post("/ai/chat", { message });

export const getGeneratedCharts = () => API.get("/ai/generated-charts");

export const deleteChart = (chartId: string) =>
  API.delete(`/ai/chart/${chartId}`);
