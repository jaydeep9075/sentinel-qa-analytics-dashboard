"use client";

import { useState, useRef, useEffect } from "react";
import { sendChat } from "@/lib/api";

export default function AIChatbot() {
  const [messages, setMessages] = useState<{ role: "user" | "ai"; content: string }[]>([
    { role: "ai", content: "Hello! I am your QA Analytics Assistant. Ask me any question about your test metrics today!" }
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
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setIsLoading(true);

    try {
      const response = await sendChat(userMsg);
      const aiReply = response.data.response || "No response generated.";
      setMessages((prev) => [...prev, { role: "ai", content: aiReply }]);
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || "Sorry, I am having trouble connecting to the server right now.";
      setMessages((prev) => [...prev, { role: "ai", content: `Error: ${errorMsg}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[500px] bg-[#1a1a1a] flex-1 rounded-xl border border-[#2a2a2a] overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 bg-[#141414] border-b border-[#2a2a2a]">
        <h2 className="text-lg font-semibold text-white flex items-center">
          <span className="w-2 h-2 rounded-full bg-green-500 mr-3 animate-pulse"></span>
          AI Test Assistant
        </h2>
        <p className="text-xs text-gray-400 mt-1">Talk naturally to your testing data</p>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-5 py-3 ${
              msg.role === "user"
                ? "bg-blue-600 text-white rounded-br-none"
                : "bg-[#2a2a2a] text-gray-200 rounded-bl-none border border-[#333]"
            }`}>
              <p className="text-sm sm:text-base whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="max-w-[85%] w-16 rounded-2xl rounded-bl-none px-5 py-4 bg-[#2a2a2a] flex items-center justify-center space-x-1.5">
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-[#141414] border-t border-[#2a2a2a]">
        <form onSubmit={handleSend} className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about slow tests, flakiness..."
            className="w-full bg-[#0a0a0a] border border-[#333] text-gray-200 text-sm rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="absolute right-2 top-2 p-1.5 text-blue-500 hover:text-blue-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
              <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
