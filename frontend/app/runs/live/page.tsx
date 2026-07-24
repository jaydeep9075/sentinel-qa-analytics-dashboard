"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Radio } from "lucide-react";
import BrandLogo from "@/components/BrandLogo";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RunSummary {
  run_id: string;
  name?: string;
  status: string;
  framework?: string;
  ci_provider?: string;
  branch?: string;
  started_at?: string;
}

const STATUS_STYLES: Record<string, string> = {
  running: "bg-blue-500/10 text-blue-400 border-blue-500/25",
  passed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  failed: "bg-red-500/10 text-red-400 border-red-500/25",
  skipped: "bg-slate-500/10 text-slate-400 border-slate-500/25",
  cancelled: "bg-slate-500/10 text-slate-400 border-slate-500/25",
};

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function LiveRunsListPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);

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
    const interval = setInterval(load, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
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
          <div className="flex items-center gap-3">
            <BrandLogo className="shadow-[0_0_20px_rgba(0,240,255,0.2)]" />
            <div>
              <h1 className="text-base font-bold tracking-tight sm:text-lg">
                <span className="text-cyan-400">Sentinel</span>{" "}
                <span className="font-normal text-slate-500 dark:text-white/60">Live Runs</span>
              </h1>
              <p className="hidden text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/25 sm:block">
                QA Intelligence Platform
              </p>
            </div>
          </div>
          <Link
            href="/dashboard"
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition-all hover:bg-slate-200 dark:border-white/[0.1] dark:bg-white/[0.05] dark:text-white/75 dark:hover:bg-white/[0.1]"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Dashboard
          </Link>
        </div>
      </header>

      <div className="relative z-10 mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-6 flex items-center gap-2">
          <Radio className="h-5 w-5 text-emerald-400" />
          <h2 className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-2xl font-bold text-transparent">
            Live Runs
          </h2>
        </div>

        {runs.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 p-6 text-sm text-slate-500 dark:border-white/[0.12] dark:bg-black/20 dark:text-white/40">
            Nothing running right now. Start <code className="rounded bg-slate-200 px-1 py-0.5 text-xs dark:bg-white/10">playwright test</code> with the{" "}
            <code className="rounded bg-slate-200 px-1 py-0.5 text-xs dark:bg-white/10">@sentinel/playwright</code> reporter configured to see it appear here.
          </div>
        )}

        <div className="space-y-2">
          {runs.map((r) => (
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
                  {r.framework || "playwright"}
                  {r.branch ? ` · ${r.branch}` : ""}
                  {r.ci_provider ? ` · ${r.ci_provider}` : " · local"}
                  {" · "}
                  {r.run_id}
                </div>
              </div>
              <span
                className={`flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize ${
                  STATUS_STYLES[r.status] || STATUS_STYLES.skipped
                }`}
              >
                {r.status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
                {r.status}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
