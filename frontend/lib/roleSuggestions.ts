// lib/roleSuggestions.ts

export type Suggestions = {
  chat: string[];
  chart: string[];
};

// ------------------------------------------------------------
// Default suggestions – safe and always work
// ------------------------------------------------------------
const defaultSuggestions: Suggestions = {
  chat: [
    "How many tests failed?",
    "How many tests passed?",
    "What is the overall pass rate?",
    "Show test status breakdown",
    "List failed tests with errors",
    "Show slowest 10 tests",
    "Is this build ready for release?",
    "Compare mobile vs desktop pass rate",
    "Tests that failed on mobile but passed on desktop",
    "List all modules",
  ],
  chart: [
    "Bar chart of test status distribution",
    "Pie chart of passed vs failed",
    "Bar chart of failures by module",
    "Horizontal bar of slowest 10 tests",
    "Grouped bar: pass rate by platform (mobile vs desktop)",
    "Bar chart of failures by project and platform",
    "Heatmap of failures by module and project",
    "Bar chart of test counts per module",
    "Pie chart of status breakdown (passed/failed/skipped)",
    "Bar chart of failed count by module (top offenders)",
  ],
};

// ------------------------------------------------------------
// Role‑specific suggestions – all mapped to real schema values
// ------------------------------------------------------------
const roleSuggestionsMap: Record<string, Suggestions> = {
  "QA Engineer": {
    chat: [
      "How many tests failed?",
      "List all failed tests with errors",
      "Show slowest 10 tests by platform",
      "What is the overall pass rate?",
      "Show test status breakdown",
      "How many tests passed on mobile?",
      "List failures in the Eligibility Tests module",
      "Show failed tests in the Checkout Tests module on desktop",
      "Which tests took more than 30 seconds?",
      "What are the test counts per module across platforms?",
      "Tests that failed on mobile but passed on desktop",
      "Show all failures in project FSA",
      "List failed tests in the Cart Tests module",
      "Show failures in the Expense Dashboard Tests module",
    ],
    chart: [
      // Bar Charts (Technical Aspects)
      "Bar chart of failed test count by module (Top Offenders)",
      "Grouped bar chart: pass rate by platform (Mobile vs Desktop)",
      "Bar chart of test execution status breakdown per project",
      "Bar chart of total tests per module stacked by status",
      // Line Charts (Trends & Stability)
      "Line chart showing pass rate trend across all modules",
      "Line chart of test duration distribution across executed tests",
      // Heatmaps (Density & Risk)
      "Heatmap of failures by module and platform type",
      "Heatmap matrix showing failure density by project and module",
      "Heatmap of test durations by browser and module",
      // Simplified Charts (High-level Quality)
      "Pie chart distribution of passed vs failed tests",
      "Donut chart of full execution status breakdown",
      "Horizontal bar chart of the top 15 slowest tests",
      "Pie chart of failure distribution by project",
    ],
  },

  CTO: {
    chat: [
      "What is the overall pass rate?",
      "Is this build ready for release?",
      "How many tests were executed across all projects?",
      "How many failures exist?",
      "Which modules have the lowest pass rate on mobile?",
      "What's the pass rate of the Payment module?",
      "How many critical failures are there?",
      "Show me the release readiness report",
      "Compare pass rate between FSA, HSA, and WDH",
      "What percentage of tests passed on desktop vs mobile?",
      "List modules with test counts and pass rate",
    ],
    chart: [
      // Bar Charts (Strategic Metrics)
      "Bar chart comparing release readiness pass rate by project",
      "Bar chart of project-level health and test density",
      "Grouped bar chart: overall pass rate by project and platform",
      // Line Charts (Quality Trends)
      "Line chart trend of overall stability across all projects",
      "Line chart of pass rate performance across modules",
      // Heatmaps (Risk Management)
      "Heatmap of strategic risk areas by project and failure count",
      "Heatmap showing quality coverage by module and project",
      // Simplified Charts (Executive Summary)
      "Donut chart of overall project health and release status",
      "Pie chart showing total test execution status distribution",
      "Horizontal bar of modules ranked by failure impact",
    ],
  }
};

// ------------------------------------------------------------
// Helper to get suggestions for a role (case‑insensitive)
// ------------------------------------------------------------
export function getRoleSuggestions(roleId: string): Suggestions {
  const clean = roleId?.toLowerCase().replace(/[^a-z]/g, "") || "";
  for (const [key, val] of Object.entries(roleSuggestionsMap)) {
    if (
      key.toLowerCase() === clean ||
      key.toLowerCase() === roleId?.toLowerCase()
    ) {
      return val;
    }
  }
  return defaultSuggestions;
}