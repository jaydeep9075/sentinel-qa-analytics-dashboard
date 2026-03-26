"use client";

import { useState } from "react";
import axios from "axios";

interface AIChatInputProps {
  onChartGenerated: () => void;
}

export default function AIChatInput({ onChartGenerated }: AIChatInputProps) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    try {
      // ✅ Hits the Chart Generation endpoint
      const { data } = await axios.post("http://localhost:8000/ai/generate-chart", {
        message: prompt
      });

      if (data.success) {
        setPrompt("");
        onChartGenerated(); // Refresh the gallery to show the new chart
      }
    } catch (err) {
      console.error("Chart generation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#141414] p-6 rounded-xl border border-[#2a2a2a]">
      <h3 className="text-white font-semibold mb-4">AI Visualizer</h3>
      <form onSubmit={handleSubmit} className="space-y-4">
        <textarea
          rows={3}
          className="w-full bg-black border border-[#333] rounded-lg p-3 text-sm text-gray-300 focus:border-blue-500 outline-none"
          placeholder="Describe a chart (e.g., 'Bar chart of failures per module')"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "AI is drawing..." : "Generate Custom Visualization"}
        </button>
      </form>
    </div>
  );
}