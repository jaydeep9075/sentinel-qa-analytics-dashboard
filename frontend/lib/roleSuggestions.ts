// lib/roleSuggestions.ts

export type Suggestions = {
  chat: string[];
  chart: string[];
};

const defaultSuggestions: Suggestions = {
  chat: [
    "How many tests failed?",
    "How many tests passed?",
    "What is the pass rate?",
    "Show test status breakdown",
    "List failed tests with errors",
    "Show slowest 10 tests",
    "List all modules",
    "What are the test counts per module?",
    "Is this build ready for release?",
    "How many tests are there?",
  ],
  chart: [
    "Bar chart of test status distribution",
    "Pie chart of passed vs failed",
    "Bar chart of failures by module",
    "Horizontal bar of slowest 10 tests",
    "Bar chart of pass rate by module",
    "Duration histogram",
    "Bar chart of test counts per module",
    "Heatmap of failures by module and priority",
    "Pie chart of status breakdown (passed/failed/skipped)",
    "Bar chart of failed count by module (top offenders)",
  ],
};

const roleSuggestionsMap: Record<string, Suggestions> = {
  "QA Engineer": {
    chat: [
      "How many tests failed?",
      "List all failed tests with errors",
      "Show slowest 10 tests",
      "What is the pass rate?",
      "Show test status breakdown",
      "How many tests passed?",
      "List failures in the Login module",
      "Show failed tests in the Payment module",
      "Which tests took more than 30 seconds?",
      "What are the test counts per module?",
    ],
    chart: [
      "Bar chart of test status distribution",
      "Pie chart of passed vs failed",
      "Bar chart of failures by module",
      "Horizontal bar of slowest 10 tests",
      "Bar chart of pass rate by module",
      "Heatmap of failures by module and priority",
      "Duration histogram",
      "Bar chart of test counts per module",
      "Pie chart of status breakdown (passed/failed/skipped)",
      "Bar chart of failed count by priority level",
    ],
  },
  CTO: {
    chat: [
      "What is the overall pass rate?",
      "Is this build ready for release?",
      "How many tests were executed?",
      "How many failures exist?",
      "Which modules have the lowest pass rate?",
      "What's the pass rate of the Payment module?",
      "How many critical failures are there?",
      "Show me the release readiness report",
      "List modules with test counts",
      "What percentage of tests passed?",
    ],
    chart: [
      "Pie chart of passed vs failed",
      "Bar chart of pass rate by module",
      "Bar chart of test status distribution",
      "Pass rate by module (worst to best)",
      "Heatmap of failures by module and priority",
      "Bar chart: total tests per module",
      "Horizontal bar of modules by failure count",
      "Pie chart of status breakdown (passed/failed/skipped)",
      "Bar chart of failed count by module",
      "Bar chart comparing passed vs failed counts",
    ],
  },
  Developer: {
    chat: [
      "How many tests failed?",
      "List failed tests with errors",
      "Show slowest 10 tests",
      "What's the pass rate?",
      "Show failures in the Login module",
      "List tests that took more than 5 seconds",
      "What are the failed tests in the Database module?",
      "List all tests in the Checkout module",
      "Which test is the slowest?",
      "How many tests passed in the API module?",
    ],
    chart: [
      "Bar chart of failures by module",
      "Horizontal bar of slowest 10 tests",
      "Duration histogram",
      "Bar chart of pass rate by module",
      "Pie chart of passed vs failed",
      "Heatmap of failures by module and priority",
      "Bar chart of test counts per module",
      "Bar chart of failed tests per module (top offenders)",
      "Bar chart of slowest tests with duration",
      "Pie chart of status breakdown",
    ],
  },
  Manager: {
    chat: [
      "What is the pass rate?",
      "Is this build ready for release?",
      "How many tests were executed?",
      "How many failures?",
      "Show test status breakdown",
      "List modules and their test counts",
      "Which modules have the most failures?",
      "What's the pass rate of the most critical module?",
      "How many tests passed?",
      "Show overall health summary",
    ],
    chart: [
      "Pie chart of passed vs failed",
      "Bar chart of pass rate by module",
      "Bar chart of test status distribution",
      "Bar chart of failures by module (top 5)",
      "Bar chart comparing passed vs failed counts",
      "Horizontal bar of modules with highest failure count",
      "Pie chart of status breakdown",
      "Bar chart of test counts per module",
      "Heatmap of module vs failure count",
      "Bar chart showing failed count by module",
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