"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Plug, Radio, LayoutDashboard, TrendingUp } from "lucide-react";
import BrandHeading from "@/components/BrandHeading";
import { NavLink } from "@/components/HeaderNav";
import ConnectRepoPanel, { ConnectionInfo } from "@/components/ConnectRepoPanel";
import {
  API_BASE,
  RunSummary,
  STATUS_STYLES,
  authHeaders,
  elapsedMs,
  formatDuration,
} from "@/lib/liveRuns";

/** Counts the backend already aggregated per run (store.list_runs). Rendering
 * them in the row is what turns this page into something you can leave open
 * on a second screen during a release - the previous version showed only a
 * status pill, so "is anything red?" meant opening every run in turn. */
function ResultPills({ run }: { run: RunSummary }) {
  const parts: { label: string; value: number; className: string }[] = [
    { label: "passed", value: run.passed_count ?? 0, className: "text-emerald-500 dark:text-emerald-400" },
    { label: "failed", value: run.failed_count ?? 0, className: "text-red-500 dark:text-red-400" },
    { label: "skipped", value: run.skipped_count ?? 0, className: "text-slate-400 dark:text-white/35" },
  ].filter((p) => p.value > 0);
  if (parts.length === 0) return null;
  return (
    <span className="flex shrink-0 items-center gap-2 text-xs font-semibold tabular-nums">
      {parts.map((p) => (
        <span key={p.label} className={p.className} title={`${p.value} ${p.label}`}>
          {p.value} {p.label}
        </span>
      ))}
    </span>
  );
}

export default function LiveRunsListPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [connection, setConnection] = useState<ConnectionInfo | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  // Durations tick without needing a new poll response, so a run's elapsed
  // time advances smoothly instead of jumping every 2s.
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // 403 here just means "not an admin", which is the common case and not an
  // error worth surfacing - the panel simply doesn't appear for them.
  useEffect(() => {
    fetch(`${API_BASE}/live/connection-info`, { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setConnection(data))
      .catch(() => setConnection(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/live/runs?limit=50`, { headers: authHeaders() });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setRuns(data);
      } catch {
        // Backend not reachable yet - keep showing the last known list.
      }
    };
    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 2000);
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)] selection:bg-cyan-500/30 font-sans">
      <div className="pointer-events-none absolute inset-0 dashboard-mesh" />
      <div className="pointer-events-none absolute inset-0 dashboard-grid-overlay" />
      <div className="pointer-events-none absolute -top-24 left-[12%] h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="pointer-events-none absolute top-[30%] right-[6%] h-80 w-80 rounded-full bg-blue-500/10 blur-3xl motion-blob-slow" />
      <div className="pointer-events-none absolute bottom-[-80px] left-[28%] h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl motion-blob-fast" />

      <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/90 shadow-[0_4px_30px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/[0.06] dark:bg-black/80 dark:shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:gap-4 sm:px-6 sm:py-3.5">
          <BrandHeading label="Live Runs" />
          <nav className="flex items-center gap-1">
            <NavLink href="/dashboard" icon={LayoutDashboard} label="Dashboard" />
            <NavLink href="/runs/live" icon={Radio} label="Live Runs" active />
            <NavLink href="/build-trends" icon={TrendingUp} label="Build Trends" />
          </nav>
        </div>
      </header>

      <div className="relative z-10 mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Radio className="h-5 w-5 text-emerald-400" />
            <h2 className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-2xl font-bold text-transparent">
              Live Runs
            </h2>
          </div>
          {connection && (
            <button
              type="button"
              onClick={() => setShowSetup((v) => !v)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition-all hover:bg-slate-200 dark:border-white/[0.1] dark:bg-white/[0.05] dark:text-white/75 dark:hover:bg-white/[0.1]"
            >
              <Plug className="h-3.5 w-3.5" /> Connect a repo
            </button>
          )}
        </div>

        {connection && showSetup && (
          <ConnectRepoPanel
            info={connection}
            onRotated={(api_key) => setConnection({ ...connection, api_key })}
          />
        )}

        {runs.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 p-6 text-sm text-slate-500 dark:border-white/[0.12] dark:bg-black/20 dark:text-white/40">
            Nothing running right now. Start a test run with Sentinel reporting enabled — Playwright,
            Cypress, or any other framework — and it will appear here within a couple of seconds.
            {connection && (
              <>
                {" "}
                <button
                  type="button"
                  onClick={() => setShowSetup(true)}
                  className="font-semibold text-cyan-500 underline-offset-2 hover:underline dark:text-cyan-400"
                >
                  Show me how to connect a repo
                </button>
                .
              </>
            )}
          </div>
        )}

        <div className="space-y-2">
          {runs.map((r) => {
            const ms = elapsedMs(r, now);
            const done = (r.passed_count ?? 0) + (r.failed_count ?? 0) + (r.skipped_count ?? 0);
            return (
              <Link
                key={r.run_id}
                href={`/runs/${r.run_id}/live`}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/90 px-4 py-3.5 text-sm shadow-[0_4px_20px_rgba(15,23,42,0.06)] transition-all hover:border-cyan-500/30 hover:shadow-[0_4px_20px_rgba(0,240,255,0.1)] dark:border-white/[0.08] dark:bg-black/40 dark:shadow-[0_4px_20px_rgba(0,0,0,0.35)]"
              >
                <div className="min-w-0">
                  <div className="truncate font-semibold text-slate-800 dark:text-white/90">
                    {r.name || r.run_id}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-500 dark:text-white/35">
                    {r.framework || "unknown framework"}
                    {r.environment ? ` · ${r.environment}` : ""}
                    {r.branch ? ` · ${r.branch}` : ""}
                    {r.ci_provider ? ` · ${r.ci_provider}` : " · local"}
                    {ms !== null ? ` · ${formatDuration(ms)}` : ""}
                    {r.total_tests ? ` · ${done}/${r.total_tests} tests` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <ResultPills run={r} />
                  <span
                    className={`flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize ${
                      STATUS_STYLES[r.status] || STATUS_STYLES.skipped
                    }`}
                  >
                    {r.status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
                    {r.status}
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
