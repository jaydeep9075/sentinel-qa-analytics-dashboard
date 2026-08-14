// components/FloatingChat.tsx
"use client";

import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MessageCircle, X, Send, Loader2, Sparkles, Copy, RotateCw, Check, ThumbsUp, ThumbsDown, SlidersHorizontal } from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { sendChatMessage, submitFeedback } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import { useSuggestions } from "@/lib/SuggestionsContext";

export default function FloatingChat() {
  const { selectedRole, selectedProject } = useRB();
  const { selectedIngestion } = useIngestion();
  const { suggestions: sharedSuggestions } = useSuggestions();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<
    { role: "user" | "ai"; content: string }[]
  >([]);
  const [isLoading, setIsLoading] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");
  const [expandedAnswers, setExpandedAnswers] = useState<Record<number, boolean>>({});
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null);
  const [regeneratingIndex, setRegeneratingIndex] = useState<number | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<Record<number, string>>({});
  const LONG_ANSWER_THRESHOLD = 420;

  function formatRoleLabel(role: string): string {
    const normalized = String(role || "").trim().toLowerCase();
    if (!normalized) return "QA Engineer";
    if (normalized === "cto") return "CTO";
    return normalized
      .split("-")
      .map((part) => (part ? `${part[0].toUpperCase()}${part.slice(1)}` : part))
      .join(" ");
  }

  const suggestions = sharedSuggestions.chat;

  useEffect(() => {
    if (!isOpen) {
      setMessages([]);
      setCustomQuestion("");
      setExpandedAnswers({});
    }
  }, [isOpen]);

  const toggleExpandAnswer = (idx: number) => {
    setExpandedAnswers((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const handleCopy = async (content: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageIndex(idx);
      setTimeout(() => setCopiedMessageIndex(null), 1500);
    } catch {
      setCopiedMessageIndex(null);
    }
  };

  const findRelatedUserQuestion = (aiIndex: number) => {
    for (let i = aiIndex - 1; i >= 0; i -= 1) {
      if (messages[i]?.role === "user") {
        return messages[i]?.content || null;
      }
    }
    return null;
  };

  const handleRegenerate = async (aiIndex: number) => {
    if (!selectedIngestion || isLoading) return;
    const question = findRelatedUserQuestion(aiIndex);
    if (!question) return;

    setRegeneratingIndex(aiIndex);
    setIsLoading(true);
    try {
      const regenPrompt = `${question}\n\nRegenerate this answer with a noticeably improved structure and apply the user's latest feedback preferences.`;
      const answer = await sendChatMessage(regenPrompt, selectedIngestion, selectedRole, selectedProject);
      setMessages((prev) =>
        prev.map((m, idx) => (idx === aiIndex ? { ...m, content: answer } : m)),
      );
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Could not regenerate answer.";
      setMessages((prev) =>
        prev.map((m, idx) =>
          idx === aiIndex ? { ...m, content: `❌ Error: ${message}` } : m,
        ),
      );
    } finally {
      setIsLoading(false);
      setRegeneratingIndex(null);
    }
  };

  const regenerateFromFeedback = async (
    aiIndex: number,
    feedbackType: "down" | "improve",
    notes: string,
  ) => {
    if (!selectedIngestion || isLoading) return;
    const question = findRelatedUserQuestion(aiIndex);
    const previous = messages[aiIndex]?.content || "";
    if (!question) return;

    setRegeneratingIndex(aiIndex);
    setIsLoading(true);
    try {
      const strongPrompt = [
        question,
        "",
        "Previous answer was not accepted by user feedback.",
        `Feedback type: ${feedbackType}`,
        `User notes: ${notes || "No additional note provided"}`,
        "Previous answer:",
        previous,
        "",
        "Return a clearly improved answer:",
        "- more accurate and directly actionable",
        "- crisp structure with short bullets",
        "- avoid repeated vague phrases",
        "- ensure quality higher than previous answer",
      ].join("\n");

      const improved = await sendChatMessage(
        strongPrompt,
        selectedIngestion,
        selectedRole,
        selectedProject,
      );

      setMessages((prev) =>
        prev.map((m, idx) => (idx === aiIndex ? { ...m, content: improved } : m)),
      );
    } catch {
      // Keep existing answer if regeneration fails.
    } finally {
      setIsLoading(false);
      setRegeneratingIndex(null);
    }
  };

  const handleFeedback = async (
    aiIndex: number,
    feedbackType: "up" | "down" | "improve",
    askForNotes = false,
  ) => {
    if (!selectedIngestion) return;
    const msg = messages[aiIndex];
    const question = findRelatedUserQuestion(aiIndex) || "";
    if (!msg || msg.role !== "ai") return;

    const notes = askForNotes
      ? window.prompt("What should improve in this answer? You can mention tone, detail, or format.") || ""
      : "";

    try {
      await submitFeedback(selectedIngestion, {
        target_kind: "chat",
        feedback_type: feedbackType,
        prompt: question,
        response: msg.content,
        notes,
        tags: feedbackType === "up" ? ["response-quality"] : ["response-improvement"],
      });
      const statusText =
        feedbackType === "up"
          ? "Marked as good. We will keep this style for future answers."
          : feedbackType === "down"
            ? "Marked as not good. Next responses will avoid this style."
            : "Tune feedback saved. Next responses will adapt to your notes.";
      setFeedbackStatus((prev) => ({ ...prev, [aiIndex]: statusText }));
      if (feedbackType === "down" || feedbackType === "improve") {
        await regenerateFromFeedback(aiIndex, feedbackType, notes);
      }
      setTimeout(() => {
        setFeedbackStatus((prev) => {
          const next = { ...prev };
          delete next[aiIndex];
          return next;
        });
      }, 2200);
    } catch {
      setFeedbackStatus((prev) => ({ ...prev, [aiIndex]: "Could not save feedback. Try again." }));
    }
  };

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
        selectedRole,
        selectedProject,
      );
      setMessages((prev) => [...prev, { role: "ai", content: answer }]);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Could not get answer from AI service.";
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content: `❌ Error: ${message}`,
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
      <motion.button
        onClick={() => setIsOpen(true)}
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 20, delay: 0.15 }}
        whileHover={{ scale: 1.1, rotate: 6 }}
        whileTap={{ scale: 0.92 }}
        className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-cyan-500 to-blue-600 text-white p-4 rounded-full shadow-[0_0_30px_rgba(0,240,255,0.25)] hover:shadow-[0_0_50px_rgba(0,240,255,0.4)] focus:outline-none group"
        aria-label="Open chat"
      >
        <MessageCircle className="w-6 h-6" />
      </motion.button>

      {/* ── Modal ── */}
      <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 300, damping: 28 }}
            className="relative bg-white border border-slate-200 dark:bg-black dark:border-white/[0.08] rounded-2xl w-full max-w-2xl h-[620px] flex flex-col shadow-[0_0_40px_rgba(15,23,42,0.15)] dark:shadow-[0_0_60px_rgba(0,0,0,0.8),0_0_30px_rgba(0,240,255,0.05)] overflow-hidden">
            <div className="pointer-events-none absolute -top-20 right-12 h-40 w-40 rounded-full bg-cyan-500/10 blur-3xl" />
            <div className="pointer-events-none absolute bottom-20 -left-16 h-40 w-40 rounded-full bg-blue-500/10 blur-3xl" />
            {/* header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-slate-50 dark:border-white/[0.06] dark:bg-white/[0.02]">
              <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_12px_rgba(0,240,255,0.2)]">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <span>
                  Sentinel{" "}
                  <span className="text-slate-500 dark:text-white/50 font-normal">QA Assistant</span>
                </span>
              </h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-slate-400 hover:text-slate-700 dark:text-white/30 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-white/[0.06] p-1.5 rounded-lg transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* messages */}
            <div className="relative z-10 flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
              {messages.length === 0 ? (
                <div className="text-center text-slate-500 dark:text-white/25 mt-12">
                  <Sparkles className="w-8 h-8 mx-auto mb-3 text-cyan-500/40" />
                  <p className="text-sm">
                    Ask a question about the test results.
                  </p>
                  <p className="text-[10px] mt-2 uppercase tracking-widest text-slate-400 dark:text-white/15">
                      Role: {formatRoleLabel(selectedRole || "")}
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
                          : "bg-slate-100 text-slate-700 border border-slate-200 dark:bg-white/[0.04] dark:text-white/75 dark:border-cyan-500/20 rounded-tl-sm"
                      }`}
                    >
                      {msg.role === "ai" ? (
                        <>
                          <div
                            className={`relative ${
                              msg.content.length > LONG_ANSWER_THRESHOLD && !expandedAnswers[idx]
                                ? "max-h-44 overflow-hidden"
                                : ""
                            }`}
                          >
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
                            {msg.content.length > LONG_ANSWER_THRESHOLD && !expandedAnswers[idx] && (
                              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-slate-100 to-transparent dark:from-[#121212]" />
                            )}
                          </div>
                          {msg.content.length > LONG_ANSWER_THRESHOLD && (
                            <button
                              type="button"
                              onClick={() => toggleExpandAnswer(idx)}
                              className="mt-2 text-[11px] font-semibold text-cyan-600 hover:text-cyan-700 dark:text-cyan-300 dark:hover:text-cyan-200"
                            >
                              {expandedAnswers[idx] ? "Show less" : "Read more"}
                            </button>
                          )}
                          <div className="mt-2 flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => handleCopy(msg.content, idx)}
                              className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-200 dark:border-white/10 dark:text-white/70 dark:hover:bg-white/10"
                            >
                              {copiedMessageIndex === idx ? (
                                <Check className="h-3 w-3" />
                              ) : (
                                <Copy className="h-3 w-3" />
                              )}
                              {copiedMessageIndex === idx ? "Copied" : "Copy"}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRegenerate(idx)}
                              disabled={isLoading || regeneratingIndex === idx || !selectedIngestion}
                              className="inline-flex items-center gap-1 rounded-md border border-cyan-500/25 px-2 py-1 text-[11px] font-semibold text-cyan-600 hover:bg-cyan-500/10 disabled:opacity-50 dark:text-cyan-300"
                            >
                              <RotateCw className={`h-3 w-3 ${regeneratingIndex === idx ? "animate-spin" : ""}`} />
                              Regenerate
                            </button>
                            <button
                              type="button"
                              onClick={() => handleFeedback(idx, "up")}
                              className="inline-flex items-center gap-1 rounded-md border border-emerald-500/25 px-2 py-1 text-[11px] font-semibold text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-300"
                            >
                              <ThumbsUp className="h-3 w-3" />
                              Good
                            </button>
                            <button
                              type="button"
                              onClick={() => handleFeedback(idx, "down", true)}
                              className="inline-flex items-center gap-1 rounded-md border border-red-500/25 px-2 py-1 text-[11px] font-semibold text-red-600 hover:bg-red-500/10 dark:text-red-300"
                            >
                              <ThumbsDown className="h-3 w-3" />
                              Not good
                            </button>
                            <button
                              type="button"
                              onClick={() => handleFeedback(idx, "improve", true)}
                              className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 px-2 py-1 text-[11px] font-semibold text-amber-600 hover:bg-amber-500/10 dark:text-amber-300"
                            >
                              <SlidersHorizontal className="h-3 w-3" />
                              Tune
                            </button>
                          </div>
                          {feedbackStatus[idx] && (
                            <p className="mt-1 text-[10px] font-semibold text-emerald-500">
                              {feedbackStatus[idx]}
                            </p>
                          )}
                        </>
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                ))
              )}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 border border-slate-200 dark:bg-white/[0.04] dark:border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-2.5 flex gap-2 items-center">
                    <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                    <span className="text-slate-500 dark:text-white/30 text-sm">Thinking...</span>
                  </div>
                </div>
              )}
            </div>

            {/* bottom panel */}
            <div className="px-5 py-4 border-t border-slate-200 bg-slate-50 dark:border-white/[0.06] dark:bg-white/[0.01] space-y-3">
              {/* suggested questions – now role‑based */}
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendQuestion(q)}
                    disabled={isLoading || !selectedIngestion}
                    className="text-[11px] bg-white border border-slate-200 hover:bg-cyan-500/[0.1] hover:border-cyan-500/20 rounded-full px-3 py-1.5 text-slate-600 hover:text-cyan-700 dark:bg-white/[0.03] dark:border-white/[0.06] dark:text-white/40 dark:hover:text-cyan-400 transition-all disabled:opacity-30"
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
                  className="flex-1 bg-white border border-slate-300 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-cyan-500/30 focus:ring-1 focus:ring-cyan-500/20 focus:shadow-[0_0_12px_rgba(0,240,255,0.06)] transition-all dark:bg-white/[0.03] dark:border-white/[0.08] dark:text-white dark:placeholder:text-white/20"
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
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>
    </>
  );
}