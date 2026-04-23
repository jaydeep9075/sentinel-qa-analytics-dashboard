"use client";

import { useState, useEffect } from "react";
import { MessageCircle, X, Send } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { sendChatMessage } from "@/lib/api";
import ReactMarkdown from "react-markdown";

/**
 * Predefined questions based on role.
 * Extend this list or fetch from an API endpoint.
 */
const ROLE_QUESTIONS: Record<string, string[]> = {
  "qa-engineer": [
    "Show me all failed tests with error messages",
    "List number of tests per module",
    "What is the average test duration?",
    "Show slowest 10 tests",
    "Give me pass rate by module",
    "Show tests from the Login module",
  ],
  cto: [
    "Is this build ready for release?",
    "Show failure trend and top failure reasons",
    "Give me pass rate and status breakdown",
    "What are the top 5 riskiest modules by failure count?",
    "Summarize key release blockers in 5 bullets",
    "Show overall test health score",
  ],
  // Default fallback
  default: [
    "How many tests passed?",
    "How many tests failed?",
    "Show test count per module",
    "List failed tests",
  ],
};

export default function FloatingChat() {
  const { selectedRole } = useRB();
  const { selectedIngestion } = useIngestion();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<{ role: "user" | "ai"; content: string }[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);

  // Determine which set of questions to show
  const roleKey = (selectedRole || "qa-engineer").toLowerCase();
  const questions = ROLE_QUESTIONS[roleKey] || ROLE_QUESTIONS.default;

  // Clear messages when modal closes (optional)
  useEffect(() => {
    if (!isOpen) {
      // Optional: keep history? We'll reset for simplicity
      setMessages([]);
      setSelectedQuestion(null);
    }
  }, [isOpen]);

  const handleQuestionClick = async (question: string) => {
    if (!selectedIngestion) {
      setMessages([
        { role: "ai", content: "⚠️ No ingestion selected. Please choose a test build first." },
      ]);
      setIsOpen(true);
      return;
    }

    setSelectedQuestion(question);
    setIsLoading(true);
    // Add user message immediately
    setMessages((prev) => [...prev, { role: "user", content: question }]);

    try {
      const answer = await sendChatMessage(
        question,
        selectedIngestion,
        selectedRole,
        undefined // project (optional)
      );
      setMessages((prev) => [...prev, { role: "ai", content: answer }]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: "❌ Error: Could not get answer from AI service." },
      ]);
    } finally {
      setIsLoading(false);
      setSelectedQuestion(null);
    }
  };

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-4 rounded-full shadow-2xl hover:scale-110 transition-all duration-200 focus:outline-none group"
        aria-label="Open chat"
      >
        <MessageCircle className="w-6 h-6 group-hover:rotate-12 transition-transform" />
      </button>

      {/* Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-[#0f0f0f] border border-white/10 rounded-2xl w-full max-w-2xl h-[600px] flex flex-col shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <MessageCircle className="w-5 h-5 text-blue-400" />
                Sentinel QA Assistant
              </h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Messages area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 ? (
                <div className="text-center text-gray-500 mt-8">
                  <p>Select a question below to get started.</p>
                  <p className="text-xs mt-2">Role: {selectedRole || "QA Engineer"}</p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
                        msg.role === "user"
                          ? "bg-blue-600 text-white rounded-tr-none"
                          : "bg-[#1a1a1a] text-gray-300 border border-white/10 rounded-tl-none"
                      }`}
                    >
                      {msg.role === "ai" ? (
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p className="my-1">{children}</p>,
                            ul: ({ children }) => <ul className="list-disc pl-5 my-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal pl-5 my-1">{children}</ol>,
                            li: ({ children }) => <li className="my-0.5">{children}</li>,
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                ))
              )}
              {isLoading && selectedQuestion && (
                <div className="flex justify-start">
                  <div className="bg-[#1a1a1a] rounded-2xl px-4 py-2 flex gap-1">
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></span>
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></span>
                  </div>
                </div>
              )}
            </div>

            {/* Predefined questions (no input field) */}
            <div className="p-4 border-t border-white/10">
              <p className="text-xs text-gray-500 mb-3">Choose a question:</p>
              <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                {questions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleQuestionClick(q)}
                    disabled={isLoading || !selectedIngestion}
                    className="text-xs bg-white/5 hover:bg-blue-500/20 border border-white/10 rounded-full px-3 py-1.5 text-gray-300 hover:text-blue-300 transition-colors disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
              {!selectedIngestion && (
                <p className="text-xs text-red-400 mt-2">
                  ⚠️ Please select an ingestion (test build) from the top bar.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}