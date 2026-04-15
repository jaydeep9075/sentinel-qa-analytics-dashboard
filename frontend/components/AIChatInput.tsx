"use client";

import { useState } from "react";
import { generateChart } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import { useRB } from "@/lib/RBContext";

interface AIChatInputProps {
  onChartGenerated: () => void;
}

export default function AIChatInput({ onChartGenerated }: AIChatInputProps) {
  const { selectedIngestion } = useIngestion();
  const { selectedRole } = useRB();
  const roleKey = (selectedRole || "qa").toLowerCase();
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const shortcuts =
    roleKey === "cto"
      ? [
          "Release health summary pie chart (passed vs failed)",
          "Line chart of failure trend over time",
          "Bar chart of failures by module",
        ]
      : [
          "Bar chart of test status distribution",
          "Pie chart of passed vs failed",
          "Slowest 5 tests",
        ];

  const handleSubmit = async (e?: React.FormEvent, manualPrompt?: string) => {
    e?.preventDefault();
    const activePrompt = manualPrompt || prompt;
    if (!activePrompt.trim() || !selectedIngestion) return;

    setLoading(true);
    setStatus("Generating chart...");

    try {
      const result = await generateChart(activePrompt, selectedIngestion);
      if (result.success) {
        setPrompt("");
        setStatus("Chart generated successfully!");
        onChartGenerated();
        setTimeout(() => setStatus(null), 3000);
      } else {
        throw new Error(result.error || "Generation failed");
      }
    } catch (err: any) {
      console.error("Chart generation error:", err);
      setStatus(`Failed: ${err.message}`);
      setTimeout(() => setStatus(null), 5000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <textarea
        rows={4}
        className="w-full bg-black/50 border border-white/10 rounded-xl p-4 text-sm text-gray-300 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 outline-none transition-all resize-none"
        placeholder="Describe the visualization you need..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={loading || !selectedIngestion}
      />

      <div className="flex flex-wrap gap-2">
        {shortcuts.map((s) => (
          <button
            key={s}
            onClick={() => handleSubmit(undefined, s)}
            disabled={loading || !selectedIngestion}
            className="text-[10px] uppercase tracking-wider font-bold px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/5 rounded-full text-gray-400 hover:text-blue-400 transition-colors"
          >
            + {s}
          </button>
        ))}
      </div>

      <button
        onClick={(e) => handleSubmit(e)}
        disabled={loading || !selectedIngestion}
        className="w-full py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl text-sm font-bold shadow-lg shadow-blue-900/20 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all uppercase tracking-widest"
      >
        {loading ? "Generating..." : "Generate Visualization"}
      </button>

      {status && (
        <div
          className={`text-center text-xs font-mono ${status.includes("failed") || status.includes("Failed") ? "text-red-500" : "text-blue-400"} animate-pulse`}
        >
          {status}
        </div>
      )}
    </div>
  );
}
