"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  TrendingUp,
  LogOut,
  Wifi,
  WifiOff,
  Plus,
  Radio,
  Shield,
  UserCog,
  LayoutDashboard,
} from "lucide-react";
import { NavLink, NAV_ACTION, NAV_DANGER } from "@/components/HeaderNav";
import ChartGallery from "@/components/ChartGallery";
import DashboardInsightBand from "@/components/DashboardInsights";
import IngestionSelector from "@/components/IngestionSelector";
import ProjectSelector from "@/components/ProjectSelector";
import RoleSelector from "@/components/RoleSelector";
import FloatingChat from "@/components/FloatingChat";
import FloatingChart from "@/components/FloatingChart";  // new
import BrandHeading from "@/components/BrandHeading";
import AddBuildWizard from "@/components/AddBuildWizard";
import {
  getDashboardOverview,
  readCachedDashboardOverview,
  type DashboardInsights,
} from "@/lib/api";
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

/** One KPI tile. Colour is carried by the number alone — the card chrome
 *  stays neutral, so a row of six reads as one instrument panel rather than
 *  six competing badges. */
const TILE_TONES = {
  neutral: "text-slate-900 dark:text-white",
  good: "text-emerald-600 dark:text-emerald-400",
  bad: "text-red-600 dark:text-red-400",
  warn: "text-amber-600 dark:text-amber-400",
  accent: "text-cyan-600 dark:text-cyan-400",
} as const;

function StatTile({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string;
  tone?: keyof typeof TILE_TONES;
  hint?: string;
}) {
  return (
    <motion.div
      variants={statCardVariants}
      whileHover={{ y: -3 }}
      title={hint}
      className="rounded-xl border border-slate-200 bg-white px-4 py-3.5 transition-colors hover:border-cyan-500/25 dark:border-white/[0.06] dark:bg-white/[0.02]"
    >
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/35">
        {label}
      </p>
      <p className={`text-2xl font-bold leading-none tabular-nums ${TILE_TONES[tone]}`}>{value}</p>
    </motion.div>
  );
}

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
  const [isAddBuildOpen, setIsAddBuildOpen] = useState(false);
  const [dataQuality, setDataQuality] = useState<{
    score?: number;
    quality?: string;
    guidance?: string[];
    checks?: { name?: string; passed?: boolean; detail?: string }[];
  } | null>(null);
  const [insights, setInsights] = useState<DashboardInsights | null>(null);
  const [isHeaderLoading, setIsHeaderLoading] = useState(true);
  const headerLoadStartRef = useRef<number>(0);

  // `chart-generated` is handled inside ChartGallery, which inserts the new
  // figure into its own list. This page used to answer the same event by
  // bumping a `key` on <ChartGallery/> — remounting it wholesale, which threw
  // away every already-drawn Plotly instance and rebuilt the entire gallery
  // from scratch. That teardown-and-redraw was the multi-second gap between
  // "generating" disappearing and charts reappearing.

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
      insights?: DashboardInsights;
    }) => {
      if (cancelled) return;
      setBackendConnected(Boolean(overview.connected));
      if (overview.status) setDataStatus(overview.status);
      if (overview.quality) setDataQuality(overview.quality);
      if (overview.insights) setInsights(overview.insights);
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
          setInsights(null);
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
          <BrandHeading label="Dashboard" />

          {/* right: selectors + status + actions */}
          <div className="flex items-center gap-3 flex-wrap justify-end">
            <IngestionSelector />
            <ProjectSelector />
            <RoleSelector />
            {canIngest && (
            <div className="relative">
              <button onClick={() => setIsAddBuildOpen(true)} className={NAV_ACTION}>
                <Plus className="w-3.5 h-3.5" />
                Add New Build
              </button>

              <AddBuildWizard
                isOpen={isAddBuildOpen}
                onClose={() => setIsAddBuildOpen(false)}
                // Switching the build already changes the gallery's SWR key,
                // which refetches it — no remount needed on top of that.
                onSuccess={(id) => setSelectedIngestion(id)}
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

            {/* Nav proper. One shared style — the page you are on is the
                only item that takes the brand accent. */}
            <nav className="flex items-center gap-1">
              <NavLink href="/dashboard" icon={LayoutDashboard} label="Dashboard" active />
              <NavLink href="/runs/live" icon={Radio} label="Live Runs" />
              <NavLink href="/build-trends" icon={TrendingUp} label="Build Trends" />
              {isAdmin && <NavLink href="/admin" icon={Shield} label="Admin" />}
              <NavLink href="/account" icon={UserCog} label="Account" />
              <button onClick={handleLogout} className={NAV_DANGER}>
                <LogOut className="w-3.5 h-3.5" />
                Logout
              </button>
            </nav>
          </div>
        </div>
      </motion.header>

      {/* ══════════ MAIN CONTENT ══════════ */}
      <div className="relative z-10 max-w-[1600px] mx-auto px-6 py-8">
        {/* ── KPI strip ───────────────────────────────────────────────
            Six equal tiles, one row. Data quality now lives here as a bare
            percentage alongside the other counts, instead of the full-width
            panel it used to own — it is a health indicator, not the headline
            of the page. */}
        {(dataStatus?.has_data && dataStatus.total_rows) || isHeaderLoading ? (
          <motion.div
            variants={statGridVariants}
            initial="hidden"
            animate="visible"
            className="grid grid-cols-2 gap-3 mb-4 md:grid-cols-3 xl:grid-cols-6"
          >
            <StatTile
              label="Total Tests"
              value={isHeaderLoading ? "..." : (dataStatus?.total_rows || 0).toLocaleString()}
              tone="neutral"
            />
            <StatTile
              label="Passed"
              value={isHeaderLoading ? "..." : (dataStatus?.status_summary?.passed || 0).toLocaleString()}
              tone="good"
            />
            <StatTile
              label="Failed"
              value={isHeaderLoading ? "..." : (dataStatus?.status_summary?.failed || 0).toLocaleString()}
              tone="bad"
            />
            <StatTile
              label="Skipped"
              value={isHeaderLoading ? "..." : (dataStatus?.status_summary?.skipped || 0).toLocaleString()}
              tone="warn"
            />
            <StatTile
              label="Pass Rate"
              value={
                isHeaderLoading
                  ? "..."
                  : `${Math.round(
                      ((dataStatus?.status_summary?.passed || 0) /
                        Math.max(1, dataStatus?.total_rows || 0)) *
                        100,
                    )}%`
              }
              tone="accent"
            />
            <StatTile
              label="Data Quality"
              value={
                isHeaderLoading
                  ? "..."
                  : `${Math.max(0, Math.min(100, Math.round(Number(dataQuality?.score || 0))))}%`
              }
              tone="accent"
              hint={
                (dataQuality?.guidance || []).slice(0, 2).join("  |  ") ||
                "Completeness and shape of this build's ingested data"
              }
            />
          </motion.div>
        ) : null}

        {/* ── Business band ───────────────────────────────────────────── */}
        <DashboardInsightBand
          insights={insights}
          qualityScore={dataQuality?.score}
          loading={isHeaderLoading && !insights}
        />

        {/* Chart Gallery - now at TOP */}
        <ChartGallery />

        {/* Floating buttons: chart (higher) and chat (lower) */}
        <FloatingChart />
        <FloatingChat />
      </div>
    </div>
  );
}