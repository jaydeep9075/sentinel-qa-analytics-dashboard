"use client";

import { useState, useEffect } from "react";
import AIChatbot from "@/components/AIChatbot";
import AIChatInput from "@/components/AIChatInput";
import ChartGallery from "@/components/ChartGallery";
import IngestionSelector from "@/components/IngestionSelector";
import ProjectSelector from "@/components/ProjectSelector";
import RoleSelector from "@/components/RoleSelector";
import { getDataStatus, checkHealth } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";

export default function Home() {
  const { selectedIngestion } = useIngestion();
  const [dataStatus, setDataStatus] = useState<any>(null);
  const [backendConnected, setBackendConnected] = useState(false);
  const [refreshGallery, setRefreshGallery] = useState(0);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const health = await checkHealth();
        setBackendConnected(true);
        if (selectedIngestion) {
          const status = await getDataStatus(selectedIngestion);
          setDataStatus(status);
        }
      } catch (error) {
        setBackendConnected(false);
      }
    };
    checkConnection();
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, [selectedIngestion]);

  const handleChartGenerated = () => {
    setRefreshGallery((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-black text-white">
      <header className="bg-black/50 backdrop-blur-lg border-b border-white/10 sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              Sentinel QA Intelligence
            </h1>
            <p className="text-gray-400 text-sm">AI-Powered Test Analytics</p>
          </div>
          <div className="flex items-center gap-4">
            <IngestionSelector />
            <ProjectSelector />
            <RoleSelector />
            {backendConnected ? (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-xs text-green-400">
                  Backend Connected
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                <span className="text-xs text-red-400">Backend Offline</span>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="container mx-auto px-6 py-8">
        {/* Data Summary Cards */}
        {dataStatus?.has_data && dataStatus.total_rows && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              <p className="text-gray-400 text-sm">Total Tests</p>
              <p className="text-2xl font-bold">
                {dataStatus.total_rows.toLocaleString()}
              </p>
            </div>
            <div className="bg-green-500/10 rounded-lg p-4 border border-green-500/20">
              <p className="text-gray-400 text-sm">Passed</p>
              <p className="text-2xl font-bold text-green-400">
                {dataStatus.status_summary?.passed?.toLocaleString() || 0}
              </p>
            </div>
            <div className="bg-red-500/10 rounded-lg p-4 border border-red-500/20">
              <p className="text-gray-400 text-sm">Failed</p>
              <p className="text-2xl font-bold text-red-400">
                {dataStatus.status_summary?.failed?.toLocaleString() || 0}
              </p>
            </div>
            <div className="bg-blue-500/10 rounded-lg p-4 border border-blue-500/20">
              <p className="text-gray-400 text-sm">Pass Rate</p>
              <p className="text-2xl font-bold text-blue-400">
                {Math.round(
                  ((dataStatus.status_summary?.passed || 0) /
                    dataStatus.total_rows) *
                    100,
                )}
                %
              </p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Chat Section */}
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 h-[600px]">
            <AIChatbot />
          </div>

          {/* Chart Generator Section */}
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 h-[600px]">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-xl font-bold">📊 Chart Generator</h2>
              <p className="text-gray-400 text-sm">Create visualizations</p>
            </div>
            <div className="p-6">
              <AIChatInput onChartGenerated={handleChartGenerated} />
            </div>
          </div>
        </div>

        <div className="mt-16">
          <ChartGallery key={refreshGallery} />
        </div>
      </div>
    </div>
  );
}
