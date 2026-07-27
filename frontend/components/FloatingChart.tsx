// components/FloatingChart.tsx (updated)
"use client";

import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BarChart3, X, Loader2, Sparkles } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { generateChart, submitFeedback } from "@/lib/api";
import { useSuggestions } from "@/lib/SuggestionsContext";

export default function FloatingChart() {
  const { selectedRole, selectedProject } = useRB();
  const { selectedIngestion } = useIngestion();
  const { suggestions: sharedSuggestions } = useSuggestions();
  const [isOpen, setIsOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingPrompt, setGeneratingPrompt] = useState<string | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");
  const [recentPrompts, setRecentPrompts] = useState<string[]>([]);
  const [styleFeedback, setStyleFeedback] = useState("");

  const suggestions = sharedSuggestions.chart;

  const handleGenerateChart = async (prompt: string) => {
    const trimmedPrompt = String(prompt || "").trim();
    const styleHint = String(styleFeedback || "").trim();
    if (!trimmedPrompt) return;

    if (!selectedIngestion) {
      setGeneratingPrompt("⚠️ No ingestion selected. Please choose a test build.");
      setTimeout(() => setGeneratingPrompt(null), 3000);
      return;
    }

    setIsGenerating(true);
    setGeneratingPrompt(`Generating: "${trimmedPrompt}"...`);
    window.dispatchEvent(new CustomEvent("chart-generating-start", { detail: trimmedPrompt }));

    try {
      if (styleHint) {
        try {
          await submitFeedback(selectedIngestion, {
            target_kind: "chart",
            feedback_type: "improve",
            prompt: trimmedPrompt,
            notes: styleHint,
            tags: ["chart-style", "color", "readability"],
          });
        } catch {
          // Feedback persistence should not block chart generation.
        }
      }

      const promptWithStyle = styleHint
        ? `${trimmedPrompt}\n\nStyle preference from user: ${styleHint}`
        : trimmedPrompt;

      await generateChart(promptWithStyle, selectedIngestion, selectedRole, selectedProject);
      setRecentPrompts((prev) => {
        const next = [trimmedPrompt, ...prev.filter((p) => p !== trimmedPrompt)];
        return next.slice(0, 6);
      });
      setGeneratingPrompt("✅ Chart ready! See it at the top of the gallery.");
      window.dispatchEvent(new CustomEvent("chart-generated", { detail: trimmedPrompt }));
      // Auto‑close after a short delay
      setTimeout(() => {
        setIsOpen(false);
        setGeneratingPrompt(null);
      }, 1500);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setGeneratingPrompt(`❌ Failed: ${message}`);
      window.dispatchEvent(new CustomEvent("chart-generation-failed", { detail: trimmedPrompt }));
      setTimeout(() => setGeneratingPrompt(null), 4000);
    } finally {
      setIsGenerating(false);
      window.dispatchEvent(new CustomEvent("chart-generating-end", { detail: trimmedPrompt }));
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const prompt = customPrompt.trim();
    if (!prompt || isGenerating) return;
    await handleGenerateChart(prompt);
    setCustomPrompt("");
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
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 20, delay: 0.1 }}
        whileHover={{ scale: 1.1, rotate: -6 }}
        whileTap={{ scale: 0.92 }}
        className="fixed bottom-24 right-6 z-40 bg-gradient-to-r from-purple-500 to-pink-600 text-white p-4 rounded-full shadow-[0_0_30px_rgba(168,85,247,0.25)] hover:shadow-[0_0_50px_rgba(168,85,247,0.4)] focus:outline-none group"
        aria-label="Generate chart"
      >
        <BarChart3 className="w-6 h-6" />
      </motion.button>

      {/* Popover panel */}
      <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.95 }}
          transition={{ type: "spring", stiffness: 320, damping: 26 }}
          className="fixed bottom-36 right-6 z-50 bg-white border border-slate-200 dark:bg-black dark:border-white/[0.08] rounded-2xl w-80 shadow-[0_0_30px_rgba(15,23,42,0.12)] dark:shadow-[0_0_40px_rgba(0,0,0,0.8),0_0_20px_rgba(168,85,247,0.08)] overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50 dark:border-white/[0.06] dark:bg-white/[0.02]">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-purple-400" />
              Chart Suggestion
            </h3>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-slate-700 dark:text-white/40 dark:hover:text-white p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-white/[0.06] transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Content */}
          <div className="p-3 space-y-3 max-h-[22rem] overflow-y-auto custom-scrollbar">
            {generatingPrompt ? (
              <div className="text-xs text-center text-cyan-400 bg-cyan-500/[0.06] border border-cyan-500/15 p-2 rounded-lg flex items-center gap-2 justify-center">
                {isGenerating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {generatingPrompt}
              </div>
            ) : (
              <>
                <form onSubmit={handleCustomSubmit} className="flex gap-2">
                  <input
                    type="text"
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder="Type chart prompt..."
                    disabled={isGenerating || !selectedIngestion}
                    className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-purple-500/40 focus:border-purple-500/40 disabled:opacity-50 dark:border-white/[0.1] dark:bg-black/40 dark:text-white/80 dark:placeholder:text-white/30"
                  />
                  <button
                    type="submit"
                    disabled={!customPrompt.trim() || isGenerating || !selectedIngestion}
                    className="rounded-lg px-3 py-2 text-xs font-semibold text-white bg-gradient-to-r from-purple-500 to-pink-600 hover:from-purple-400 hover:to-pink-500 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Go
                  </button>
                </form>
                <textarea
                  value={styleFeedback}
                  onChange={(e) => setStyleFeedback(e.target.value)}
                  placeholder="Optional chart feedback: e.g. use softer colors, bigger labels, clearer legend"
                  disabled={isGenerating || !selectedIngestion}
                  rows={2}
                  className="w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-purple-500/40 focus:border-purple-500/40 disabled:opacity-50 dark:border-white/[0.1] dark:bg-black/40 dark:text-white/80 dark:placeholder:text-white/30"
                />
                {recentPrompts.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/30">
                      Recent prompts
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {recentPrompts.map((prompt, idx) => (
                        <button
                          key={`${prompt}-${idx}`}
                          type="button"
                          onClick={() => setCustomPrompt(prompt)}
                          className="max-w-full truncate rounded-full border border-purple-500/25 bg-purple-500/10 px-2.5 py-1 text-[10px] font-semibold text-purple-700 hover:bg-purple-500/20 dark:text-purple-300"
                          title={prompt}
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <p className="text-[10px] text-slate-500 dark:text-white/25 uppercase tracking-wider text-center mb-1">
                  {selectedRole || "QA"} prompts
                </p>
                {suggestions.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleGenerateChart(prompt)}
                    disabled={isGenerating || !selectedIngestion}
                    className="group w-full text-left text-xs bg-slate-50 hover:bg-purple-500/[0.08] border border-slate-200 dark:bg-white/[0.03] dark:border-white/[0.06] hover:border-purple-500/20 rounded-lg px-3 py-2 text-slate-600 hover:text-purple-700 dark:text-white/50 dark:hover:text-purple-300 transition-all disabled:opacity-30 flex justify-between items-center"
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
        </motion.div>
      )}
      </AnimatePresence>
    </div>
  );
}