// lib/roleSuggestions.ts

export type Suggestions = {
  chat: string[];
  chart: string[];
};

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

const roleSuggestionsMap: Record<string, Suggestions> = {
  "QA Engineer": {
    chat: [
      "How many tests failed?",
      "List all failed tests with errors",
      "Show slowest 10 tests by platform",
      "What is the pass rate?",
      "Show test status breakdown",
      "How many tests passed on mobile?",
      "List failures in the Eligibility module",
      "Show failed tests in the Checkout module on desktop",
      "Which tests took more than 30 seconds?",
      "What are the test counts per module across platforms?",
      "Tests that failed on mobile but passed on desktop",
      "Show all failures in project FSA",
    ],
    chart: [
      "Bar chart of test status distribution",
      "Pie chart of passed vs failed",
      "Bar chart of failures by module, grouped by platform",
      "Horizontal bar of slowest 10 tests with platform coloring",
      "Bar chart of pass rate by module and platform",
      "Heatmap of failures by module and project",
      "Duration histogram split by platform",
      "Bar chart of test counts per module (stacked by platform)",
      "Pie chart of status breakdown for mobile only",
      "Bar chart of failed count by module (top offenders) with platform filter",
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
      "Pie chart of passed vs failed",
      "Bar chart of pass rate by module (worst to best)",
      "Bar chart of test status distribution",
      "Grouped bar: pass rate by project and platform",
      "Heatmap of failures by module and priority",
      "Bar chart: total tests per module with pass rate overlay",
      "Horizontal bar of modules by failure count",
      "Pie chart of status breakdown for desktop only",
      "Bar chart of failed count by project",
      "Line chart of pass rate over time (if date column available)",
    ],
  },
  Developer: {
    chat: [
      "How many tests failed?",
      "List failed tests with errors in the API module",
      "Show slowest 10 tests with browser info",
      "What's the pass rate on Chrome desktop?",
      "Show failures in the Login module on mobile",
      "List tests that took more than 5 seconds",
      "What are the failed tests in the Database module?",
      "List all tests in the Checkout module",
      "Which test is the slowest on iPhone?",
      "How many tests passed in the Eligibility module?",
      "Show me tests that failed only on mobile",
    ],
    chart: [
      "Bar chart of failures by module, colored by project",
      "Horizontal bar of slowest 10 tests with duration and platform",
      "Duration histogram by platform",
      "Bar chart of pass rate by module (filter by project HSA)",
      "Pie chart of passed vs failed for mobile tests",
      "Heatmap of failures by module and browser type",
      "Bar chart of test counts per module for desktop only",
      "Bar chart of failed tests per module (top offenders) with error details",
      "Bar chart of slowest tests grouped by module",
      "Scatter plot: duration vs status",
    ],
  },
  Manager: {
    chat: [
      "What is the overall pass rate?",
      "Is this build ready for release?",
      "How many tests were executed?",
      "How many failures across projects?",
      "Show test status breakdown by platform",
      "List modules and their test counts per project",
      "Which modules have the most failures on desktop?",
      "What's the pass rate of the most critical module on mobile?",
      "How many tests passed in project WDH?",
      "Show overall health summary with platform comparison",
    ],
    chart: [
      "Pie chart of passed vs failed",
      "Bar chart of pass rate by module, grouped by project",
      "Bar chart of test status distribution with platform split",
      "Bar chart of failures by module (top 5) for each platform",
      "Grouped bar comparing passed vs failed counts by project",
      "Horizontal bar of modules with highest failure count on mobile",
      "Pie chart of status breakdown for desktop vs mobile side by side",
      "Bar chart of test counts per module (stacked by project)",
      "Heatmap of module vs failure count across projects",
      "Bar chart showing failed count by module and platform",
    ],
  },
};

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