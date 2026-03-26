"use client";

import { useState, useRef, useEffect } from "react";
import axios from "axios"; // Using axios for cleaner error handling

export default function AIChatbot() {
  const [messages, setMessages] = useState<{ role: "user" | "ai"; content: string }[]>([
    { role: "ai", content: "Hello! I am Sentinel. I have analyzed your local test results from LanceDB. Ask me about flakiness, slow tests, or build trends!" }
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
      // ✅ Ensure this matches your FastAPI URL
      const { data } = await axios.post("http://localhost:8000/ai/chat", {
        message: userMsg
      });

      setMessages((prev) => [...prev, { role: "ai", content: data.response }]);
    } catch (error: any) {
      setMessages((prev) => [...prev, { role: "ai", content: "Error: Could not reach the Sentinel Brain." }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[600px] bg-[#0d0d0d] rounded-xl border border-[#2a2a2a] shadow-2xl overflow-hidden">
      <div className="px-6 py-4 bg-[#141414] border-b border-[#2a2a2a] flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold text-white tracking-widest uppercase flex items-center">
            <span className="w-2 h-2 rounded-full bg-blue-500 mr-2 animate-pulse"></span>
            Sentinel RAG Assistant
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-lg px-4 py-2 text-sm ${msg.role === "user" ? "bg-blue-600 text-white" : "bg-[#1a1a1a] text-gray-300 border border-[#2a2a2a]"
              }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && <div className="text-xs text-gray-500 animate-pulse">Sentinel is querying LanceDB...</div>}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="p-4 bg-[#141414] border-t border-[#2a2a2a]">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g., Which tests failed in the last build?"
          className="w-full bg-black border border-[#333] text-white text-sm rounded-md px-4 py-3 focus:outline-none focus:border-blue-500"
        />
      </form>
    </div>
  );
}