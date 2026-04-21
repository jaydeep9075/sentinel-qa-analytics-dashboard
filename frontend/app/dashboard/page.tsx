"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AIChatbot from "@/components/AIChatbot";
import AIChatInput from "@/components/AIChatInput";
import ChartGallery from "@/components/ChartGallery";
import IngestionSelector from "@/components/IngestionSelector";
import ProjectSelector from "@/components/ProjectSelector";
import RoleSelector from "@/components/RoleSelector";
import { getDataStatus, checkHealth } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";

export default function Dashboard() {
  const router = useRouter();
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

  const handleLogout = () => {
    localStorage.clear();
    window.location.href = "/";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-gray-900 to-black text-white selection:bg-blue-500/30 font-sans">
      <header className="bg-white/[0.02] backdrop-blur-xl border-b border-white/10 sticky top-0 z-50 shadow-2xl">
        <div className="container mx-auto px-6 py-4 flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-3 relative">
            <div className="absolute -inset-2 bg-gradient-to-r from-blue-500/20 to-purple-500/20 blur-xl rounded-full pointer-events-none" />
            <div className="w-10 h-10 bg-gradient-to-tr from-blue-500 to-purple-500 rounded-xl flex items-center justify-center font-bold text-lg shadow-lg relative z-10">
              S
            </div>
            <div className="relative z-10">
              <h1 className="text-xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
                Sentinel Dashboard
              </h1>
              <p className="text-gray-500 text-xs tracking-wider uppercase font-semibold">QA Intelligence Platform</p>
            </div>
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
            <Link 
              href="/build-trends" 
              className="text-sm text-blue-400 hover:text-blue-300 font-bold ml-2 border border-blue-500/30 px-3 py-1.5 rounded-lg bg-blue-500/10 transition-colors"
            >
              Build Trends
            </Link>
            <button
              onClick={handleLogout}
              className="text-sm text-red-400 hover:text-red-300 ml-2"
            >
              Logout
            </button>
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
