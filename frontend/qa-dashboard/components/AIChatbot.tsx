"use client";

import { useState, useRef, useEffect } from "react";
import axios from "axios";

export default function AIChatbot() {
  const [messages, setMessages] = useState<{ role: "user" | "ai"; content: string }[]>([
    { role: "ai", content: "System Online. I am Sentinel. Accessing LanceDB test metadata. How can I assist with your QA analytics today?" }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setIsLoading(true);

    try {
      const { data } = await axios.post("http://localhost:8000/ai/chat", { message: userMsg });
      setMessages((prev) => [...prev, { role: "ai", content: data.response }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "ai", content: "Error: Neural link to Sentinel backend failed." }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0a0a] rounded-2xl border border-white/10 shadow-2xl overflow-hidden relative">
      <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-purple-600 to-transparent"></div>

      {/* Header */}
      <div className="px-6 py-4 bg-[#0f0f0f] border-b border-white/5 flex items-center justify-between">
        <span className="text-xs font-bold tracking-widest text-purple-400 uppercase">Agentic RAG Assistant</span>
        <div className="flex gap-1">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-5 py-3 text-sm leading-relaxed ${msg.role === "user"
              ? "bg-blue-600 text-white rounded-tr-none shadow-lg shadow-blue-900/20"
              : "bg-[#161616] text-gray-300 border border-white/5 rounded-tl-none"
              }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex items-center gap-2 text-[10px] text-purple-500 font-mono italic">
            <span className="animate-spin text-lg italic">◌</span> QUERYING LANCE_VECTOR_DB...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSend} className="p-4 bg-[#0f0f0f] border-t border-white/5">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about flakiness, trends, or specific errors..."
          className="w-full bg-black border border-white/10 text-white text-sm rounded-xl px-5 py-4 focus:outline-none focus:border-purple-500/50 transition-all placeholder:text-gray-700"
        />
      </form>
    </div>
  );
}