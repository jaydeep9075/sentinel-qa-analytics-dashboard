"use client";

import { useState } from "react";
// Static chart components removed per user request in favor of 100% AI dynamic generation
import AIChatInput from "@/components/AIChatInput";
import ChartGallery from "@/components/ChartGallery";
import AIChatbot from "@/components/AIChatbot";

export default function Home() {
  const [refreshGallery, setRefreshGallery] = useState(0);

  const handleChartGenerated = () => {
    setRefreshGallery((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0a0a0a] via-[#0f0f0f] to-[#1a1a1a]">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
        {/* Header */}
        <div className="mb-8 sm:mb-10">
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            Sentinel QA AI Analytics Dashboard
          </h1>
          <p className="text-gray-400 mt-2 text-sm sm:text-base">
            AI-powered test analytics and visualization platform
          </p>
        </div>

        {/* All static dashboard components have been removed. 
            The Layout relies exclusively on the AI Chart Generator. */}

        {/* AI Interactions Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 sm:gap-8 mt-4 sm:mt-8">
          
          {/* Left Column: AI Chart Generator */}
          <div className="relative h-[500px]">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-2xl blur-xl"></div>
            <div className="relative h-full bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-6 sm:p-8 flex flex-col">
              <h2 className="text-xl sm:text-2xl font-bold mb-2 text-white">
                AI Chart Generator
              </h2>
              <p className="text-gray-400 mb-6 text-sm sm:text-base">
                Select a primary test analytic from the predefined prompts below, and our model will securely execute localized queries to generate your chart.
              </p>
              <div className="flex-1 overflow-y-auto pr-2">
                <AIChatInput onChartGenerated={handleChartGenerated} />
              </div>
            </div>
          </div>

          {/* Right Column: AI Chatbot */}
          <div className="h-full min-h-[500px] flex">
             <AIChatbot />
          </div>

        </div>

        {/* Chart Gallery Section */}
        <div className="mt-8 sm:mt-12">
          <ChartGallery key={refreshGallery} />
        </div>
      </div>
    </div>
  );
}
