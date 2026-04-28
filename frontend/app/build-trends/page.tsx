"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { TrendingUp, LayoutDashboard, LogOut, ChevronDown, BarChart3, AlertTriangle } from "lucide-react";
import BrandLogo from "@/components/BrandLogo";

const BuildTrendCharts = dynamic(() => import("@/components/BuildTrendCharts"), { 
  ssr: false,
  loading: () => <div className="h-96 flex items-center justify-center text-slate-500 dark:text-white/30">Loading charts...</div>
});

export default function BuildTrends() {
  const [builds, setBuilds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(5);

  useEffect(() => {
    const fetchBuilds = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/builds");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.builds && Array.isArray(data.builds)) {
          const sorted = [...data.builds].sort(
            (a, b) => new Date(a.ingested_at).getTime() - new Date(b.ingested_at).getTime()
          );
          setBuilds(sorted);
          if (sorted.length === 0) setError("No builds found.");
        } else {
          setError("Invalid data format.");
        }
      } catch (err: any) {
        console.error(err);
        setError(`Failed to load builds: ${err.message}`);
      } finally {
        setLoading(false);
      }
    };
    fetchBuilds();
  }, []);

  const displayedBuilds = limit < builds.length ? builds.slice(-limit) : builds;

  const chartData = displayedBuilds.map((b, index) => {
    const metrics = b.metrics || {};
    return {
      buildNumber: index + 1,
      label: `Build ${index + 1}`,
      passRate: Number(metrics.pass_rate) || 0,
      passed: Number(metrics.passed) || 0,
      failed: Number(metrics.failed) || 0,
      skipped: Number(metrics.skipped_tests) || 0,
      totalDuration: Number(metrics.total_duration_sec) || 0,
      avgDuration: Number(metrics.avg_duration_sec) || 0,
    };
  });

  const handleLogout = () => {
    localStorage.clear();
    window.location.href = "/";
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-slate-500 dark:text-white/30 text-xs uppercase tracking-widest">Loading build data</span>
        </div>
      </div>
    );
  }

  if (error || builds.length === 0) {
    return (
      <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-red-500/[0.08] border border-red-500/20 flex items-center justify-center">
            <AlertTriangle className="w-8 h-8 text-red-400" />
          </div>
          <p className="text-red-400 text-lg font-semibold mb-2">{error || "No builds found"}</p>
          <Link href="/dashboard" className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-sm font-medium shadow-[0_0_25px_rgba(0,240,255,0.2)] hover:shadow-[0_0_40px_rgba(0,240,255,0.35)] transition-all">
            <LayoutDashboard className="w-4 h-4" />
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      {/* ══════════ HEADER ══════════ */}
      <header className="bg-white/90 border-slate-200 shadow-[0_4px_30px_rgba(15,23,42,0.08)] dark:bg-black/80 dark:border-white/[0.06] dark:shadow-[0_4px_30px_rgba(0,0,0,0.5)] backdrop-blur-xl border-b sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 py-3.5 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <BrandLogo className="shadow-[0_0_20px_rgba(0,240,255,0.2)]" />
            <div>
              <h1 className="text-lg font-bold tracking-tight">
                <span className="text-cyan-400">Sentinel</span>{" "}
                <span className="text-slate-500 dark:text-white/60 font-normal">Dashboard</span>
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-cyan-600 dark:text-white/40 dark:hover:text-cyan-400 transition-colors">
              <LayoutDashboard className="w-3.5 h-3.5" />
              Dashboard
            </Link>
            <div className="flex items-center gap-1.5 text-xs text-cyan-400 font-semibold border-b border-cyan-500/40 pb-0.5">
              <TrendingUp className="w-3.5 h-3.5" />
              Build Trends
            </div>
            <button onClick={handleLogout} className="flex items-center gap-1.5 text-xs text-red-600/80 hover:text-red-700 hover:bg-red-100 dark:text-red-400/70 dark:hover:text-red-400 dark:hover:bg-red-500/[0.08] px-3 py-1.5 rounded-lg transition-all">
              <LogOut className="w-3.5 h-3.5" />
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* ══════════ MAIN ══════════ */}
      <main className="max-w-[1600px] mx-auto px-6 py-8">
        <div className="flex justify-between items-end mb-8 flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-5 h-5 text-cyan-400" />
              <span className="text-[10px] text-cyan-500 uppercase tracking-widest font-semibold">Analytics</span>
            </div>
            <h2 className="text-3xl font-bold">
              Build{" "}
              <span className="bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">Analytics</span>
            </h2>
            <p className="text-slate-500 dark:text-white/30 mt-1 text-sm">
              Loaded {builds.length} builds — showing {chartData.length}
            </p>
          </div>
          <div className="relative">
            <select
              className="appearance-none bg-white border border-slate-300 rounded-xl px-4 py-2 pr-10 text-sm text-slate-700 hover:border-cyan-500/30 focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20 transition-all cursor-pointer dark:bg-white/[0.03] dark:border-white/[0.08] dark:text-white/70 dark:hover:border-cyan-500/20 dark:focus:border-cyan-500/30"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              <option value={5}>Last 5 builds</option>
              <option value={10}>Last 10 builds</option>
              <option value={20}>Last 20 builds</option>
              <option value={builds.length}>All builds</option>
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-white/25 pointer-events-none" />
          </div>
        </div>

        {chartData.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-2xl border border-slate-200 text-slate-500 dark:bg-white/[0.02] dark:border-white/[0.06] dark:text-white/30">No data for this selection</div>
        ) : (
          <BuildTrendCharts chartData={chartData} />
        )}
      </main>
    </div>
  );
}