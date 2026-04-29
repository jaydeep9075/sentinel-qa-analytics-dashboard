"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { sendChatMessage } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import { useRB } from "@/lib/RBContext";
import { getRoleSuggestions } from "@/lib/roleSuggestions";
import ReactMarkdown from "react-markdown";
import { Trash2, RefreshCw } from "lucide-react";

interface Message {
  role: "user" | "ai";
  content: string;
  timestamp: number;
}

const STORAGE_KEY_PREFIX = "sentinel_chat_";

export default function AIChatbot() {
  const { selectedIngestion } = useIngestion();
  const { selectedRole } = useRB();

  const storageKey = `${STORAGE_KEY_PREFIX}${selectedIngestion || "default"}`;

  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === "undefined") return [defaultWelcome()];
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Message[];
        if (parsed.length > 0) return parsed;
      }
    } catch {}
    return [defaultWelcome()];
  });

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      // Keep only last 100 messages in storage
      const toStore = messages.slice(-100);
      localStorage.setItem(storageKey, JSON.stringify(toStore));
    } catch {}
  }, [messages, storageKey]);

  // Reload messages when ingestion changes
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Message[];
        if (parsed.length > 0) {
          setMessages(parsed);
          return;
        }
      }
    } catch {}
    setMessages([defaultWelcome()]);
  }, [storageKey]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function defaultWelcome(): Message {
    return {
      role: "ai",
      content:
        "**Sentinel Online.** Ask me anything about your test results — pass rates, failures, modules, release readiness, and more.",
      timestamp: Date.now(),
    };
  }

  const clearHistory = useCallback(() => {
    const welcome = defaultWelcome();
    setMessages([welcome]);
    try {
      localStorage.setItem(storageKey, JSON.stringify([welcome]));
    } catch {}
  }, [storageKey]);

  const handleSend = async (e?: React.FormEvent, overrideMessage?: string) => {
    e?.preventDefault();
    const userMsg = (overrideMessage ?? input).trim();
    if (!userMsg || isLoading || !selectedIngestion) return;

    const userEntry: Message = { role: "user", content: userMsg, timestamp: Date.now() };
    setMessages((prev) => [...prev, userEntry]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await sendChatMessage(
        userMsg,
        selectedIngestion,
        selectedRole,
        undefined,
      );
      const aiEntry: Message = { role: "ai", content: response, timestamp: Date.now() };
      setMessages((prev) => [...prev, aiEntry]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: "❌ Could not reach the AI service. Check your connection.", timestamp: Date.now() },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const formatTime = (ts: number) => {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  // Role-specific suggestions
  const chatSuggestions = getRoleSuggestions(selectedRole || "").chat.slice(0, 8);

  return (
    <div className="flex flex-col h-full bg-transparent">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/5 bg-black/20">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-mono text-gray-400 tracking-widest uppercase">
            Sentinel Chat
          </span>
          {selectedIngestion && (
            <span className="text-xs text-gray-600 font-mono">· {selectedIngestion}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600 font-mono">
            {messages.length - 1} messages
          </span>
          <button
            onClick={clearHistory}
            title="Clear chat history"
            className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-thin scrollbar-thumb-white/10">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"} gap-0.5`}
          >
            <div
              className={`max-w-[88%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-600/90 text-white rounded-tr-sm"
                  : "bg-[#111111] text-gray-200 border border-white/5 rounded-tl-sm"
              }`}
            >
              {msg.role === "ai" ? (
                <ReactMarkdown
                  components={{
                    ol: ({ node, ...props }) => (
                      <ol className="list-decimal pl-5 my-1.5 space-y-0.5" {...props} />
                    ),
                    ul: ({ node, ...props }) => (
                      <ul className="list-disc pl-5 my-1.5 space-y-0.5" {...props} />
                    ),
                    li: ({ node, ...props }) => <li className="text-sm" {...props} />,
                    strong: ({ node, ...props }) => (
                      <strong className="font-semibold text-white" {...props} />
                    ),
                    p: ({ node, ...props }) => <p className="my-1" {...props} />,
                    code: ({ node, ...props }) => (
                      <code
                        className="bg-white/10 rounded px-1 py-0.5 text-xs font-mono text-blue-300"
                        {...props}
                      />
                    ),
                    h3: ({ node, ...props }) => (
                      <h3 className="font-semibold text-white mt-2 mb-1" {...props} />
                    ),
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              ) : (
                <span>{msg.content}</span>
              )}
            </div>
            <span className="text-[10px] text-gray-600 font-mono px-1">
              {formatTime(msg.timestamp)}
            </span>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-start gap-2">
            <div className="bg-[#111111] border border-white/5 rounded-2xl rounded-tl-sm px-4 py-2.5">
              <div className="flex gap-1 items-center">
                <span className="text-xs text-gray-500 font-mono mr-1">thinking</span>
                <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      <div className="px-4 pt-3 pb-1">
        <div className="flex gap-1.5 overflow-x-auto pb-2 no-scrollbar">
          {chatSuggestions.map((q, i) => (
            <button
              key={i}
              onClick={() => handleSend(undefined, q)}
              disabled={isLoading || !selectedIngestion}
              className="shrink-0 text-[10px] px-3 py-1.5 bg-blue-500/8 hover:bg-blue-500/15 text-blue-400 rounded-full transition-all border border-blue-500/15 whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed font-mono tracking-wide"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Input area */}
      <div className="px-4 pb-4">
        <form onSubmit={handleSend} className="relative">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              selectedIngestion
                ? "Ask about test results, failures, modules..."
                : "Select a test build first..."
            }
            className="w-full bg-black/60 border border-white/8 text-white text-sm rounded-xl px-4 py-3.5 pr-12 focus:outline-none focus:border-blue-500/40 transition-all placeholder:text-gray-600 font-mono"
            disabled={isLoading || !selectedIngestion}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim() || !selectedIngestion}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-600 text-white rounded-lg transition-all"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </button>
        </form>
        {!selectedIngestion && (
          <p className="text-xs text-amber-500/70 text-center mt-2 font-mono">
            ⚠ Select a test build from the top bar to start chatting
          </p>
        )}
      </div>
    </div>
  );
}