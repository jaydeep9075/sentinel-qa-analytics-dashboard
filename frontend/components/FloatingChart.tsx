"use client";

import { useState } from "react";
import { BarChart3, X, Loader2 } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { generateChart } from "@/lib/api";

/**
 * Predefined chart prompts based on role.
 * Extend as needed.
 */
const ROLE_CHART_PROMPTS: Record<string, string[]> = {
  "qa-engineer": [
    "Bar chart of test status distribution (passed/failed/skipped)",
    "Pie chart of passed vs failed tests",
    "Bar chart of failures by module",
    "Line chart of test execution trend over time",
    "Horizontal bar chart of slowest 10 tests",
  ],
  cto: [
    "Release health summary pie chart (passed vs failed)",
    "Line chart of failure trend over last 5 builds",
    "Bar chart of top 5 modules with highest failure rate",
    "Pie chart showing test stability (flaky vs stable)",
    "Stacked bar chart of test results by priority",
  ],
  default: [
    "Bar chart of test count per module",
    "Pie chart of passed/failed",
    "List of failed tests (as table chart)",
  ],
};

export default function FloatingChart() {
  const { selectedRole } = useRB();
  const { selectedIngestion } = useIngestion();
  const [isOpen, setIsOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const roleKey = (selectedRole || "qa-engineer").toLowerCase();
  const prompts = ROLE_CHART_PROMPTS[roleKey] || ROLE_CHART_PROMPTS.default;

  const handleGenerateChart = async (prompt: string) => {
    if (!selectedIngestion) {
      setStatusMessage("⚠️ Please select an ingestion (test build) first.");
      setTimeout(() => setStatusMessage(null), 3000);
      return;
    }

    setIsGenerating(true);
    setStatusMessage(`Generating chart: "${prompt}"...`);

    try {
      const result = await generateChart(prompt, selectedIngestion);
      if (result.success) {
        setStatusMessage("✅ Chart generated successfully! It will appear at the top.");
        // Refresh gallery? The parent component will need to refresh.
        // We'll dispatch a custom event that the dashboard listens to.
        window.dispatchEvent(new CustomEvent("chart-generated"));
        setTimeout(() => {
          setStatusMessage(null);
          setIsOpen(false); // close modal after success
        }, 1500);
      } else {
        throw new Error(result.error || "Generation failed");
      }
    } catch (error: any) {
      setStatusMessage(`❌ Failed: ${error.message}`);
      setTimeout(() => setStatusMessage(null), 4000);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-24 right-6 z-50 bg-gradient-to-r from-purple-600 to-pink-600 text-white p-4 rounded-full shadow-2xl hover:scale-110 transition-all duration-200 focus:outline-none group"
        aria-label="Generate chart"
      >
        <BarChart3 className="w-6 h-6 group-hover:rotate-6 transition-transform" />
      </button>

      {/* Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-[#0f0f0f] border border-white/10 rounded-2xl w-full max-w-lg flex flex-col shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-purple-400" />
                Generate Visualization
              </h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-4">
              {statusMessage && (
                <div className="mb-4 text-sm text-center text-blue-300 bg-blue-500/10 p-2 rounded-lg">
                  {statusMessage}
                </div>
              )}
              <p className="text-sm text-gray-400 mb-4">
                Choose a chart type. The chart will appear at the top of the dashboard.
              </p>
              <div className="flex flex-col gap-2 max-h-96 overflow-y-auto">
                {prompts.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleGenerateChart(prompt)}
                    disabled={isGenerating || !selectedIngestion}
                    className="text-left text-sm bg-white/5 hover:bg-purple-500/20 border border-white/10 rounded-xl px-4 py-3 text-gray-300 hover:text-purple-300 transition-colors disabled:opacity-50 flex justify-between items-center group"
                  >
                    <span>{prompt}</span>
                    {isGenerating ? (
                      <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                    ) : (
                      <BarChart3 className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                    )}
                  </button>
                ))}
              </div>
              {!selectedIngestion && (
                <p className="text-xs text-red-400 mt-4 text-center">
                  ⚠️ No ingestion selected. Please choose a test build from the top bar.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}