"use client";

import { useState, useRef, useEffect } from "react";
import { sendChatMessage } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import { useRB } from "@/lib/RBContext";
import ReactMarkdown from "react-markdown";

export default function AIChatbot() {
  const { selectedIngestion } = useIngestion();
  const { selectedRole, selectedProject } = useRB();
  const roleKey = (selectedRole || "qa").toLowerCase();
  const [messages, setMessages] = useState<
    { role: "user" | "ai"; content: string }[]
  >([
    {
      role: "ai",
      content:
        "System Online. I am Sentinel. How can I assist with your QA analytics today?",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !selectedIngestion) return;

    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await sendChatMessage(
        userMsg,
        selectedIngestion,
        selectedRole,
        selectedProject,
      );
      setMessages((prev) => [...prev, { role: "ai", content: response }]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: "Error: Could not reach AI service." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-5 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-tr-none"
                  : "bg-[#161616] text-gray-300 border border-white/5 rounded-tl-none"
              }`}
            >
              {msg.role === "ai" ? (
                <ReactMarkdown
                  components={{
                    ol: ({ node, ...props }) => (
                      <ol className="list-decimal pl-5 my-2" {...props} />
                    ),
                    ul: ({ node, ...props }) => (
                      <ul className="list-disc pl-5 my-2" {...props} />
                    ),
                    li: ({ node, ...props }) => (
                      <li className="my-1" {...props} />
                    ),
                    strong: ({ node, ...props }) => (
                      <strong className="font-semibold" {...props} />
                    ),
                    p: ({ node, ...props }) => (
                      <p className="my-1" {...props} />
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
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[#161616] rounded-2xl px-5 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="p-4 border-t border-white/10 bg-black/20">
        <div className="flex gap-2 overflow-x-auto pb-3 mb-1 no-scrollbar">
          {(roleKey === "cto"
            ? [
                "Is this result good for release?",
                "Give me pass rate and status breakdown",
                "Show failure trend and top failure reasons",
                "Give me the top 10 riskiest modules by failure count",
                "What are the top 15 slowest tests and duration?",
                "Summarize key release blockers in 5 bullets",
              ]
            : [
                "Give me all available module names",
                "Give me number of tests per module",
                "Show failed tests list with errors",
                "Give me list of tests from Common Functionality / Login module",
                "What is the average time it took to run each test?",
                "Give me the top 15 slowest tests and duration",
              ]
          ).map((suggestion, i) => (
            <button 
              key={i}
              onClick={() => setInput(suggestion)} 
              className="shrink-0 text-xs px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 rounded-full transition border border-blue-500/20 whitespace-nowrap"
            >
              {suggestion}
            </button>
          ))}
        </div>
        <form onSubmit={handleSend} className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask about test results as a ${selectedRole ? selectedRole.toUpperCase() : "QA"}...`}
            className="w-full bg-black/50 border border-white/10 text-white text-sm rounded-xl px-5 py-4 focus:outline-none focus:border-blue-500/50 transition-all placeholder:text-gray-700 pr-12"
            disabled={isLoading || !selectedIngestion}
          />
          <button 
            type="submit" 
            disabled={isLoading || !input.trim() || !selectedIngestion}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
          </button>
        </form>
      </div>
    </div>
  );
}
