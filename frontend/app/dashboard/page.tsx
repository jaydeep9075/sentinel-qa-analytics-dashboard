"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Shield, TrendingUp, LogOut, Wifi, WifiOff } from "lucide-react";
import ChartGallery from "@/components/ChartGallery";
import IngestionSelector from "@/components/IngestionSelector";
import ProjectSelector from "@/components/ProjectSelector";
import RoleSelector from "@/components/RoleSelector";
import FloatingChat from "@/components/FloatingChat";
import FloatingChart from "@/components/FloatingChart";  // new
import { getDataStatus, checkHealth } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";

export default function Dashboard() {
  const router = useRouter();
  const { selectedIngestion } = useIngestion();
  const [dataStatus, setDataStatus] = useState<any>(null);
  const [backendConnected, setBackendConnected] = useState(false);
  const [refreshGallery, setRefreshGallery] = useState(0);

  // Listen for chart-generated events from FloatingChart
  useEffect(() => {
    const handleChartGenerated = () => {
      setRefreshGallery(prev => prev + 1);
    };
    window.addEventListener("chart-generated", handleChartGenerated);
    return () => window.removeEventListener("chart-generated", handleChartGenerated);
  }, []);

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

  const handleLogout = () => {
    localStorage.clear();
    window.location.href = "/";
  };

  return (
    <div className="min-h-screen bg-black text-white selection:bg-cyan-500/30 font-sans">
      {/* ══════════ HEADER ══════════ */}
      <header className="bg-black/80 backdrop-blur-xl border-b border-white/[0.06] sticky top-0 z-50 shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="max-w-[1600px] mx-auto px-6 py-3.5 flex flex-col md:flex-row justify-between items-center gap-4">
          {/* left: logo */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_20px_rgba(0,240,255,0.25)]">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">
                <span className="text-cyan-400">Sentinel</span>{" "}
                <span className="text-white/60 font-normal">Dashboard</span>
              </h1>
              <p className="text-[10px] text-white/25 uppercase tracking-widest font-semibold">QA Intelligence Platform</p>
            </div>
          </div>

          {/* right: selectors + status + actions */}
          <div className="flex items-center gap-3 flex-wrap justify-end">
            <IngestionSelector />
            <ProjectSelector />
            <RoleSelector />

            {/* connection status */}
            {backendConnected ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/[0.08] border border-emerald-500/20">
                <Wifi className="w-3 h-3 text-emerald-400" />
                <span className="text-[10px] text-emerald-400 uppercase tracking-wider font-semibold">Connected</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-500/[0.08] border border-red-500/20">
                <WifiOff className="w-3 h-3 text-red-400" />
                <span className="text-[10px] text-red-400 uppercase tracking-wider font-semibold">Offline</span>
              </div>
            )}

            {/* build trends link */}
            <Link
              href="/build-trends"
              className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 font-semibold border border-cyan-500/20 px-3 py-1.5 rounded-lg bg-cyan-500/[0.06] hover:bg-cyan-500/[0.12] hover:border-cyan-500/30 hover:shadow-[0_0_15px_rgba(0,240,255,0.08)] transition-all"
            >
              <TrendingUp className="w-3.5 h-3.5" />
              Build Trends
            </Link>

            {/* logout */}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 text-xs text-red-400/70 hover:text-red-400 hover:bg-red-500/[0.08] px-3 py-1.5 rounded-lg transition-all"
            >
              <LogOut className="w-3.5 h-3.5" />
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <div className="max-w-[1600px] mx-auto px-6 py-8">
        {/* Data Summary Cards */}
        {dataStatus?.has_data && dataStatus.total_rows && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            {/* Total Tests */}
            <div className="group relative rounded-2xl p-5 border border-white/[0.06] bg-white/[0.02] hover:border-cyan-500/20 hover:bg-cyan-500/[0.03] transition-all overflow-hidden">
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-cyan-500/[0.06] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] text-white/30 uppercase tracking-widest font-semibold mb-1">Total Tests</p>
              <p className="text-3xl font-bold text-white group-hover:text-cyan-400 transition-colors">
                {dataStatus.total_rows.toLocaleString()}
              </p>
            </div>

            {/* Passed */}
            <div className="group relative rounded-2xl p-5 border border-emerald-500/10 bg-emerald-500/[0.03] hover:border-emerald-500/25 hover:bg-emerald-500/[0.06] transition-all overflow-hidden">
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-emerald-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] text-white/30 uppercase tracking-widest font-semibold mb-1">Passed</p>
              <p className="text-3xl font-bold text-emerald-400">
                {dataStatus.status_summary?.passed?.toLocaleString() || 0}
              </p>
            </div>

            {/* Failed */}
            <div className="group relative rounded-2xl p-5 border border-red-500/10 bg-red-500/[0.03] hover:border-red-500/25 hover:bg-red-500/[0.06] transition-all overflow-hidden">
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-red-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] text-white/30 uppercase tracking-widest font-semibold mb-1">Failed</p>
              <p className="text-3xl font-bold text-red-400">
                {dataStatus.status_summary?.failed?.toLocaleString() || 0}
              </p>
            </div>

            {/* Pass Rate */}
            <div className="group relative rounded-2xl p-5 border border-cyan-500/10 bg-cyan-500/[0.03] hover:border-cyan-500/25 hover:bg-cyan-500/[0.06] transition-all overflow-hidden">
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-cyan-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] text-white/30 uppercase tracking-widest font-semibold mb-1">Pass Rate</p>
              <p className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
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

        {/* Chart Gallery - now at TOP */}
        <ChartGallery key={refreshGallery} />

        {/* Floating buttons: chart (higher) and chat (lower) */}
        <FloatingChart />
        <FloatingChat />
      </div>
    </div>
  );
}