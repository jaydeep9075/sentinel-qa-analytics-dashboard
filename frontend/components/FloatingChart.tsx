// components/FloatingChart.tsx (updated)
"use client";

import { useState, useEffect } from "react";
import { BarChart3, X, Loader2, Sparkles } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { generateChart } from "@/lib/api";
import { getRoleSuggestions } from "@/lib/roleSuggestions";

export default function FloatingChart() {
  const { selectedRole } = useRB();
  const { selectedIngestion } = useIngestion();
  const [isOpen, setIsOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingPrompt, setGeneratingPrompt] = useState<string | null>(null);

  // Get role‑specific chart prompts
  const suggestions = getRoleSuggestions(selectedRole || "").chart;

  const handleGenerateChart = async (prompt: string) => {
    if (!selectedIngestion) {
      setGeneratingPrompt("⚠️ No ingestion selected. Please choose a test build.");
      setTimeout(() => setGeneratingPrompt(null), 3000);
      return;
    }

    setIsGenerating(true);
    setGeneratingPrompt(`Generating: "${prompt}"...`);
    window.dispatchEvent(new CustomEvent("chart-generating-start", { detail: prompt }));

    try {
      await generateChart(prompt, selectedIngestion);
      setGeneratingPrompt("✅ Chart ready! See it at the top of the gallery.");
      window.dispatchEvent(new CustomEvent("chart-generated"));
      // Auto‑close after a short delay
      setTimeout(() => {
        setIsOpen(false);
        setGeneratingPrompt(null);
      }, 1500);
    } catch (error: any) {
      setGeneratingPrompt(`❌ Failed: ${error.message}`);
      setTimeout(() => setGeneratingPrompt(null), 4000);
    } finally {
      setIsGenerating(false);
      window.dispatchEvent(new CustomEvent("chart-generating-end", { detail: prompt }));
    }
  };

  // Close popover when clicking outside (optional)
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (isOpen && !target.closest('[data-floating-chart]')) {
        setIsOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [isOpen]);

  return (
    <div data-floating-chart className="relative inline-block">
      {/* FAB button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-24 right-6 z-40 bg-gradient-to-r from-purple-500 to-pink-600 text-white p-4 rounded-full shadow-[0_0_30px_rgba(168,85,247,0.25)] hover:shadow-[0_0_50px_rgba(168,85,247,0.4)] hover:scale-110 transition-all duration-200 focus:outline-none group"
        aria-label="Generate chart"
      >
        <BarChart3 className="w-6 h-6 group-hover:rotate-6 transition-transform" />
      </button>

      {/* Popover panel */}
      {isOpen && (
        <div className="fixed bottom-36 right-6 z-50 bg-black border border-white/[0.08] rounded-2xl w-72 shadow-[0_0_40px_rgba(0,0,0,0.8),0_0_20px_rgba(168,85,247,0.08)] overflow-hidden animate-in slide-in-from-bottom-2">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-purple-400" />
              Chart Suggestion
            </h3>
            <button
              onClick={() => setIsOpen(false)}
              className="text-white/40 hover:text-white p-1 rounded-lg hover:bg-white/[0.06] transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Content */}
          <div className="p-3 space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
            {generatingPrompt ? (
              <div className="text-xs text-center text-cyan-400 bg-cyan-500/[0.06] border border-cyan-500/15 p-2 rounded-lg flex items-center gap-2 justify-center">
                {isGenerating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {generatingPrompt}
              </div>
            ) : (
              <>
                <p className="text-[10px] text-white/25 uppercase tracking-wider text-center mb-1">
                  {selectedRole || "QA"} prompts
                </p>
                {suggestions.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleGenerateChart(prompt)}
                    disabled={isGenerating || !selectedIngestion}
                    className="group w-full text-left text-xs bg-white/[0.03] hover:bg-purple-500/[0.08] border border-white/[0.06] hover:border-purple-500/20 rounded-lg px-3 py-2 text-white/50 hover:text-purple-300 transition-all disabled:opacity-30 flex justify-between items-center"
                  >
                    <span>{prompt}</span>
                    <Sparkles className="w-3 h-3 opacity-0 group-hover:opacity-100 text-purple-400 transition-opacity flex-shrink-0" />
                  </button>
                ))}
              </>
            )}
            {!selectedIngestion && (
              <p className="text-[10px] text-red-400/70 text-center uppercase tracking-wider mt-2">
                ⚠️ No build selected
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}