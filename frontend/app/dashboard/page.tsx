"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Wifi, WifiOff, Plus, ChevronRight } from "lucide-react";
import { NAV_ACTION } from "@/components/HeaderNav";
import ChartGallery from "@/components/ChartGallery";
import DashboardInsightBand from "@/components/DashboardInsights";
import IngestionSelector from "@/components/IngestionSelector";
import ProjectSelector from "@/components/ProjectSelector";
import RoleSelector from "@/components/RoleSelector";
import FloatingChat from "@/components/FloatingChat";
import FloatingChart from "@/components/FloatingChart";  // new
import AppHeader from "@/components/AppHeader";
import AddBuildWizard from "@/components/AddBuildWizard";
import TestExplorerDrawer, { type TestStatus } from "@/components/TestExplorerDrawer";
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
  onClick,
}: {
  label: string;
  value: string;
  tone?: keyof typeof TILE_TONES;
  hint?: string;
  /** Present on the tiles that drill down into a test list. The tile becomes
   *  a real button so it is reachable by keyboard, not just by mouse. */
  onClick?: () => void;
}) {
  const interactive = Boolean(onClick);
  return (
    <motion.div
      variants={statCardVariants}
      whileHover={{ y: -3 }}
      title={hint}
      onClick={onClick}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={`group relative rounded-xl border border-slate-200 bg-white px-4 py-3.5 transition-colors hover:border-cyan-500/25 dark:border-white/[0.06] dark:bg-white/[0.02] ${
        interactive
          ? "cursor-pointer outline-none focus-visible:border-cyan-500/50 focus-visible:ring-2 focus-visible:ring-cyan-500/25"
          : ""
      }`}
    >
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/35">
        {label}
      </p>
      <p className={`text-2xl font-bold leading-none tabular-nums ${TILE_TONES[tone]}`}>{value}</p>
      {interactive && (
        <ChevronRight className="absolute right-3 top-3 h-3.5 w-3.5 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100 dark:text-white/25" />
      )}
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
  // Which status tile the drill-down is showing, or null when it's closed.
  const [explorerStatus, setExplorerStatus] = useState<TestStatus | null>(null);
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

  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)] selection:bg-cyan-500/30 font-sans">
      <div className="pointer-events-none absolute inset-0 dashboard-mesh" />
      <div className="pointer-events-none absolute inset-0 dashboard-grid-overlay" />
      <div className="pointer-events-none absolute -top-24 left-[12%] h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="pointer-events-none absolute top-[30%] right-[6%] h-80 w-80 rounded-full bg-blue-500/10 blur-3xl motion-blob-slow" />
      <div className="pointer-events-none absolute bottom-[-80px] left-[28%] h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl motion-blob-fast" />

      {/* ══════════ HEADER ══════════
          Nav, account menu and chrome all live in <AppHeader/>; this page
          only supplies the context that is specific to it. The connection
          state is a bare dot rather than the "Connected" pill it used to be
          — it is ambient status, not a control, and the pill cost ~100px on
          a row that has to stay one line. */}
      <AppHeader
        label="Dashboard"
        controls={
          <>
            <IngestionSelector />
            <ProjectSelector />
            <RoleSelector />
            {canIngest && (
              <div className="relative shrink-0">
                <button onClick={() => setIsAddBuildOpen(true)} className={NAV_ACTION}>
                  <Plus className="w-3.5 h-3.5" />
                  New Build
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

            <span
              title={backendConnected ? "Connected to the Sentinel API" : "Cannot reach the Sentinel API"}
              className="flex shrink-0 items-center gap-1.5 px-1"
            >
              {backendConnected ? (
                <Wifi className="h-3.5 w-3.5 text-emerald-500" />
              ) : (
                <WifiOff className="h-3.5 w-3.5 animate-pulse text-red-500" />
              )}
              <span className="sr-only">{backendConnected ? "Connected" : "Offline"}</span>
            </span>
          </>
        }
      />

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
              hint="See which tests passed"
              onClick={isHeaderLoading ? undefined : () => setExplorerStatus("passed")}
            />
            <StatTile
              label="Failed"
              value={isHeaderLoading ? "..." : (dataStatus?.status_summary?.failed || 0).toLocaleString()}
              tone="bad"
              hint="See which tests failed, grouped by cause"
              onClick={isHeaderLoading ? undefined : () => setExplorerStatus("failed")}
            />
            <StatTile
              label="Skipped"
              value={isHeaderLoading ? "..." : (dataStatus?.status_summary?.skipped || 0).toLocaleString()}
              tone="warn"
              hint="See which tests were skipped"
              onClick={isHeaderLoading ? undefined : () => setExplorerStatus("skipped")}
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

        {/* Drill-down behind the Passed / Failed / Skipped tiles. */}
        <TestExplorerDrawer
          isOpen={explorerStatus !== null}
          status={explorerStatus || "failed"}
          onStatusChange={setExplorerStatus}
          onClose={() => setExplorerStatus(null)}
          ingestionId={selectedIngestion || ""}
        />

        {/* Floating buttons: chart (higher) and chat (lower) */}
        <FloatingChart />
        <FloatingChat />
      </div>
    </div>
  );
}