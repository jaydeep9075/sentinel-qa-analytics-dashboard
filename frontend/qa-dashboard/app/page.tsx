"use client";

import { useState } from "react";
import KPICards from "@/components/KPICards";
import StatusChart from "@/components/StatusChart";
import ModuleChart from "@/components/ModuleChart";
import TrendChart from "@/components/TrendChart";
import SlowTests from "@/components/SlowTests";
import FailuresTable from "@/components/FailuresTable";
import AIChatInput from "@/components/AIChatInput";
import ChartGallery from "@/components/ChartGallery";

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

        {/* KPI Cards */}
        <div className="mb-8 sm:mb-10">
          <KPICards />
        </div>

        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 sm:gap-8 mb-8 sm:mb-10">
          <div className="bg-[#1a1a1a] rounded-xl p-4 sm:p-6 border border-[#2a2a2a] hover:border-blue-500/30 transition-all">
            <StatusChart />
          </div>
          <div className="bg-[#1a1a1a] rounded-xl p-4 sm:p-6 border border-[#2a2a2a] hover:border-blue-500/30 transition-all">
            <ModuleChart />
          </div>
        </div>

        {/* Trend Chart */}
        <div className="mb-8 sm:mb-10">
          <div className="bg-[#1a1a1a] rounded-xl p-4 sm:p-6 border border-[#2a2a2a] hover:border-blue-500/30 transition-all">
            <TrendChart />
          </div>
        </div>

        {/* Tables Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 sm:gap-8 mb-8 sm:mb-10">
          <div className="bg-[#1a1a1a] rounded-xl p-4 sm:p-6 border border-[#2a2a2a] hover:border-blue-500/30 transition-all">
            <SlowTests />
          </div>
          <div className="bg-[#1a1a1a] rounded-xl p-4 sm:p-6 border border-[#2a2a2a] hover:border-blue-500/30 transition-all">
            <FailuresTable />
          </div>
        </div>

        {/* AI Chart Generator Section */}
        <div className="mt-8 sm:mt-12">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-2xl blur-xl"></div>
            <div className="relative bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-6 sm:p-8">
              <h2 className="text-xl sm:text-2xl font-bold mb-2 text-white">
                AI Chart Generator
              </h2>
              <p className="text-gray-400 mb-6 text-sm sm:text-base">
                Describe the visualization you want, and our AI will create it
                for you
              </p>
              <AIChatInput onChartGenerated={handleChartGenerated} />
            </div>
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
