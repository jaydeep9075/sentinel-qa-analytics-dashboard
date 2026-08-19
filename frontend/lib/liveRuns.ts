/** Shared shapes and formatting for the two live-run pages, which render the
 * same run from two angles (list vs detail) and previously each carried their
 * own copy of the status palette and their own idea of what a run looks like. */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface RunSummary {
  run_id: string;
  name?: string;
  status: string;
  framework?: string;
  ci_provider?: string;
  branch?: string;
  environment?: string;
  build_url?: string;
  started_at?: string;
  finished_at?: string;
  /** Resolved by the test runner before it starts, when the framework can
   * know it - the denominator behind every progress figure on these pages. */
  total_tests?: number | null;
  /** Aggregates the backend computes for the list view (see store.list_runs);
   * absent on the detail snapshot, which has the full test rows instead. */
  tests_seen?: number;
  passed_count?: number;
  failed_count?: number;
  skipped_count?: number;
  running_count?: number;
}

export const STATUS_STYLES: Record<string, string> = {
  running: "bg-blue-500/10 text-blue-400 border-blue-500/25",
  passed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  failed: "bg-red-500/10 text-red-400 border-red-500/25",
  skipped: "bg-slate-500/10 text-slate-400 border-slate-500/25",
  retried: "bg-amber-500/10 text-amber-400 border-amber-500/25",
  cancelled: "bg-slate-500/10 text-slate-400 border-slate-500/25",
};

export function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** "4m 12s" / "38s" / "1h 04m". Compact on purpose: this sits inside a row
 * that already carries a name, a branch and a status, and a run's duration
 * only ever needs to answer "is this taking unusually long?". */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${seconds}s`;
}

/** Wall-clock span of a run: to its finish if it has one, to now if it is
 * still going. Returns null rather than 0 for a run with no start timestamp,
 * so callers render "—" instead of a confident, wrong "0s". */
export function elapsedMs(
  run: { started_at?: string; finished_at?: string } | null | undefined,
  now: number
): number | null {
  if (!run?.started_at) return null;
  const start = Date.parse(run.started_at);
  if (Number.isNaN(start)) return null;
  const end = run.finished_at ? Date.parse(run.finished_at) : now;
  return Math.max(0, (Number.isNaN(end) ? now : end) - start);
}

/** Share of finished tests that passed. Deliberately excludes still-running
 * tests from the denominator: mid-run, counting not-yet-finished tests as
 * failures would show a pass rate that starts near 0% and climbs, which
 * looks alarming and means nothing. Skips are excluded too - a skipped test
 * neither passed nor failed, and folding it in either direction misreports
 * the health of the run. */
export function passRate(passed: number, failed: number): number | null {
  const finished = passed + failed;
  if (finished === 0) return null;
  return Math.round((passed / finished) * 100);
}
