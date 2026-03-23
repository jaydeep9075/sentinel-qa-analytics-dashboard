"use client";

import { useState } from "react";
import { generateChart } from "@/lib/api";

interface AIChatInputProps {
  onChartGenerated: () => void;
}

export default function AIChatInput({ onChartGenerated }: AIChatInputProps) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!prompt.trim()) {
      setError("Please enter a prompt");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const response = await generateChart(prompt);

      if (response.data.success) {
        setSuccess("Chart generated successfully!");
        setPrompt("");
        onChartGenerated();
      } else {
        setError(response.data.error || "Failed to generate chart");
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Error connecting to AI service");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full">
      <form onSubmit={handleSubmit}>
        <div className="mb-4">
          <label
            htmlFor="prompt"
            className="block text-sm font-medium text-gray-300 mb-2"
          >
            Describe the visualization you want
          </label>
          <textarea
            id="prompt"
            rows={4}
            className="w-full px-4 py-3 bg-[#0f0f0f] border border-[#2a2a2a] rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-200 placeholder-gray-500 transition-all"
            placeholder="Example: Show me a pie chart of test status distribution, or Create a heatmap of test failures by module..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center space-y-3 sm:space-y-0 sm:space-x-4">
          <button
            type="submit"
            disabled={loading}
            className={`w-full sm:w-auto px-6 py-2.5 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-lg hover:from-blue-700 hover:to-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-[#1a1a1a] font-medium transition-all ${
              loading ? "opacity-50 cursor-not-allowed" : ""
            }`}
          >
            {loading ? "Generating..." : "Generate Chart"}
          </button>

          {loading && (
            <div className="flex items-center text-gray-400">
              <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              AI is thinking...
            </div>
          )}
        </div>

        {error && (
          <div className="mt-4 p-4 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg">
            {error}
          </div>
        )}

        {success && (
          <div className="mt-4 p-4 bg-green-500/10 border border-green-500/30 text-green-400 rounded-lg">
            {success}
          </div>
        )}
      </form>

      <div className="mt-6">
        <h3 className="text-sm font-medium text-gray-300 mb-3">
          Example Prompts:
        </h3>
        <div className="flex flex-wrap gap-2">
          {[
            "Find tests that both passed and failed in the last 5 runs",
            "Show top 10 slowest tests by average duration",
            "Show failure percentage per module",
            "Group similar error messages",
            "Compare current run vs previous run failures",
            "Compare DEV vs QA failure rates",
            "Show tests that passed only after retry",
            "Calculate stability score per test",
            "Create risk score = failure_rate * duration",
            "Find slow tests that rarely fail",
          ].map((example, i) => (
            <button
              key={i}
              onClick={() => setPrompt(example)}
              className="px-3 py-1.5 bg-[#0f0f0f] text-gray-300 rounded-lg text-sm hover:bg-[#2a2a2a] hover:text-white border border-[#2a2a2a] transition-all"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
