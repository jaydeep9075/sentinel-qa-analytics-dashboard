"use client";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import { SkeletonRows } from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type AuditEvent = {
  id: number;
  created_at: string;
  action: string;
  actor: string;
  target: string;
  workspace_id: string;
  success: boolean;
  details: unknown;
};

const ACTION_LABELS: Record<string, string> = {
  login: "Login",
  login_failed: "Login failed",
  login_blocked: "Login blocked",
  register: "Registration",
  user_create: "User created",
  user_update: "User updated",
  user_approve: "User approved",
  user_delete: "User deleted",
  password_reset: "Password reset (admin)",
  password_change: "Password changed (self)",
  username_change: "Username changed",
  llm_settings_update: "LLM settings updated",
  usage_reset: "Usage reset",
  build_delete: "Build deleted",
};

export default function AdminAuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const url = new URL(`${API}/admin/audit`);
      url.searchParams.set("limit", "300");
      if (actionFilter) url.searchParams.set("action", actionFilter);
      const res = await fetch(url.toString(), { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load audit log");
      const data = await res.json();
      setEvents(data.events || []);
    } catch {
      setError("Could not load the audit log.");
    } finally {
      setLoading(false);
    }
  }, [actionFilter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <PageTransition>
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold">Audit log</h2>
          <p className="text-sm text-slate-500 dark:text-white/40">Security-relevant actions, most recent first.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-white dark:bg-black/50 border border-slate-300 dark:border-white/10 text-sm"
          >
            <option value="">All actions</option>
            {Object.entries(ACTION_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <button
            onClick={load}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-300 dark:border-white/10 text-sm hover:border-cyan-500/40"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{error}</div>}

      {loading ? (
        <SkeletonRows count={6} />
      ) : (
      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-white/[0.08]">
        <table className="w-full text-sm min-w-[760px]">
          <thead className="bg-slate-50 dark:bg-white/[0.03] text-left">
            <tr className="text-xs uppercase tracking-wider text-slate-500 dark:text-white/40">
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Target</th>
              <th className="px-4 py-3">Workspace</th>
              <th className="px-4 py-3 text-center">Result</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id} className="border-t border-slate-200 dark:border-white/[0.06]">
                <td className="px-4 py-3 text-xs text-slate-500 dark:text-white/40 whitespace-nowrap">
                  {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3 font-medium">{ACTION_LABELS[e.action] || e.action}</td>
                <td className="px-4 py-3">{e.actor}</td>
                <td className="px-4 py-3 text-slate-500 dark:text-white/40">{e.target || "—"}</td>
                <td className="px-4 py-3 text-slate-500 dark:text-white/40">{e.workspace_id || "—"}</td>
                <td className="px-4 py-3 text-center">
                  {e.success ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 inline" />
                  ) : (
                    <XCircle className="w-4 h-4 text-red-500 inline" />
                  )}
                </td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400 dark:text-white/30">
                  No events recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      )}
    </div>
    </PageTransition>
  );
}
