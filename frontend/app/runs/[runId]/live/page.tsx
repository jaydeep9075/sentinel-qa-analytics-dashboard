"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  CircleDot,
  Loader2,
  Image as ImageIcon,
  Video,
  Paperclip,
  Radio,
} from "lucide-react";
import BrandLogo from "@/components/BrandLogo";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TestRow {
  test_id: string;
  title: string;
  file?: string;
  status?: string;
  duration_ms?: number;
  retry?: number;
  worker_id?: number;
  error?: string;
}

interface LogRow {
  ts: string;
  test_id?: string;
  level?: string;
  message: string;
}

interface AttachmentRow {
  /** Numeric while the run is live (SQLite row id); "run_id/filename" once
   * finalized (see get_finalized_run in the backend - the SQLite id is
   * gone by then on purpose, only the file itself survives). */
  id: number | string;
  test_id?: string;
  kind: string;
  storage_path?: string;
}

interface RunInfo {
  run_id: string;
  name?: string;
  status: string;
  framework?: string;
  ci_provider?: string;
  branch?: string;
  started_at?: string;
  finished_at?: string;
}

const STATUS_STYLES: Record<string, string> = {
  running: "bg-blue-500/10 text-blue-400 border-blue-500/25 shadow-[0_0_14px_rgba(59,130,246,0.15)]",
  passed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25 shadow-[0_0_14px_rgba(16,185,129,0.15)]",
  failed: "bg-red-500/10 text-red-400 border-red-500/25 shadow-[0_0_14px_rgba(239,68,68,0.15)]",
  skipped: "bg-slate-500/10 text-slate-400 border-slate-500/25",
  retried: "bg-amber-500/10 text-amber-400 border-amber-500/25",
  cancelled: "bg-slate-500/10 text-slate-400 border-slate-500/25",
};

function StatusBadge({ status }: { status?: string }) {
  const s = status || "running";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize ${
        STATUS_STYLES[s] || STATUS_STYLES.running
      }`}
    >
      {s === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
      {s}
    </span>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white/90 shadow-[0_4px_20px_rgba(15,23,42,0.06)] dark:border-white/[0.08] dark:bg-black/40 dark:shadow-[0_4px_20px_rgba(0,0,0,0.35)] ${className}`}
    >
      {children}
    </div>
  );
}

export default function LiveRunPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;

  const [run, setRun] = useState<RunInfo | null>(null);
  const [tests, setTests] = useState<Record<string, TestRow>>({});
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [attachments, setAttachments] = useState<AttachmentRow[]>([]);
  const [frames, setFrames] = useState<Record<string, string>>({});
  const [connected, setConnected] = useState(false);
  // A run that already finished (and had its hot-layer rows discarded, see
  // LIVE_EXECUTION_WHY_THIS_APPROACH.md) has nothing left to stream - it's
  // read once from the permanent record instead of over SSE.
  const [historyMode, setHistoryMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

  // A finished run's SQLite rows are gone (see LIVE_EXECUTION_WHY_THIS_APPROACH.md),
  // so /live/runs/{id}/stream would 404 forever and EventSource would just
  // retry it in an endless loop. Check which mode we're in first: if the
  // run is still live, proceed exactly as before (SSE); if it already
  // finalized, load the permanent record once and render statically -
  // there is nothing left to "watch" for a run that's already over.
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    const loadHistory = async () => {
      try {
        const res = await fetch(`${API_BASE}/live/history/${runId}`, { headers: authHeaders });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        setHistoryMode(true);
        if (data.run) setRun(data.run);
        if (Array.isArray(data.tests)) {
          setTests(Object.fromEntries(data.tests.map((t: TestRow) => [t.test_id, t])));
        }
        if (Array.isArray(data.attachments)) setAttachments(data.attachments);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    const checkLive = async () => {
      try {
        const res = await fetch(`${API_BASE}/live/runs/${runId}`, { headers: authHeaders });
        if (res.ok) {
          if (!cancelled) setLoading(false);
          return true;
        }
      } catch {
        // fall through to history
      }
      await loadHistory();
      return false;
    };

    let source: EventSource | null = null;

    checkLive().then((isLive) => {
      if (!isLive || cancelled) return;

      const url = `${API_BASE}/live/runs/${runId}/stream${token ? `?token=${encodeURIComponent(token)}` : ""}`;
      source = new EventSource(url);
      wireLiveStream(source);
    });

    return () => {
      cancelled = true;
      source?.close();
    };
  }, [runId, token]);

  function wireLiveStream(source: EventSource) {
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    source.addEventListener("snapshot", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.run) setRun(data.run);
      if (Array.isArray(data.tests)) {
        setTests(Object.fromEntries(data.tests.map((t: TestRow) => [t.test_id, t])));
      }
      if (Array.isArray(data.logs)) {
        setLogs([...data.logs].reverse());
      }
      if (Array.isArray(data.attachments)) {
        setAttachments(
          data.attachments.map((a: { id: number; test_id?: string; kind: string; storage_path?: string }) => ({
            id: a.id,
            test_id: a.test_id,
            kind: a.kind,
            storage_path: a.storage_path,
          }))
        );
      }
      if (data.frames && typeof data.frames === "object") {
        setFrames(data.frames);
      }
    });

    source.addEventListener("run.started", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.run) setRun(data.run);
    });

    source.addEventListener("run.finished", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setRun((prev) => (prev ? { ...prev, status: data.status } : prev));
    });

    source.addEventListener("test.started", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      const t = data.test;
      if (!t) return;
      setTests((prev) => ({ ...prev, [t.id]: { ...prev[t.id], test_id: t.id, ...t } }));
    });

    source.addEventListener("test.finished", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      const t = data.test;
      if (!t) return;
      setTests((prev) => ({ ...prev, [t.id]: { ...prev[t.id], test_id: t.id, ...t } }));
    });

    source.addEventListener("test.log", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setLogs((prev) => {
        // A long/chatty run streams indefinitely for as long as the tab
        // stays open watching it - cap in-memory history to match the
        // backend's own snapshot limit (LIMIT 200 in store.py) instead of
        // growing forever.
        const next = [
          ...prev,
          {
            ts: data.ts,
            test_id: data.test?.id,
            level: data.payload?.level,
            message: data.payload?.message ?? "",
          },
        ];
        return next.length > 200 ? next.slice(next.length - 200) : next;
      });
    });

    source.addEventListener("test.attachment", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      const p = data.payload;
      if (!p?.id) return;
      setAttachments((prev) => [
        ...prev,
        { id: p.id, test_id: data.test?.id, kind: p.kind, storage_path: p.storage_path },
      ]);
    });

    source.addEventListener("worker.frame", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      const frame = data.payload?.frame;
      if (!frame || data.worker_id === undefined) return;
      setFrames((prev) => ({ ...prev, [String(data.worker_id)]: frame }));
    });
  }

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // The run just finished (via the run.finished SSE event below) but is
  // still in "live" mode - the attachment URLs on screen right now are
  // SQLite-id based and will 404 the moment finalize deletes those rows
  // (screenshots/video are preserved, but under a different URL scheme -
  // see LIVE_EXECUTION_ARCHITECTURE.md #8). Poll the permanent record
  // until it's ready, then switch over, instead of leaving stale/broken
  // links on screen. Finalize duration varies (embeddings can take a
  // while on a cold model), so this polls rather than assuming a fixed delay.
  useEffect(() => {
    if (historyMode || !run || run.status === "running" || !runId) return;
    let cancelled = false;
    const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    const poll = async () => {
      for (let attempt = 0; attempt < 20 && !cancelled; attempt++) {
        try {
          const res = await fetch(`${API_BASE}/live/history/${runId}`, { headers: authHeaders });
          if (res.ok) {
            const data = await res.json();
            if (cancelled) return;
            setHistoryMode(true);
            if (Array.isArray(data.attachments)) setAttachments(data.attachments);
            return;
          }
        } catch {
          // backend momentarily unreachable mid-finalize - keep polling
        }
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    };
    void poll();
    return () => {
      cancelled = true;
    };
  }, [run?.status, historyMode, runId, token]);

  const attachmentUrl = (a: AttachmentRow) =>
    historyMode
      ? `${API_BASE}/live/history-attachments/${a.id}${token ? `?token=${encodeURIComponent(token)}` : ""}`
      : `${API_BASE}/live/attachments/${a.id}${token ? `?token=${encodeURIComponent(token)}` : ""}`;

  const testList = useMemo(
    () => Object.values(tests).sort((a, b) => a.title.localeCompare(b.title)),
    [tests]
  );

  const counts = useMemo(() => {
    const c = { running: 0, passed: 0, failed: 0, skipped: 0 };
    for (const t of testList) {
      const key = (t.status || "running") as keyof typeof c;
      if (key in c) c[key] += 1;
    }
    return c;
  }, [testList]);

  const COUNT_ACCENT: Record<string, string> = {
    running: "text-blue-400",
    passed: "text-emerald-400",
    failed: "text-red-400",
    skipped: "text-slate-400",
  };

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
                <span className="font-normal text-slate-500 dark:text-white/60">Live Run</span>
              </h1>
              <p className="hidden text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/25 sm:block">
                QA Intelligence Platform
              </p>
            </div>
          </div>
          <Link
            href="/runs/live"
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition-all hover:bg-slate-200 dark:border-white/[0.1] dark:bg-white/[0.05] dark:text-white/75 dark:hover:bg-white/[0.1]"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> All live runs
          </Link>
        </div>
      </header>

      <div className="relative z-10 mx-auto max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
        {loading && (
          <div className="mb-6 flex items-center gap-2 text-sm text-slate-400 dark:text-white/30">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading run…
          </div>
        )}

        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-1 flex items-center gap-2 text-xs font-medium text-slate-400 dark:text-white/30">
              <CircleDot className={`h-3 w-3 ${connected ? "text-emerald-400" : historyMode ? "text-slate-400" : "text-amber-400"}`} />
              {historyMode ? "finished · showing permanent record" : connected ? "live" : "reconnecting…"} · {runId}
            </div>
            <h2 className="truncate bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-xl font-bold text-transparent sm:text-2xl">
              {run?.name || "playwright run"}
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-white/40">
              {run?.framework || "playwright"}
              {run?.ci_provider ? ` · ${run.ci_provider}` : " · local"}
              {run?.branch ? ` · ${run.branch}` : ""}
            </p>
          </div>
          <StatusBadge status={run?.status} />
        </div>

        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(["running", "passed", "failed", "skipped"] as const).map((key) => (
            <Card key={key} className="p-3 sm:p-4">
              <div className={`text-2xl font-bold tabular-nums sm:text-3xl ${COUNT_ACCENT[key]}`}>{counts[key]}</div>
              <div className="mt-0.5 text-xs font-medium capitalize text-slate-500 dark:text-white/40">{key}</div>
            </Card>
          ))}
        </div>

        {!historyMode && Object.keys(frames).length > 0 && (
          <Card className="mb-6 p-4">
            <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/30">
              <Radio className="h-3.5 w-3.5 text-emerald-400" /> Live browser
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {Object.entries(frames).map(([workerId, frame]) => (
                <div key={workerId} className="overflow-hidden rounded-lg border border-slate-200 dark:border-white/[0.08]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/jpeg;base64,${frame}`}
                    alt={`Worker ${workerId} live view`}
                    className="w-full"
                  />
                  <div className="border-t border-slate-200 px-2 py-1 text-[11px] text-slate-500 dark:border-white/[0.08] dark:text-white/40">
                    Worker {workerId}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        <div className={`grid gap-6 ${historyMode ? "" : "md:grid-cols-2"}`}>
          <Card>
            <h3 className="border-b border-slate-200 px-4 py-3 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:border-white/[0.08] dark:text-white/30">
              Tests
            </h3>
            <div className="max-h-[420px] overflow-y-auto">
              {testList.length === 0 && (
                <div className="p-4 text-sm text-slate-400 dark:text-white/30">Waiting for tests to start…</div>
              )}
              {testList.map((t) => {
                const attachmentCount = attachments.filter((a) => a.test_id === t.test_id).length;
                return (
                  <div
                    key={t.test_id}
                    className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5 text-sm last:border-b-0 dark:border-white/[0.04]"
                  >
                    <span className="flex min-w-0 items-center gap-1.5 truncate">
                      <span className="truncate">{t.title}</span>
                      {attachmentCount > 0 && (
                        <span className="flex shrink-0 items-center gap-0.5 text-[10px] text-slate-400 dark:text-white/30">
                          <Paperclip className="h-3 w-3" />
                          {attachmentCount}
                        </span>
                      )}
                    </span>
                    <StatusBadge status={t.status} />
                  </div>
                );
              })}
            </div>
          </Card>

          {!historyMode && (
          <Card className="overflow-hidden">
            <h3 className="border-b border-slate-200 px-4 py-3 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:border-white/[0.08] dark:text-white/30">
              Live log
            </h3>
            <div className="h-[420px] overflow-y-auto bg-slate-950 p-3 font-mono text-xs text-slate-300">
              {logs.map((l, i) => (
                <div key={i} className="whitespace-pre-wrap">
                  <span className="text-slate-600">{l.ts?.slice(11, 19)}</span>{" "}
                  <span className={l.level === "stderr" ? "text-red-400" : "text-slate-300"}>{l.message}</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </Card>
          )}
        </div>

        {attachments.length > 0 && (
          <div className="mt-6">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-white/30">
              Attachments ({attachments.length})
            </h3>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {attachments.map((a) => {
                const testTitle = (a.test_id && tests[a.test_id]?.title) || a.test_id || "";
                const isImage = a.kind.toLowerCase().includes("screenshot") || a.kind.toLowerCase().includes("image");
                const isVideo = a.kind.toLowerCase().includes("video");
                return (
                  <a
                    key={a.id}
                    href={attachmentUrl(a)}
                    target="_blank"
                    rel="noreferrer"
                    className="group block overflow-hidden rounded-xl border border-slate-200 bg-white/90 shadow-[0_4px_20px_rgba(15,23,42,0.06)] transition-all hover:border-cyan-500/30 hover:shadow-[0_4px_20px_rgba(0,240,255,0.1)] dark:border-white/[0.08] dark:bg-black/40 dark:shadow-[0_4px_20px_rgba(0,0,0,0.35)]"
                  >
                    <div className="flex h-28 items-center justify-center bg-slate-100 dark:bg-white/[0.03]">
                      {isImage ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={attachmentUrl(a)}
                          alt={`${a.kind} for ${testTitle}`}
                          className="h-full w-full object-cover"
                        />
                      ) : isVideo ? (
                        <video src={attachmentUrl(a)} className="h-full w-full object-cover" muted />
                      ) : (
                        <Paperclip className="h-6 w-6 text-slate-400" />
                      )}
                    </div>
                    <div className="flex items-center gap-1 border-t border-slate-200 px-2 py-1.5 text-[11px] text-slate-500 dark:border-white/[0.08] dark:text-white/40">
                      {isImage ? (
                        <ImageIcon className="h-3 w-3 shrink-0" />
                      ) : isVideo ? (
                        <Video className="h-3 w-3 shrink-0" />
                      ) : (
                        <Paperclip className="h-3 w-3 shrink-0" />
                      )}
                      <span className="truncate">{a.kind}</span>
                      {testTitle && <span className="truncate text-slate-400 dark:text-white/25">· {testTitle}</span>}
                    </div>
                  </a>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
