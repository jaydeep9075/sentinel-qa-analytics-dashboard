"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  TrendingUp,
  LayoutDashboard,
  LogOut,
  ChevronDown,
  BarChart3,
  AlertTriangle,
  Radio,
  UserCog,
} from "lucide-react";
import BrandHeading from "@/components/BrandHeading";
import { NavLink, NAV_DANGER } from "@/components/HeaderNav";

const BuildTrendCharts = dynamic(() => import("@/components/BuildTrendCharts"), { 
  ssr: false,
  loading: () => <div className="h-96 flex items-center justify-center text-slate-500 dark:text-white/30">Loading charts...</div>
});

interface BuildMetrics {
  pass_rate?: number;
  passed?: number;
  failed?: number;
  skipped_tests?: number;
  total_duration_sec?: number;
  avg_duration_sec?: number;
}

interface BuildSummary {
  ingested_at?: string;
  metrics?: BuildMetrics;
}

export default function BuildTrends() {
  const [builds, setBuilds] = useState<BuildSummary[]>([]);
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
          const buildRows = data.builds as BuildSummary[];
          const sorted = [...buildRows].sort(
            (a, b) =>
              new Date(a.ingested_at || "1970-01-01T00:00:00Z").getTime() -
              new Date(b.ingested_at || "1970-01-01T00:00:00Z").getTime()
          );
          setBuilds(sorted);
          if (sorted.length === 0) setError("No builds found.");
        } else {
          setError("Invalid data format.");
        }
      } catch (err: unknown) {
        console.error(err);
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(`Failed to load builds: ${message}`);
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

  const avgPassRate = chartData.length
    ? chartData.reduce((sum, b) => sum + b.passRate, 0) / chartData.length
    : 0;
  const bestBuild = chartData.length
    ? chartData.reduce((best, cur) => (cur.passRate > best.passRate ? cur : best), chartData[0])
    : null;
  const worstBuild = chartData.length
    ? chartData.reduce((worst, cur) => (cur.passRate < worst.passRate ? cur : worst), chartData[0])
    : null;
  const volatility = chartData.length
    ? Math.sqrt(
        chartData.reduce((acc, b) => acc + Math.pow(b.passRate - avgPassRate, 2), 0) / chartData.length,
      )
    : 0;
  const durationTrendDelta = chartData.length >= 2
    ? chartData[chartData.length - 1].avgDuration - chartData[0].avgDuration
    : 0;
  const failLoad = chartData.length
    ? chartData.reduce((sum, b) => sum + b.failed, 0) / chartData.length
    : 0;

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
        <div className="max-w-[1600px] mx-auto px-6 py-3.5 flex flex-wrap justify-between items-center gap-4">
          {/* This header used to label itself "Sentinel Dashboard" while
              rendering the trends page, and hand-rolled the mark instead of
              using BrandHeading. */}
          <BrandHeading label="Build Trends" />
          <nav className="flex items-center gap-1">
            <NavLink href="/dashboard" icon={LayoutDashboard} label="Dashboard" />
            <NavLink href="/runs/live" icon={Radio} label="Live Runs" />
            <NavLink href="/build-trends" icon={TrendingUp} label="Build Trends" active />
            <NavLink href="/account" icon={UserCog} label="Account" />
            <button onClick={handleLogout} className={NAV_DANGER}>
              <LogOut className="w-3.5 h-3.5" />
              Logout
            </button>
          </nav>
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

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
          <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.05] p-4">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/35">Average Pass Rate</p>
            <p className="text-2xl font-bold text-cyan-500 dark:text-cyan-300">{avgPassRate.toFixed(1)}%</p>
          </div>
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.05] p-4">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/35">Best Build</p>
            <p className="text-lg font-semibold text-emerald-600 dark:text-emerald-300">{bestBuild?.label || "-"}</p>
            <p className="text-sm text-slate-600 dark:text-white/55">{bestBuild ? `${bestBuild.passRate.toFixed(1)}%` : "-"}</p>
          </div>
          <div className="rounded-2xl border border-red-500/20 bg-red-500/[0.05] p-4">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/35">Worst Build</p>
            <p className="text-lg font-semibold text-red-600 dark:text-red-300">{worstBuild?.label || "-"}</p>
            <p className="text-sm text-slate-600 dark:text-white/55">{worstBuild ? `${worstBuild.passRate.toFixed(1)}%` : "-"}</p>
          </div>
          <div className="rounded-2xl border border-violet-500/20 bg-violet-500/[0.05] p-4">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/35">Pass-Rate Volatility</p>
            <p className="text-2xl font-bold text-violet-600 dark:text-violet-300">{volatility.toFixed(2)}</p>
          </div>
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.05] p-4">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/35">Avg Fail Load / Duration Delta</p>
            <p className="text-sm text-slate-700 dark:text-white/70">Failed: {failLoad.toFixed(1)} tests/build</p>
            <p className="text-sm text-slate-700 dark:text-white/70">Avg duration Δ: {durationTrendDelta >= 0 ? "+" : ""}{durationTrendDelta.toFixed(2)}s</p>
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