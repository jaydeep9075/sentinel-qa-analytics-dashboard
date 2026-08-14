"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { TrendingUp, LogOut, Wifi, WifiOff, Plus, Radio, Shield, UserCog } from "lucide-react";
import ChartGallery from "@/components/ChartGallery";
import IngestionSelector from "@/components/IngestionSelector";
import ProjectSelector from "@/components/ProjectSelector";
import RoleSelector from "@/components/RoleSelector";
import FloatingChat from "@/components/FloatingChat";
import FloatingChart from "@/components/FloatingChart";  // new
import BrandLogo from "@/components/BrandLogo";
import AddBuildWizard from "@/components/AddBuildWizard";
import { getDashboardOverview, readCachedDashboardOverview } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import { usePermissions } from "@/lib/usePermissions";

const statGridVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

const statCardVariants = {
  hidden: { opacity: 0, y: 18, scale: 0.97 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 300, damping: 26 },
  },
};

export default function Dashboard() {
  const router = useRouter();
  const { selectedIngestion, setSelectedIngestion } = useIngestion();
  const { has: hasPermission } = usePermissions();
  const canIngest = hasPermission("data.ingest");
  const [dataStatus, setDataStatus] = useState<{
    has_data?: boolean;
    total_rows?: number;
    status_summary?: {
      passed?: number;
      failed?: number;
      skipped?: number;
    };
  } | null>(null);
  const [backendConnected, setBackendConnected] = useState(false);
  const [refreshGallery, setRefreshGallery] = useState(0);
  const [isAddBuildOpen, setIsAddBuildOpen] = useState(false);
  const [dataQuality, setDataQuality] = useState<{
    score?: number;
    quality?: string;
    guidance?: string[];
    checks?: { name?: string; passed?: boolean; detail?: string }[];
  } | null>(null);
  const [isHeaderLoading, setIsHeaderLoading] = useState(true);
  const headerLoadStartRef = useRef<number>(0);

  // Listen for chart-generated events from FloatingChart
  useEffect(() => {
    const handleChartGenerated = () => {
      setRefreshGallery(prev => prev + 1);
    };
    window.addEventListener("chart-generated", handleChartGenerated);
    return () => window.removeEventListener("chart-generated", handleChartGenerated);
  }, []);

  useEffect(() => {
    let cancelled = false;
    headerLoadStartRef.current =
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? performance.now()
        : Date.now();
    setIsHeaderLoading(true);

    const applyOverview = (overview: {
      connected?: boolean;
      status?: {
        has_data?: boolean;
        total_rows?: number;
        status_summary?: { passed?: number; failed?: number; skipped?: number };
      };
      quality?: {
        score?: number;
        quality?: string;
        guidance?: string[];
        checks?: { name?: string; passed?: boolean; detail?: string }[];
      };
    }) => {
      if (cancelled) return;
      setBackendConnected(Boolean(overview.connected));
      if (overview.status) setDataStatus(overview.status);
      if (overview.quality) setDataQuality(overview.quality);
      setIsHeaderLoading(false);
    };

    const cached = selectedIngestion ? readCachedDashboardOverview(selectedIngestion) : null;
    if (cached) {
      applyOverview(cached);
    }

    const refreshOverview = async () => {
      if (!selectedIngestion) {
        if (!cancelled) {
          setDataStatus(null);
          setDataQuality(null);
          setBackendConnected(true);
          setIsHeaderLoading(false);
        }
        return;
      }

      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;

      try {
        // Quality is computed from already-in-memory DuckDB aggregates (no LLM,
        // no disk I/O) — same cost class as status — so fetching both in one
        // call removes two redundant round trips (a separate /data/quality
        // prefetch plus a second /dashboard/overview call) with no first-paint
        // cost.
        const overview = await getDashboardOverview(selectedIngestion, {
          forceRefresh: true,
          includeQuality: true,
        });
        applyOverview(overview);
      } catch {
        if (!cancelled) setBackendConnected(false);
      }
    };

    refreshOverview();

    const interval = setInterval(refreshOverview, 20000);
    const onVisible = () => {
      if (document.visibilityState === "visible") refreshOverview();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [selectedIngestion]);

  useEffect(() => {
    if (isHeaderLoading) return;
    if (typeof window === "undefined") return;
    const enabled = process.env.NODE_ENV !== "production" || localStorage.getItem("qa_perf_debug") === "1";
    if (!enabled) return;
    const now =
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? performance.now()
        : Date.now();
    console.debug("[perf] dashboard:header-ready", {
      ingestion: selectedIngestion,
      ready_ms: Number((now - headerLoadStartRef.current).toFixed(1)),
    });
  }, [isHeaderLoading, selectedIngestion]);

  // Only gates whether the nav link is rendered — /admin/* is enforced by
  // require_admin on the backend, so hiding it is convenience, not security.
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    const role = (localStorage.getItem("role") || "").toLowerCase();
    setIsAdmin(role === "admin" || role === "cto");
  }, []);

  // A must-change-password session can't reach anything else on the backend
  // (see credential_change_middleware) - every panel on this page would 403
  // and render as a broken dashboard instead of explaining why. Checked here
  // rather than only relying on login's redirect so a stale token that still
  // has the flag (e.g. an admin-issued reset) gets caught on a page reload
  // too, not just at the moment of signing in.
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((me) => {
        if (me?.must_change_password) {
          // router.push, not window.location.href: this is a same-app
          // redirect, and a hard navigation would blank the page to white
          // for a frame before the browser re-requests and re-parses
          // everything Next.js already has loaded. The account page and its
          // "forced" banner mount instantly instead.
          router.push("/account?forced=1");
        }
      })
      .catch(() => {});
  }, [router]);

  const handleLogout = () => {
    localStorage.clear();
    window.location.href = "/";
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)] selection:bg-cyan-500/30 font-sans">
      <div className="pointer-events-none absolute inset-0 dashboard-mesh" />
      <div className="pointer-events-none absolute inset-0 dashboard-grid-overlay" />
      <div className="pointer-events-none absolute -top-24 left-[12%] h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="pointer-events-none absolute top-[30%] right-[6%] h-80 w-80 rounded-full bg-blue-500/10 blur-3xl motion-blob-slow" />
      <div className="pointer-events-none absolute bottom-[-80px] left-[28%] h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl motion-blob-fast" />

      {/* ══════════ HEADER ══════════ */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="bg-white/90 border-slate-200 shadow-[0_4px_30px_rgba(15,23,42,0.08)] dark:bg-black/80 dark:border-white/[0.06] dark:shadow-[0_4px_30px_rgba(0,0,0,0.5)] backdrop-blur-xl border-b sticky top-0 z-50"
      >
        <div className="max-w-[1600px] mx-auto px-6 py-3.5 flex flex-col md:flex-row justify-between items-center gap-4">
          {/* left: logo */}
          <div className="flex items-center gap-3">
            <BrandLogo className="shadow-[0_0_20px_rgba(0,240,255,0.2)]" />
            <div>
              <h1 className="text-lg font-bold tracking-tight">
                <span className="text-cyan-400">Sentinel</span>{" "}
                <span className="font-normal text-slate-500 dark:text-white/60">Dashboard</span>
              </h1>
              <p className="text-[10px] uppercase tracking-widest font-semibold text-slate-500 dark:text-white/25">QA Intelligence Platform</p>
            </div>
          </div>

          {/* right: selectors + status + actions */}
          <div className="flex items-center gap-3 flex-wrap justify-end">
            <IngestionSelector />
            <ProjectSelector />
            <RoleSelector />
            {canIngest && (
            <div className="relative">
              <button
                onClick={() => setIsAddBuildOpen(true)}
                className="flex items-center gap-1.5 text-xs text-slate-700 dark:text-white/75 font-semibold border border-slate-300 dark:border-white/[0.1] px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.05] dark:hover:bg-white/[0.1] transition-all active:scale-95"
              >
                <Plus className="w-3.5 h-3.5" />
                Add New Build
              </button>

              <AddBuildWizard
                isOpen={isAddBuildOpen}
                onClose={() => setIsAddBuildOpen(false)}
                onSuccess={(id) => {
                  setSelectedIngestion(id);
                  setRefreshGallery((prev) => prev + 1);
                }}
              />
            </div>
            )}

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

            {/* live runs link */}
            <Link
              href="/runs/live"
              className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 font-semibold border border-emerald-500/20 px-3 py-1.5 rounded-lg bg-emerald-500/[0.06] hover:bg-emerald-500/[0.12] hover:border-emerald-500/30 hover:shadow-[0_0_15px_rgba(16,240,150,0.08)] hover:-translate-y-0.5 active:scale-95 transition-all"
            >
              <Radio className="w-3.5 h-3.5" />
              Live Runs
            </Link>

            {/* build trends link */}
            <Link
              href="/build-trends"
              className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 font-semibold border border-cyan-500/20 px-3 py-1.5 rounded-lg bg-cyan-500/[0.06] hover:bg-cyan-500/[0.12] hover:border-cyan-500/30 hover:shadow-[0_0_15px_rgba(0,240,255,0.08)] hover:-translate-y-0.5 active:scale-95 transition-all"
            >
              <TrendingUp className="w-3.5 h-3.5" />
              Build Trends
            </Link>

            {/* admin console — admins only */}
            {isAdmin && (
              <Link
                href="/admin"
                className="flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 font-semibold border border-purple-500/20 px-3 py-1.5 rounded-lg bg-purple-500/[0.06] hover:bg-purple-500/[0.12] hover:border-purple-500/30 hover:-translate-y-0.5 active:scale-95 transition-all"
              >
                <Shield className="w-3.5 h-3.5" />
                Admin
              </Link>
            )}

            {/* account settings — everyone */}
            <Link
              href="/account"
              className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-white/60 hover:text-cyan-500 font-semibold border border-slate-300 dark:border-white/[0.1] px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.05] dark:hover:bg-white/[0.1] hover:-translate-y-0.5 active:scale-95 transition-all"
            >
              <UserCog className="w-3.5 h-3.5" />
              Account
            </Link>

            {/* logout */}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all active:scale-95 text-red-600/80 hover:text-red-700 hover:bg-red-100 dark:text-red-400/70 dark:hover:text-red-400 dark:hover:bg-red-500/[0.08]"
            >
              <LogOut className="w-3.5 h-3.5" />
              Logout
            </button>
          </div>
        </div>
      </motion.header>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <div className="relative z-10 max-w-[1600px] mx-auto px-6 py-8">
        {/* Data Summary Cards */}
        {(dataStatus?.has_data && dataStatus.total_rows) || isHeaderLoading ? (
          <motion.div
            variants={statGridVariants}
            initial="hidden"
            animate="visible"
            className="grid grid-cols-1 md:grid-cols-6 gap-4 mb-4"
          >
            {/* Total Tests */}
            <motion.div
              variants={statCardVariants}
              whileHover={{ y: -6 }}
              className="group relative rounded-2xl p-5 border border-slate-200 bg-white hover:border-cyan-500/20 hover:bg-cyan-500/[0.03] hover:shadow-[0_16px_35px_rgba(6,182,212,0.1)] transition-all overflow-hidden dark:border-white/[0.06] dark:bg-white/[0.02] dark:hover:shadow-[0_16px_35px_rgba(0,0,0,0.5)]"
            >
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-cyan-500/[0.06] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] uppercase tracking-widest font-semibold mb-1 text-slate-500 dark:text-white/30">Total Tests</p>
              <p className="text-3xl font-bold transition-colors text-slate-900 group-hover:text-cyan-600 dark:text-white dark:group-hover:text-cyan-400">
                {isHeaderLoading ? "..." : (dataStatus?.total_rows || 0).toLocaleString()}
              </p>
            </motion.div>

            {/* Passed */}
            <motion.div
              variants={statCardVariants}
              whileHover={{ y: -6 }}
              className="group relative rounded-2xl p-5 border border-emerald-500/10 bg-emerald-500/[0.03] hover:border-emerald-500/25 hover:bg-emerald-500/[0.06] hover:shadow-[0_16px_35px_rgba(16,185,129,0.12)] transition-all overflow-hidden"
            >
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-emerald-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] uppercase tracking-widest font-semibold mb-1 text-slate-500 dark:text-white/30">Passed</p>
              <p className="text-3xl font-bold text-emerald-400">
                {isHeaderLoading ? "..." : (dataStatus?.status_summary?.passed?.toLocaleString() || 0)}
              </p>
            </motion.div>

            {/* Failed */}
            <motion.div
              variants={statCardVariants}
              whileHover={{ y: -6 }}
              className="group relative rounded-2xl p-5 border border-red-500/10 bg-red-500/[0.03] hover:border-red-500/25 hover:bg-red-500/[0.06] hover:shadow-[0_16px_35px_rgba(239,68,68,0.12)] transition-all overflow-hidden"
            >
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-red-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] uppercase tracking-widest font-semibold mb-1 text-slate-500 dark:text-white/30">Failed</p>
              <p className="text-3xl font-bold text-red-400">
                {isHeaderLoading ? "..." : (dataStatus?.status_summary?.failed?.toLocaleString() || 0)}
              </p>
            </motion.div>

            {/* Pass Rate */}
            <motion.div
              variants={statCardVariants}
              whileHover={{ y: -6 }}
              className="group relative rounded-2xl p-5 border border-cyan-500/10 bg-cyan-500/[0.03] hover:border-cyan-500/25 hover:bg-cyan-500/[0.06] hover:shadow-[0_16px_35px_rgba(6,182,212,0.12)] transition-all overflow-hidden"
            >
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-cyan-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] uppercase tracking-widest font-semibold mb-1 text-slate-500 dark:text-white/30">Pass Rate</p>
              <p className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                {isHeaderLoading
                  ? "..."
                  : `${Math.round(
                      (((dataStatus?.status_summary?.passed || 0) / Math.max(1, dataStatus?.total_rows || 0)) * 100),
                    )}%`}
              </p>
            </motion.div>

            {/* Skipped */}
            <motion.div
              variants={statCardVariants}
              whileHover={{ y: -6 }}
              className="group relative rounded-2xl p-5 border border-amber-500/10 bg-amber-500/[0.03] hover:border-amber-500/25 hover:bg-amber-500/[0.06] hover:shadow-[0_16px_35px_rgba(245,158,11,0.12)] transition-all overflow-hidden"
            >
              <div className="absolute -top-12 -right-12 w-24 h-24 bg-amber-500/[0.08] blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              <p className="text-[10px] uppercase tracking-widest font-semibold mb-1 text-slate-500 dark:text-white/30">Skipped</p>
              <p className="text-3xl font-bold text-amber-500 dark:text-amber-400">
                {isHeaderLoading ? "..." : (dataStatus?.status_summary?.skipped?.toLocaleString() || 0)}
              </p>
            </motion.div>
          </motion.div>
        ) : null}

        {dataQuality && (
          <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/[0.06] dark:bg-white/[0.02]">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-widest font-semibold text-slate-500 dark:text-white/30">Ingestion Quality</p>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                  Score: {Math.max(0, Math.min(100, Number(dataQuality.score || 0)))} / 100
                  <span className="ml-2 text-sm font-normal text-slate-500 dark:text-white/45">({String(dataQuality.quality || "unknown").toUpperCase()})</span>
                </h3>
              </div>
              <div className="flex items-center gap-2">
                {(dataQuality.checks || []).slice(0, 3).map((c, idx) => (
                  <span
                    key={`${c.name}-${idx}`}
                    className={`text-[10px] px-2 py-1 rounded-full border ${
                      c.passed
                        ? "text-emerald-600 border-emerald-500/30 bg-emerald-500/[0.08] dark:text-emerald-300"
                        : "text-amber-700 border-amber-500/30 bg-amber-500/[0.08] dark:text-amber-300"
                    }`}
                    title={c.detail || c.name || ""}
                  >
                    {c.passed ? "PASS" : "CHECK"} {c.name || "rule"}
                  </span>
                ))}
              </div>
            </div>
            {(dataQuality.guidance || []).length > 0 && (
              <p className="mt-3 text-xs text-slate-600 dark:text-white/55">
                {(dataQuality.guidance || []).slice(0, 2).join("  |  ")}
              </p>
            )}
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