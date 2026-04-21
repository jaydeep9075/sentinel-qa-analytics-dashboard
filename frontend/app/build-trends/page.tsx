"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";

const BuildTrendCharts = dynamic(() => import("@/components/BuildTrendCharts"), { 
  ssr: false,
  loading: () => <div className="h-96 flex items-center justify-center text-gray-500">Loading charts...</div>
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
        const res = await fetch("/builds.json");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.builds && Array.isArray(data.builds)) {
          // Sort builds from oldest to newest (by ingested_at)
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

  // Limit to last N builds (most recent N if limit is less than total)
  const displayedBuilds = limit < builds.length ? builds.slice(-limit) : builds;

  // Build chart data with sequential labels "Build 1", "Build 2", ...
  const chartData = displayedBuilds.map((b, index) => {
    const metrics = b.metrics || {};
    return {
      buildNumber: index + 1,
      label: `Build ${index + 1}`,
      passRate: Number(metrics.pass_rate) || 0,
      passed: Number(metrics.passed) || 0,
      failed: Number(metrics.failed) || 0,
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
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-gray-900 to-black text-white flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error || builds.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-gray-900 to-black text-white flex items-center justify-center">
        <div className="text-center">
          <div className="text-5xl mb-4">📊</div>
          <p className="text-red-400 text-xl font-semibold">{error || "No builds found"}</p>
          <Link href="/dashboard" className="mt-4 inline-block px-4 py-2 bg-blue-600 rounded-lg">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-gray-900 to-black text-white">
      <header className="bg-white/[0.02] backdrop-blur-xl border-b border-white/10 sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-tr from-blue-500 to-purple-500 rounded-xl flex items-center justify-center font-bold">S</div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              Sentinel Dashboard
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-sm text-gray-300 hover:text-blue-400">Dashboard</Link>
            <Link href="/build-trends" className="text-sm text-blue-400 font-bold border-b border-blue-400 pb-1">Build Trends</Link>
            <button onClick={handleLogout} className="text-sm text-red-400 hover:text-red-300">Logout</button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-8">
        <div className="flex justify-between items-end mb-6 flex-wrap gap-4">
          <div>
            <h2 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              Build Analytics
            </h2>
            <p className="text-gray-400 mt-1">Loaded {builds.length} builds — showing {chartData.length}</p>
          </div>
          <div className="flex gap-3">
            <select
              className="bg-black/50 border border-white/20 rounded px-3 py-1.5 text-sm"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              <option value={5}>Last 5 builds</option>
              <option value={10}>Last 10 builds</option>
              <option value={20}>Last 20 builds</option>
              <option value={builds.length}>All builds</option>
            </select>
          </div>
        </div>

        {chartData.length === 0 ? (
          <div className="text-center py-12 bg-white/5 rounded-2xl">No data for this selection</div>
        ) : (
          <BuildTrendCharts chartData={chartData} />
        )}
      </main>
    </div>
  );
}