// lib/roleSuggestions.ts

export type Suggestions = {
  chat: string[];
  chart: string[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const workspaceId = typeof window !== "undefined" ? localStorage.getItem("workspace_id") : null;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (workspaceId) headers["x-workspace-id"] = workspaceId;
  return headers;
}

// ------------------------------------------------------------
// Suggestions
//
// Deliberately short. These are a nudge for someone who has not thought of a
// question yet, not a menu of everything the assistant can do - a wall of
// fourteen chips reads as a form to fill in and buries the answer area
// underneath it. MAX_SUGGESTIONS is the cap the UI relies on.
// ------------------------------------------------------------
export const MAX_SUGGESTIONS = 4;

const defaultSuggestions: Suggestions = {
  chat: [
    "What is the overall pass rate?",
    "List failed tests with errors",
    "Which modules are failing most?",
    "Is this build ready for release?",
  ],
  chart: [
    "Pie chart of passed vs failed",
    "Bar chart of failures by module",
    "Horizontal bar of slowest 10 tests",
    "Grouped bar: pass rate by platform",
  ],
};

// ------------------------------------------------------------
// Role-specific suggestions - all mapped to real schema values
// ------------------------------------------------------------
const roleSuggestionsMap: Record<string, Suggestions> = {
  sdet: {
    chat: [
      "List all failed tests with errors",
      "Show slowest 10 tests by platform",
      "Tests that failed on mobile but passed on desktop",
      "Which tests took more than 30 seconds?",
    ],
    chart: [
      "Bar chart of failed test count by module (top offenders)",
      "Heatmap of failures by module and platform type",
      "Horizontal bar chart of the top 15 slowest tests",
      "Grouped bar chart: pass rate by platform (mobile vs desktop)",
    ],
  },

  "qa-manager": {
    chat: [
      "What is the overall pass rate?",
      "Which modules have the lowest pass rate?",
      "How many failures exist and where?",
      "Is this build ready for release?",
    ],
    chart: [
      "Bar chart of failures by module",
      "Grouped bar chart: pass rate by project and platform",
      "Donut chart of full execution status breakdown",
      "Line chart of pass rate trend across modules",
    ],
  },

  cto: {
    chat: [
      "Is this build ready for release?",
      "What is the overall pass rate?",
      "Which areas carry the most release risk?",
      "Compare pass rate across projects",
    ],
    chart: [
      "Bar chart comparing release readiness pass rate by project",
      "Donut chart of overall project health and release status",
      "Heatmap of strategic risk areas by project and failure count",
      "Horizontal bar of modules ranked by failure impact",
    ],
  },
};

// ------------------------------------------------------------
// Helper to get suggestions for a role (case‑insensitive)
// ------------------------------------------------------------
export function getRoleSuggestions(roleId: string): Suggestions {
  const clean = String(roleId || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  if (clean.includes("cto") || clean.includes("admin")) return roleSuggestionsMap.cto;
  if (clean.includes("sdet") || clean.includes("engineer") || clean.includes("developer")) {
    return roleSuggestionsMap.sdet;
  }
  if (clean.includes("qa")) return roleSuggestionsMap["qa-manager"];
  return defaultSuggestions;
}

export async function getAdaptiveRoleSuggestions(
  ingestionId: string,
  roleId?: string | null,
  projectId?: string | null,
): Promise<Suggestions> {
  const fallback = getRoleSuggestions(roleId || "");
  if (!ingestionId) return fallback;

  try {
    const headers: Record<string, string> = {
      "x-ingestion-id": ingestionId,
      ...getAuthHeaders(),
    };
    if (roleId) headers["x-role"] = roleId;
    if (projectId) headers["x-project"] = projectId;

    const res = await fetch(`${API_BASE}/suggestions`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) return fallback;
    const data = await res.json();
    const chat = Array.isArray(data?.chat) ? data.chat.map((x: unknown) => String(x).trim()).filter(Boolean) : [];
    const chart = Array.isArray(data?.chart) ? data.chart.map((x: unknown) => String(x).trim()).filter(Boolean) : [];
    if (chat.length === 0 || chart.length === 0) return fallback;
    return { chat: chat.slice(0, MAX_SUGGESTIONS), chart: chart.slice(0, MAX_SUGGESTIONS) };
  } catch {
    return fallback;
  }
}