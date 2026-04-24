// components/FloatingChat.tsx
"use client";

import { useState, useEffect } from "react";
import { MessageCircle, X, Send, Loader2, Sparkles } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { sendChatMessage } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import { getRoleSuggestions } from "@/lib/roleSuggestions";

export default function FloatingChat() {
  const { selectedRole } = useRB();
  const { selectedIngestion } = useIngestion();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<
    { role: "user" | "ai"; content: string }[]
  >([]);
  const [isLoading, setIsLoading] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");

  // Get role‑specific chat questions
  const suggestions = getRoleSuggestions(selectedRole || "").chat;

  useEffect(() => {
    if (!isOpen) {
      setMessages([]);
      setCustomQuestion("");
    }
  }, [isOpen]);

  const sendQuestion = async (question: string) => {
    if (!selectedIngestion) {
      setMessages([
        {
          role: "ai",
          content: "⚠️ No ingestion selected. Please choose a test build first.",
        },
      ]);
      setIsOpen(true);
      return;
    }

    setIsLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: question }]);

    try {
      const answer = await sendChatMessage(
        question,
        selectedIngestion,
        selectedRole
      );
      setMessages((prev) => [...prev, { role: "ai", content: answer }]);
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content: `❌ Error: ${error.message || "Could not get answer from AI service."}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customQuestion.trim()) {
      sendQuestion(customQuestion.trim());
      setCustomQuestion("");
    }
  };

  return (
    <>
      {/* ── FAB ── */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-cyan-500 to-blue-600 text-white p-4 rounded-full shadow-[0_0_30px_rgba(0,240,255,0.25)] hover:shadow-[0_0_50px_rgba(0,240,255,0.4)] hover:scale-110 transition-all duration-200 focus:outline-none group"
        aria-label="Open chat"
      >
        <MessageCircle className="w-6 h-6 group-hover:rotate-12 transition-transform" />
      </button>

      {/* ── Modal ── */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="bg-black border border-white/[0.08] rounded-2xl w-full max-w-2xl h-[600px] flex flex-col shadow-[0_0_60px_rgba(0,0,0,0.8),0_0_30px_rgba(0,240,255,0.05)] overflow-hidden">
            {/* header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06] bg-white/[0.02]">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_12px_rgba(0,240,255,0.2)]">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <span>
                  Sentinel{" "}
                  <span className="text-white/50 font-normal">QA Assistant</span>
                </span>
              </h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-white/30 hover:text-white hover:bg-white/[0.06] p-1.5 rounded-lg transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* messages */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
              {messages.length === 0 ? (
                <div className="text-center text-white/25 mt-12">
                  <Sparkles className="w-8 h-8 mx-auto mb-3 text-cyan-500/40" />
                  <p className="text-sm">
                    Ask a question about the test results.
                  </p>
                  <p className="text-[10px] mt-2 uppercase tracking-widest text-white/15">
                    Role: {selectedRole || "QA Engineer"}
                  </p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${
                      msg.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                        msg.role === "user"
                          ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white rounded-tr-sm shadow-[0_0_15px_rgba(0,240,255,0.1)]"
                          : "bg-white/[0.04] text-white/70 border border-white/[0.06] rounded-tl-sm"
                      }`}
                    >
                      {msg.role === "ai" ? (
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => (
                              <p className="my-1">{children}</p>
                            ),
                            ul: ({ children }) => (
                              <ul className="list-disc pl-5 my-1">
                                {children}
                              </ul>
                            ),
                            ol: ({ children }) => (
                              <ol className="list-decimal pl-5 my-1">
                                {children}
                              </ol>
                            ),
                            li: ({ children }) => (
                              <li className="my-0.5">{children}</li>
                            ),
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
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-white/[0.04] border border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-2.5 flex gap-2 items-center">
                    <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                    <span className="text-white/30 text-sm">Thinking...</span>
                  </div>
                </div>
              )}
            </div>

            {/* bottom panel */}
            <div className="px-5 py-4 border-t border-white/[0.06] bg-white/[0.01] space-y-3">
              {/* suggested questions – now role‑based */}
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendQuestion(q)}
                    disabled={isLoading || !selectedIngestion}
                    className="text-[11px] bg-white/[0.03] hover:bg-cyan-500/[0.1] border border-white/[0.06] hover:border-cyan-500/20 rounded-full px-3 py-1.5 text-white/40 hover:text-cyan-400 transition-all disabled:opacity-30"
                  >
                    {q}
                  </button>
                ))}
              </div>

              {/* custom input */}
              <form onSubmit={handleCustomSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={customQuestion}
                  onChange={(e) => setCustomQuestion(e.target.value)}
                  placeholder="Or type your own question..."
                  className="flex-1 bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-cyan-500/30 focus:ring-1 focus:ring-cyan-500/20 focus:shadow-[0_0_12px_rgba(0,240,255,0.06)] transition-all"
                  disabled={isLoading || !selectedIngestion}
                />
                <button
                  type="submit"
                  disabled={
                    !customQuestion.trim() || isLoading || !selectedIngestion
                  }
                  className="bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-30 rounded-xl px-4 py-2.5 shadow-[0_0_15px_rgba(0,240,255,0.15)] hover:shadow-[0_0_25px_rgba(0,240,255,0.3)] transition-all"
                >
                  <Send className="w-4 h-4 text-white" />
                </button>
              </form>

              {!selectedIngestion && (
                <p className="text-[10px] text-red-400/70 text-center uppercase tracking-wider">
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