"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Database, KeyRound, RefreshCw, Users, Layers } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import Skeleton from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type Overview = {
  users: { total: number; by_status: Record<string, number> };
  workspaces: { count: number; names: string[] };
  builds: { count: number };
  token_usage: { lifetime_total: number; accounts_with_usage: number };
  llm: { ready: boolean; provider: string; model: string };
  server_time: string;
};

export default function AdminOverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await fetch(`${API}/admin/overview`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load overview");
      setData(await res.json());
    } catch {
      setError("Could not load the deployment overview.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-4 w-72" />
          </div>
          <Skeleton className="h-9 w-28" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{error}</div>;
  }

  const pending = data.users.by_status.pending || 0;

  return (
    <PageTransition>
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Deployment overview</h2>
          <p className="text-sm text-slate-500 dark:text-white/40">What this install looks like right now.</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-300 dark:border-white/10 text-sm hover:border-cyan-500/40"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {pending > 0 && (
        <Link
          href="/admin/users"
          className="flex items-center gap-3 p-4 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] hover:bg-amber-500/[0.1] transition-colors"
        >
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
          <span className="text-sm font-semibold text-amber-600 dark:text-amber-400">
            {pending} account{pending === 1 ? "" : "s"} awaiting approval — review in Users →
          </span>
        </Link>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Users} label="Users" value={data.users.total} sub={`${data.users.by_status.active || 0} active · ${pending} pending · ${data.users.by_status.disabled || 0} disabled`} />
        <StatCard icon={Layers} label="Workspaces" value={data.workspaces.count} sub={data.workspaces.names.slice(0, 4).join(", ") || "none"} />
        <StatCard icon={Database} label="Builds" value={data.builds.count} sub="ingested and visible" />
        <StatCard icon={KeyRound} label="Tokens spent" value={data.token_usage.lifetime_total.toLocaleString()} sub={`${data.token_usage.accounts_with_usage} account(s) with usage`} />
      </div>

      <div className={`flex items-center gap-3 p-4 rounded-xl border ${data.llm.ready ? "border-emerald-500/25 bg-emerald-500/[0.06]" : "border-red-500/25 bg-red-500/[0.06]"}`}>
        {data.llm.ready ? (
          <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
        ) : (
          <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
        )}
        <div className="text-sm flex-1">
          <p className={`font-semibold ${data.llm.ready ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
            {data.llm.ready
              ? `LLM configured — ${data.llm.provider} / ${data.llm.model}`
              : "LLM is not fully configured"}
          </p>
          {!data.llm.ready && (
            <p className="text-red-700/80 dark:text-red-300/70 mt-0.5">
              Chat and chart generation will fail until this is finished.{" "}
              <Link href="/admin/settings" className="underline">Finish setup →</Link>
            </p>
          )}
        </div>
      </div>
    </div>
    </PageTransition>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  sub: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] bg-white dark:bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 text-slate-500 dark:text-white/40 text-xs font-semibold uppercase tracking-wider">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <p className="text-2xl font-bold mt-2">{value}</p>
      <p className="text-xs text-slate-400 dark:text-white/30 mt-1 truncate" title={sub}>{sub}</p>
    </div>
  );
}
