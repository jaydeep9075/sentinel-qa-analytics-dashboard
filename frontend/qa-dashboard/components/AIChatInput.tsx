"use client";

import { useState } from "react";
import axios from "axios";

interface AIChatInputProps {
  onChartGenerated: () => void;
}

export default function AIChatInput({ onChartGenerated }: AIChatInputProps) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const shortcuts = [
    "Bar chart of failure reasons",
    "Slowest 5 tests this week",
    "Test duration trend line"
  ];

  const handleSubmit = async (e?: React.FormEvent, manualPrompt?: string) => {
    e?.preventDefault();
    const activePrompt = manualPrompt || prompt;
    if (!activePrompt.trim()) return;

    setLoading(true);
    setStatus("Analyzing LanceDB...");

    try {
      const { data } = await axios.post("http://localhost:8000/ai/generate-chart", {
        message: activePrompt
      });

      if (data.success) {
        setPrompt("");
        setStatus("Chart synthesized successfully!");
        onChartGenerated();
        setTimeout(() => setStatus(null), 3000);
      }
    } catch (err) {
      setStatus("Generation failed. Check console.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <textarea
          rows={4}
          className="w-full bg-[#050505] border border-white/10 rounded-xl p-4 text-sm text-gray-300 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 outline-none transition-all resize-none"
          placeholder="Describe the visualization you need..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        {/* Quick Shortcuts */}
        <div className="flex flex-wrap gap-2">
          {shortcuts.map((s) => (
            <button
              key={s}
              onClick={() => handleSubmit(undefined, s)}
              className="text-[10px] uppercase tracking-wider font-bold px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/5 rounded-full text-gray-400 hover:text-blue-400 transition-colors"
            >
              + {s}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={(e) => handleSubmit(e)}
        disabled={loading}
        className="w-full py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl text-sm font-bold shadow-lg shadow-blue-900/20 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all uppercase tracking-widest"
      >
        {loading ? "Processing Metadata..." : "Generate Visualization"}
      </button>

      {status && (
        <div className={`text-center text-xs font-mono ${status.includes("failed") ? "text-red-500" : "text-blue-400"} animate-pulse`}>
          {status}
        </div>
      )}
    </div>
  );
}