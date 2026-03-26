"use client";

import { useState } from "react";
import AIChatInput from "@/components/AIChatInput";
import ChartGallery from "@/components/ChartGallery";
import AIChatbot from "@/components/AIChatbot";

export default function Home() {
  const [refreshGallery, setRefreshGallery] = useState(0);

  const handleChartGenerated = () => {
    setRefreshGallery((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-[#050505] text-white selection:bg-blue-500/30">
      {/* Background Glow */}
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(17,24,39,1),rgba(0,0,0,1))] -z-10" />

      <div className="container mx-auto px-6 py-10">
        {/* Header */}
        <header className="mb-12">
          <h1 className="text-4xl font-extrabold tracking-tighter bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-500 bg-clip-text text-transparent">
            SENTINEL <span className="text-white/20 font-light">|</span> QA INTELLIGENCE
          </h1>
          <p className="text-gray-500 mt-2 font-medium">
            Autonomous Test Analytics & Agentic Observability
          </p>
        </header>

        {/* AI Control Center */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-stretch">

          {/* Left: Generator */}
          <div className="flex flex-col h-[600px] bg-[#0a0a0a] rounded-2xl border border-white/10 p-8 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-600 to-transparent"></div>
            <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
              Visualizer
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              Command the AI to synthesize custom data visualizations from LanceDB.
            </p>
            <div className="flex-1">
              <AIChatInput onChartGenerated={handleChartGenerated} />
            </div>
          </div>

          {/* Right: Chatbot */}
          <div className="h-[600px]">
            <AIChatbot />
          </div>
        </div>

        {/* Persistent Gallery Section */}
        <div className="mt-16 pb-20">
          <ChartGallery key={refreshGallery} />
        </div>
      </div>
    </div>
  );
}