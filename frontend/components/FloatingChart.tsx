"use client";

import { useState } from "react";
import { BarChart3, X, Loader2, Sparkles } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { generateChart } from "@/lib/api";

// Predefined chart prompts that the backend can handle
const CHART_PROMPTS = [
  "Bar chart of test status distribution (passed/failed/skipped)",
  "Pie chart of passed vs failed tests",
  "Bar chart of failures by module",
  "Horizontal bar chart of slowest 10 tests",
  "Line chart of test execution trend over time (if multiple builds are available)",
];

export default function FloatingChart() {
  const { selectedRole } = useRB();
  const { selectedIngestion } = useIngestion();
  const [isOpen, setIsOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

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
        window.dispatchEvent(new CustomEvent("chart-generated"));
        setTimeout(() => {
          setStatusMessage(null);
          setIsOpen(false);
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
      {/* ── FAB ── */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-24 right-6 z-50 bg-gradient-to-r from-purple-500 to-pink-600 text-white p-4 rounded-full shadow-[0_0_30px_rgba(168,85,247,0.25)] hover:shadow-[0_0_50px_rgba(168,85,247,0.4)] hover:scale-110 transition-all duration-200 focus:outline-none group"
        aria-label="Generate chart"
      >
        <BarChart3 className="w-6 h-6 group-hover:rotate-6 transition-transform" />
      </button>

      {/* ── Modal ── */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="bg-black border border-white/[0.08] rounded-2xl w-full max-w-lg flex flex-col shadow-[0_0_60px_rgba(0,0,0,0.8),0_0_30px_rgba(168,85,247,0.05)] overflow-hidden">
            {/* header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06] bg-white/[0.02]">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center shadow-[0_0_12px_rgba(168,85,247,0.2)]">
                  <BarChart3 className="w-4 h-4 text-white" />
                </div>
                <span>Generate <span className="text-white/50 font-normal">Visualization</span></span>
              </h2>
              <button onClick={() => setIsOpen(false)} className="text-white/30 hover:text-white hover:bg-white/[0.06] p-1.5 rounded-lg transition-all">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* body */}
            <div className="p-5">
              {statusMessage && (
                <div className="mb-4 text-sm text-center text-cyan-400 bg-cyan-500/[0.06] border border-cyan-500/15 p-3 rounded-xl">
                  {statusMessage}
                </div>
              )}
              <p className="text-xs text-white/30 mb-4">
                Choose a chart type. The chart will appear at the top of the dashboard.
              </p>
              <div className="flex flex-col gap-2 max-h-96 overflow-y-auto custom-scrollbar">
                {CHART_PROMPTS.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleGenerateChart(prompt)}
                    disabled={isGenerating || !selectedIngestion}
                    className="group text-left text-sm bg-white/[0.03] hover:bg-purple-500/[0.08] border border-white/[0.06] hover:border-purple-500/20 rounded-xl px-4 py-3.5 text-white/50 hover:text-purple-300 transition-all disabled:opacity-30 flex justify-between items-center"
                  >
                    <span>{prompt}</span>
                    {isGenerating ? (
                      <Loader2 className="w-4 h-4 animate-spin text-purple-400 flex-shrink-0 ml-2" />
                    ) : (
                      <Sparkles className="w-4 h-4 opacity-0 group-hover:opacity-100 text-purple-400 transition-opacity flex-shrink-0 ml-2" />
                    )}
                  </button>
                ))}
              </div>
              {!selectedIngestion && (
                <p className="text-[10px] text-red-400/70 mt-4 text-center uppercase tracking-wider">
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