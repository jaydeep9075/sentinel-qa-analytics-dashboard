"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, RotateCcw } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import { SkeletonRows } from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type UsageRow = {
  username: string;
  role: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
  updated_at: string;
  token_limit: number;
  unlimited: boolean;
  remaining: number | null;
  over_limit: boolean;
};

export default function AdminUsagePage() {
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [totals, setTotals] = useState({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, calls: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await fetch(`${API}/admin/usage`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load usage");
      const data = await res.json();
      setRows(data.users || []);
      setTotals(data.totals || totals);
    } catch {
      setError("Could not load token usage.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetUsage = async (username: string) => {
    if (!window.confirm(`Clear recorded token usage for ${username}? Their limit is unaffected.`)) return;
    setNotice("");
    setError("");
    try {
      const res = await fetch(`${API}/admin/usage/${encodeURIComponent(username)}/reset`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed to reset usage");
      setNotice(`Usage cleared for ${username}.`);
      await load();
    } catch {
      setError(`Could not reset usage for ${username}.`);
    }
  };

  return (
    <PageTransition>
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold">Token usage</h2>
          <p className="text-sm text-slate-500 dark:text-white/40">
            Lifetime LLM spend per account. Set limits from the Users tab.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-300 dark:border-white/10 text-sm hover:border-cyan-500/40"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {error && <div className="text-red-400 text-sm bg-red-500/[0.08] p-3 rounded-xl border border-red-500/20">{error}</div>}
      {notice && <div className="text-emerald-500 text-sm bg-emerald-500/[0.08] p-3 rounded-xl border border-emerald-500/20">{notice}</div>}

      <div className="grid gap-4 sm:grid-cols-4">
        <TotalCard label="Prompt tokens" value={totals.prompt_tokens} />
        <TotalCard label="Completion tokens" value={totals.completion_tokens} />
        <TotalCard label="Total tokens" value={totals.total_tokens} />
        <TotalCard label="Calls" value={totals.calls} />
      </div>

      {loading ? (
        <SkeletonRows count={5} />
      ) : (
      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-white/[0.08]">
        <table className="w-full text-sm min-w-[880px]">
          <thead className="bg-slate-50 dark:bg-white/[0.03] text-left">
            <tr className="text-xs uppercase tracking-wider text-slate-500 dark:text-white/40">
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3 text-right">Prompt</th>
              <th className="px-4 py-3 text-right">Completion</th>
              <th className="px-4 py-3 text-right">Total</th>
              <th className="px-4 py-3 text-right">Calls</th>
              <th className="px-4 py-3">Limit</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.username} className={`border-t border-slate-200 dark:border-white/[0.06] ${r.over_limit ? "bg-red-500/[0.04]" : ""}`}>
                <td className="px-4 py-3 font-medium">{r.username}</td>
                <td className="px-4 py-3 text-slate-500 dark:text-white/40">{r.role || "—"}</td>
                <td className="px-4 py-3 text-right tabular-nums">{r.prompt_tokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-right tabular-nums">{r.completion_tokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-right tabular-nums font-semibold">{r.total_tokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-right tabular-nums">{r.calls.toLocaleString()}</td>
                <td className="px-4 py-3">
                  {r.unlimited ? (
                    <span className="text-xs text-slate-400 dark:text-white/30">unlimited</span>
                  ) : (
                    <span className={`text-xs font-medium ${r.over_limit ? "text-red-500" : "text-slate-500 dark:text-white/40"}`}>
                      {r.token_limit.toLocaleString()} {r.over_limit ? "(exceeded)" : ""}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => resetUsage(r.username)}
                    title="Clear recorded usage"
                    className="p-2 rounded-lg border border-slate-300 dark:border-white/10 hover:border-cyan-500/40 inline-flex"
                  >
                    <RotateCcw className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-400 dark:text-white/30">
                  No usage recorded yet.
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

function TotalCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-white/[0.08] bg-white dark:bg-white/[0.02] p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-white/40">{label}</p>
      <p className="text-2xl font-bold mt-1 tabular-nums">{value.toLocaleString()}</p>
    </div>
  );
}
