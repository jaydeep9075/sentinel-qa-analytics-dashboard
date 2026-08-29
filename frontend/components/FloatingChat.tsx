// components/FloatingChat.tsx
"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  MessageCircle,
  X,
  Send,
  Sparkles,
  Copy,
  RotateCw,
  Check,
  ThumbsUp,
  ThumbsDown,
  SlidersHorizontal,
  Database,
  ArrowDown,
  Trash2,
} from "lucide-react";
import { useRB } from "@/lib/RBContext";
import { useIngestion } from "@/lib/IngestionContext";
import { sendChatMessage, submitFeedback } from "@/lib/api";
import { ASK_SENTINEL_EVENT } from "@/lib/askSentinel";
import ReactMarkdown from "react-markdown";
import { useSuggestions } from "@/lib/SuggestionsContext";
import { MAX_SUGGESTIONS } from "@/lib/roleSuggestions";
import { formatRoleLabel } from "@/lib/roles";
import ThinkingIndicator from "./ThinkingIndicator";
import BrandLogo from "./BrandLogo";

type ChatMessage = { role: "user" | "ai"; content: string };

const REGEN_QUESTION_CAP = 900;
const REGEN_ANSWER_CAP = 1200;

function capText(value: string, maxChars: number): string {
  const text = String(value || "").trim();
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars).trimEnd()}\n...[truncated]`;
}

export default function FloatingChat() {
  const { selectedRole, selectedProject } = useRB();
  const { selectedIngestion, selectedBuildLabel } = useIngestion();
  const { suggestions: sharedSuggestions } = useSuggestions();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [customQuestion, setCustomQuestion] = useState("");
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null);
  const [regeneratingIndex, setRegeneratingIndex] = useState<number | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<Record<number, string>>({});
  const [isPinnedToBottom, setIsPinnedToBottom] = useState(true);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // The answer style, not the signed-in account's role - those are two
  // different things and used to be conflated.
  const roleLabel = formatRoleLabel(selectedRole || "");
  const buildLabel = selectedBuildLabel || selectedIngestion || "";
  // Suggestions are a starting nudge, not a permanent menu: once the
  // conversation has begun they disappear so the answer owns the panel.
  const suggestions = sharedSuggestions.chat.slice(0, MAX_SUGGESTIONS);
  const showSuggestions = messages.length === 0 && !isLoading;
  const isBusy = isLoading || regeneratingIndex !== null;
  const canSend = Boolean(selectedIngestion) && !isBusy;

  // ── scrolling ──────────────────────────────────────────────────────────
  // A chat panel that does not follow the answer is the single thing that
  // makes one feel broken, so the list sticks to the bottom while the user
  // is already there — and stops sticking the moment they scroll up to read
  // something, rather than yanking them back down mid-sentence.
  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsPinnedToBottom(distanceFromBottom < 80);
  }, []);

  useLayoutEffect(() => {
    if (!isOpen) return;
    if (isPinnedToBottom) scrollToBottom(messages.length <= 1 ? "auto" : "smooth");
    // isPinnedToBottom is read, not tracked: re-running when the user scrolls
    // away would immediately scroll them back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, isLoading, isOpen, scrollToBottom]);

  useEffect(() => {
    if (isOpen) {
      setIsPinnedToBottom(true);
      // Focus after the open animation so the panel doesn't jump.
      const t = setTimeout(() => inputRef.current?.focus(), 250);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // Closing the panel is not the same as ending the conversation — a
  // question asked, the panel closed to look at a chart, then reopened, used
  // to come back to an empty window. The thread now survives; "New chat"
  // below is the explicit way to drop it.
  const clearConversation = () => {
    setMessages([]);
    setCustomQuestion("");
    setFeedbackStatus({});
    inputRef.current?.focus();
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
    if (!selectedIngestion || isBusy) return;
    const question = findRelatedUserQuestion(aiIndex);
    if (!question) return;

    setRegeneratingIndex(aiIndex);
    setIsLoading(true);
    try {
      const regenPrompt = `${capText(question, REGEN_QUESTION_CAP)}\n\nRegenerate this answer with a noticeably improved structure and apply the user's latest feedback preferences.`;
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
    if (!selectedIngestion || isBusy) return;
    const question = findRelatedUserQuestion(aiIndex);
    const previous = messages[aiIndex]?.content || "";
    if (!question) return;

    setRegeneratingIndex(aiIndex);
    setIsLoading(true);
    try {
      const strongPrompt = [
        capText(question, REGEN_QUESTION_CAP),
        "",
        "Previous answer was not accepted by user feedback.",
        `Feedback type: ${feedbackType}`,
        `User notes: ${capText(notes || "No additional note provided", 320)}`,
        "Previous answer:",
        capText(previous, REGEN_ANSWER_CAP),
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
          content: "⚠️ No build selected. Please choose a test build from the top bar first.",
        },
      ]);
      setIsOpen(true);
      return;
    }

    setIsPinnedToBottom(true);
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

  const submitCurrentInput = () => {
    const question = customQuestion.trim();
    if (!question || !canSend) return;
    setCustomQuestion("");
    sendQuestion(question);
  };

  // Other panels (today: the status drill-down) hand a question over by
  // dispatching ASK_SENTINEL_EVENT rather than importing anything from here.
  // Held in a ref so the subscription survives every render - sendQuestion is
  // rebuilt each one, and re-subscribing on every keystroke would be a leak
  // waiting to happen.
  const sendQuestionRef = useRef(sendQuestion);
  sendQuestionRef.current = sendQuestion;

  useEffect(() => {
    const onAsk = (event: Event) => {
      const question = String((event as CustomEvent).detail || "").trim();
      if (!question) return;
      setIsOpen(true);
      sendQuestionRef.current(question);
    };
    window.addEventListener(ASK_SENTINEL_EVENT, onAsk);
    return () => window.removeEventListener(ASK_SENTINEL_EVENT, onAsk);
  }, []);

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitCurrentInput();
  };

  // Enter sends, Shift+Enter breaks the line — the convention every chat
  // product shares, and the reason the input is a textarea rather than the
  // single-line <input> it used to be.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitCurrentInput();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setCustomQuestion(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
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
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          onClick={() => setIsOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 300, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
            className="relative flex h-[min(760px,88vh)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_0_40px_rgba(15,23,42,0.15)] dark:border-white/[0.08] dark:bg-black dark:shadow-[0_0_60px_rgba(0,0,0,0.8),0_0_30px_rgba(0,240,255,0.05)]">
            <div className="pointer-events-none absolute -top-20 right-12 h-40 w-40 rounded-full bg-cyan-500/10 blur-3xl" />
            <div className="pointer-events-none absolute bottom-20 -left-16 h-40 w-40 rounded-full bg-blue-500/10 blur-3xl" />

            {/* ── header ─────────────────────────────────────────────────
                The build being answered about is the one piece of context
                that changes what every reply means, so it is stated here as
                a highlighted chip rather than left to be remembered from a
                dropdown in another part of the page. */}
            <div className="relative z-20 flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-3.5 dark:border-white/[0.06] dark:bg-white/[0.02]">
              <div className="flex min-w-0 items-center gap-3">
                <BrandLogo size={26} />
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold text-slate-900 dark:text-white">
                    <span className="font-bold tracking-tight text-cyan-600 dark:text-cyan-400">-Insight</span>{" "}
                    <span className="font-normal text-slate-500 dark:text-white/50">QA Assistant</span>
                  </h2>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] leading-none">
                    {buildLabel ? (
                      <span
                        title={selectedIngestion || undefined}
                        className="inline-flex max-w-[220px] items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-1 font-semibold text-cyan-700 dark:text-cyan-300"
                      >
                        <Database className="h-3 w-3 shrink-0" />
                        <span className="truncate">{buildLabel}</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 font-semibold text-amber-600 dark:text-amber-400">
                        <Database className="h-3 w-3" />
                        No build selected
                      </span>
                    )}
                    {roleLabel && (
                      <span
                        title="Answer style — the role these answers are written for. Change it from the dashboard header."
                        className="rounded-full border border-slate-200 px-2 py-1 font-medium text-slate-500 dark:border-white/10 dark:text-white/45"
                      >
                        Style: {roleLabel}
                      </span>
                    )}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                {messages.length > 0 && (
                  <button
                    onClick={clearConversation}
                    disabled={isBusy}
                    title="Start a new conversation"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 transition-colors hover:bg-slate-200 disabled:opacity-40 dark:border-white/10 dark:text-white/60 dark:hover:bg-white/[0.06]"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    New chat
                  </button>
                )}
                <button
                  onClick={() => setIsOpen(false)}
                  aria-label="Close chat"
                  className="rounded-lg p-1.5 text-slate-400 transition-all hover:bg-slate-200 hover:text-slate-700 dark:text-white/30 dark:hover:bg-white/[0.06] dark:hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* ── conversation ─────────────────────────────────────────── */}
            <div className="relative z-10 min-h-0 flex-1">
              <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="custom-scrollbar h-full overflow-y-auto overscroll-contain px-5 py-5"
              >
              {messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                  <Sparkles className="mb-3 h-8 w-8 text-cyan-500/40" />
                  <p className="text-sm font-medium text-slate-700 dark:text-white/70">
                    Ask a question about this build&apos;s test results.
                  </p>
                  <p className="mt-1.5 text-xs text-slate-500 dark:text-white/35">
                    {buildLabel
                      ? `Answers are drawn from ${buildLabel}${roleLabel ? `, written for ${roleLabel}` : ""}.`
                      : "Select a test build from the top bar to begin."}
                  </p>

                  {showSuggestions && suggestions.length > 0 && (
                    <div className="mt-6 flex w-full max-w-lg flex-col gap-2">
                      {suggestions.map((q, i) => (
                        <button
                          key={i}
                          onClick={() => sendQuestion(q)}
                          disabled={!canSend}
                          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-left text-[13px] text-slate-600 transition-all hover:border-cyan-500/30 hover:bg-cyan-500/[0.06] hover:text-cyan-700 disabled:opacity-30 dark:border-white/[0.07] dark:bg-white/[0.02] dark:text-white/55 dark:hover:border-cyan-500/25 dark:hover:text-cyan-300"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`rounded-2xl px-4 py-2.5 text-sm ${
                          msg.role === "user"
                            ? "max-w-[85%] whitespace-pre-wrap break-words rounded-tr-sm bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_15px_rgba(0,240,255,0.1)]"
                            : "w-full max-w-[92%] break-words rounded-tl-sm border border-slate-200 bg-slate-100 text-slate-700 dark:border-cyan-500/20 dark:bg-white/[0.04] dark:text-white/75"
                        }`}
                      >
                        {msg.role === "ai" ? (
                          <>
                            {/* No collapse here any more: the panel scrolls,
                                so a long answer is read by scrolling it, not
                                by hunting for a "Read more" button that hid
                                the part the question was about. */}
                            <div className="prose-sm max-w-none">
                              <ReactMarkdown
                                components={{
                                  p: ({ children }) => <p className="my-1.5">{children}</p>,
                                  ul: ({ children }) => (
                                    <ul className="my-1.5 list-disc space-y-0.5 pl-5">{children}</ul>
                                  ),
                                  ol: ({ children }) => (
                                    <ol className="my-1.5 list-decimal space-y-0.5 pl-5">{children}</ol>
                                  ),
                                  li: ({ children }) => <li className="my-0.5">{children}</li>,
                                  strong: ({ children }) => (
                                    <strong className="font-semibold text-slate-900 dark:text-white">
                                      {children}
                                    </strong>
                                  ),
                                  h3: ({ children }) => (
                                    <h3 className="mb-1 mt-3 font-semibold text-slate-900 dark:text-white">
                                      {children}
                                    </h3>
                                  ),
                                  code: ({ children }) => (
                                    <code className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[12px] text-cyan-700 dark:bg-white/10 dark:text-cyan-300">
                                      {children}
                                    </code>
                                  ),
                                  pre: ({ children }) => (
                                    <pre className="my-2 overflow-x-auto rounded-lg bg-slate-200/60 p-3 text-[12px] dark:bg-black/50">
                                      {children}
                                    </pre>
                                  ),
                                  table: ({ children }) => (
                                    <div className="my-2 overflow-x-auto">
                                      <table className="w-full text-left text-[12px]">{children}</table>
                                    </div>
                                  ),
                                  th: ({ children }) => (
                                    <th className="border-b border-slate-300 px-2 py-1 font-semibold dark:border-white/10">
                                      {children}
                                    </th>
                                  ),
                                  td: ({ children }) => (
                                    <td className="border-b border-slate-200/70 px-2 py-1 dark:border-white/[0.06]">
                                      {children}
                                    </td>
                                  ),
                                }}
                              >
                                {msg.content}
                              </ReactMarkdown>
                            </div>

                            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-slate-200/70 pt-2 dark:border-white/[0.06]">
                              <button
                                type="button"
                                onClick={() => handleCopy(msg.content, idx)}
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-800 dark:text-white/45 dark:hover:bg-white/10 dark:hover:text-white"
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
                                disabled={isBusy || !selectedIngestion}
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-slate-500 transition-colors hover:bg-cyan-500/10 hover:text-cyan-700 disabled:opacity-40 dark:text-white/45 dark:hover:text-cyan-300"
                              >
                                <RotateCw className={`h-3 w-3 ${regeneratingIndex === idx ? "animate-spin" : ""}`} />
                                Regenerate
                              </button>
                              <span className="mx-0.5 h-3 w-px bg-slate-300 dark:bg-white/10" />
                              <button
                                type="button"
                                onClick={() => handleFeedback(idx, "up")}
                                title="Good answer"
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-slate-500 transition-colors hover:bg-emerald-500/10 hover:text-emerald-600 dark:text-white/45 dark:hover:text-emerald-300"
                              >
                                <ThumbsUp className="h-3 w-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => handleFeedback(idx, "down", true)}
                                title="Not good — tell us why and we'll retry"
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-600 dark:text-white/45 dark:hover:text-red-300"
                              >
                                <ThumbsDown className="h-3 w-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => handleFeedback(idx, "improve", true)}
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-slate-500 transition-colors hover:bg-amber-500/10 hover:text-amber-600 dark:text-white/45 dark:hover:text-amber-300"
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
                  ))}

                  {isLoading && (
                    <ThinkingIndicator
                      label={
                        regeneratingIndex !== null
                          ? "Rewriting that answer with your feedback…"
                          : undefined
                      }
                    />
                  )}
                </div>
              )}
              </div>

              {/* Jump-to-latest, shown only when the user has scrolled away
                  from the newest message. */}
              <AnimatePresence>
                {!isPinnedToBottom && messages.length > 0 && (
                  <motion.button
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 6 }}
                    onClick={() => {
                      setIsPinnedToBottom(true);
                      scrollToBottom();
                    }}
                    className="absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-600 shadow-lg dark:border-white/10 dark:bg-[#111] dark:text-white/70"
                  >
                    <ArrowDown className="h-3 w-3" />
                    Jump to latest
                  </motion.button>
                )}
              </AnimatePresence>
            </div>

            {/* ── composer ─────────────────────────────────────────────── */}
            <div className="relative z-10 shrink-0 border-t border-slate-200 bg-slate-50 px-5 py-3.5 dark:border-white/[0.06] dark:bg-white/[0.01]">
              <form onSubmit={handleCustomSubmit} className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={customQuestion}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    selectedIngestion
                      ? `Ask about ${buildLabel}…`
                      : "Select a test build from the top bar first…"
                  }
                  className="max-h-[132px] flex-1 resize-none rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm leading-relaxed text-slate-800 transition-all placeholder:text-slate-400 focus:border-cyan-500/30 focus:shadow-[0_0_12px_rgba(0,240,255,0.06)] focus:outline-none focus:ring-1 focus:ring-cyan-500/20 disabled:opacity-60 dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white dark:placeholder:text-white/20"
                  disabled={!canSend}
                />
                <button
                  type="submit"
                  disabled={!customQuestion.trim() || !canSend}
                  aria-label="Send"
                  className="rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2.5 shadow-[0_0_15px_rgba(0,240,255,0.15)] transition-all hover:from-cyan-400 hover:to-blue-500 hover:shadow-[0_0_25px_rgba(0,240,255,0.3)] disabled:opacity-30"
                >
                  <Send className="h-4 w-4 text-white" />
                </button>
              </form>

              <p className="mt-2 text-center text-[10px] text-slate-400 dark:text-white/25">
                {selectedIngestion ? (
                  <>
                    <kbd className="font-sans font-semibold">Enter</kbd> to send ·{" "}
                    <kbd className="font-sans font-semibold">Shift + Enter</kbd> for a new line
                  </>
                ) : (
                  <span className="font-semibold uppercase tracking-wider text-red-400/80">
                    ⚠️ Select a test build from the top bar to start chatting
                  </span>
                )}
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>
    </>
  );
}
