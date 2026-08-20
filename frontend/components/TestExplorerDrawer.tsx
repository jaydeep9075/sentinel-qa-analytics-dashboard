"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Check,
  ChevronRight,
  Copy,
  Download,
  Loader2,
  MessageSquare,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import {
  getTestsByStatus,
  type TestExplorerResponse,
  type TestRecord,
} from "@/lib/api";
import { askSentinel } from "@/lib/askSentinel";

/**
 * The drill-down behind the dashboard's Passed / Failed / Skipped tiles.
 *
 * Two panes, because a list of 260 failures answers "which ones" but not
 * "what is going on": the rail on the left is the categorised read (failures
 * clustered by cause, everything else by where it lives), the list on the
 * right is the individual tests. Selecting a bucket narrows the list, so the
 * same panel serves both the skim and the specific lookup.
 *
 * Every filter is a server query - nothing here reduces over a full result
 * set client-side, so it behaves the same on a 40-test suite and a 100k one.
 */

export type TestStatus = "passed" | "failed" | "skipped";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  ingestionId: string;
  status: TestStatus;
  onStatusChange: (status: TestStatus) => void;
}

const PAGE_SIZE = 50;
/** CSV export pages the API rather than adding a bulk endpoint; this bounds
 *  how many round trips one click can cost. */
const EXPORT_CAP = 2000;
const EXPORT_PAGE = 200;

const STATUS_META: Record<
  TestStatus,
  { label: string; dot: string; text: string; bar: string; chipOn: string }
> = {
  passed: {
    label: "Passed",
    dot: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    bar: "bg-emerald-500",
    chipOn: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  failed: {
    label: "Failed",
    dot: "bg-red-500",
    text: "text-red-600 dark:text-red-400",
    bar: "bg-red-500",
    chipOn: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  skipped: {
    label: "Skipped",
    dot: "bg-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    bar: "bg-amber-500",
    chipOn: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
};

const SORTS: { key: string; label: string }[] = [
  { key: "name", label: "Name (A–Z)" },
  { key: "slowest", label: "Slowest first" },
  { key: "fastest", label: "Fastest first" },
  { key: "recent", label: "Most recent" },
];

const TAG_PATTERN = /@[\w./:@-]+/g;

/** Split a raw result name into the three things a reader actually scans for.
 *
 *  Playwright/Allure names arrive as one string that concatenates the spec
 *  path, the suite, the case title and every tag - rendered verbatim it is an
 *  unreadable 200-character line, and every row looks identical for the first
 *  60 of them. */
function parseTestName(name: string, specFile?: string) {
  const raw = String(name || "").trim();
  let path = String(specFile || "").trim();
  let rest = raw;

  const hash = raw.indexOf("#");
  if (hash > -1) {
    if (!path) path = raw.slice(0, hash).trim();
    rest = raw.slice(hash + 1);
  }

  // Deduped: these names routinely repeat a tag (once on the suite, again on
  // the case), which renders as the same chip twice and — since the tag is
  // the React key — as a duplicate-key warning.
  const tags = Array.from(new Set(rest.match(TAG_PATTERN) || []));
  const title = rest.replace(TAG_PATTERN, " ").replace(/\s+/g, " ").trim();
  return { title: title || raw || "(unnamed test)", path, tags };
}

/** The question to hand the chat when someone asks about one result.
 *
 *  Carries the identifying detail inline rather than saying "this test",
 *  because the chat has no idea which row was on screen. */
function chatPromptFor(record: TestRecord, title: string, path: string): string {
  const where = path ? ` in ${path}` : "";
  const firstErrorLine = String(record.error || "").split("\n")[0].trim();

  if (record.status === "failed") {
    return (
      `Why did the test "${title}"${where} fail?` +
      (firstErrorLine ? ` It failed with: ${firstErrorLine}` : "") +
      " Explain the likely cause and whether other tests in this build hit the same problem."
    );
  }
  if (record.status === "skipped") {
    return (
      `The test "${title}"${where} was skipped in this build.` +
      (firstErrorLine ? ` The reason recorded was: ${firstErrorLine}` : "") +
      " Why might it have been skipped, and what coverage does that leave open?"
    );
  }
  return `Tell me about the test "${title}"${where} — how it has behaved across recent builds and whether it is stable.`;
}

function formatDuration(seconds?: number): string {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return "—";
  if (value < 1) return `${Math.round(value * 1000)}ms`;
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`;
  const minutes = value / 60;
  if (minutes < 60) return `${minutes.toFixed(minutes < 10 ? 1 : 0)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

function csvCell(value: unknown): string {
  const text = String(value ?? "").replace(/"/g, '""').replace(/\r?\n/g, " ");
  return `"${text}"`;
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          },
          () => {
            // Clipboard can be blocked (insecure origin, permissions policy);
            // silently leaving the icon unchanged is the honest outcome.
          },
        );
      }}
      title={label}
      className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 transition-colors hover:border-cyan-500/30 hover:text-slate-800 dark:border-white/10 dark:text-white/45 dark:hover:text-white"
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function TestRow({
  record,
  dimensions,
  showError,
  onAsk,
}: {
  record: TestRecord;
  dimensions: string[];
  showError: boolean;
  onAsk: (question: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const { title, path, tags } = useMemo(
    () => parseTestName(record.test_name, record.spec_file),
    [record.test_name, record.spec_file],
  );
  const hasError = showError && Boolean(record.error);

  // Deduped for the same reason as the tags: module and project are often the
  // same string on a single-project suite, and rendering it twice is both
  // noise and a duplicate React key.
  const meta = Array.from(
    new Set(
      [
        dimensions.includes("module_name") ? record.module_name : "",
        dimensions.includes("project_name") ? record.project_name : "",
        dimensions.includes("browser") ? record.browser : "",
      ].filter((v): v is string => Boolean(v)),
    ),
  );

  const ask = (e: React.MouseEvent) => {
    e.stopPropagation();
    onAsk(chatPromptFor(record, title, path));
  };

  return (
    <li className="border-b border-slate-100 last:border-0 dark:border-white/[0.05]">
      <div
        role={hasError ? "button" : undefined}
        tabIndex={hasError ? 0 : undefined}
        onClick={hasError ? () => setExpanded((v) => !v) : undefined}
        onKeyDown={
          hasError
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setExpanded((v) => !v);
                }
              }
            : undefined
        }
        className={`group/row flex items-start gap-2.5 px-4 py-2.5 transition-colors ${
          hasError ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-white/[0.03]" : ""
        }`}
      >
        {hasError ? (
          <ChevronRight
            className={`mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform dark:text-white/30 ${
              expanded ? "rotate-90" : ""
            }`}
          />
        ) : (
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300 dark:bg-white/15" />
        )}

        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-slate-800 dark:text-white/85" title={title}>
            {title}
          </p>
          {path && (
            <p
              className="mt-0.5 truncate font-mono text-[11px] text-slate-400 dark:text-white/35"
              title={path}
            >
              {path}
            </p>
          )}
          {(meta.length > 0 || tags.length > 0) && (
            <div className="mt-1 flex flex-wrap items-center gap-1">
              {meta.map((m) => (
                <span
                  key={m}
                  className="rounded border border-slate-200 px-1.5 py-px text-[10px] text-slate-500 dark:border-white/10 dark:text-white/40"
                >
                  {m}
                </span>
              ))}
              {tags.slice(0, 3).map((t) => (
                <span key={t} className="text-[10px] text-cyan-600/70 dark:text-cyan-400/60">
                  {t}
                </span>
              ))}
              {tags.length > 3 && (
                <span className="text-[10px] text-slate-400 dark:text-white/25">
                  +{tags.length - 3}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2 pt-0.5">
          <button
            type="button"
            onClick={ask}
            title="Ask the AI about this test"
            aria-label={`Ask the AI about ${title}`}
            className="rounded-md p-1 text-slate-300 opacity-0 transition-all hover:bg-cyan-500/10 hover:text-cyan-600 focus-visible:opacity-100 group-hover/row:opacity-100 dark:text-white/25 dark:hover:text-cyan-400"
          >
            <MessageSquare className="h-3.5 w-3.5" />
          </button>
          <span className="text-[11px] tabular-nums text-slate-400 dark:text-white/35">
            {formatDuration(record.duration)}
          </span>
        </div>
      </div>

      {hasError && expanded && (
        <div className="border-t border-slate-100 bg-slate-50/70 px-4 py-3 dark:border-white/[0.05] dark:bg-white/[0.02]">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-white/35">
              {record.failure_signature || "Error"}
            </span>
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                onClick={ask}
                className="inline-flex items-center gap-1 rounded-md border border-cyan-500/25 bg-cyan-500/5 px-1.5 py-0.5 text-[10px] font-medium text-cyan-700 transition-colors hover:bg-cyan-500/10 dark:text-cyan-400"
              >
                <MessageSquare className="h-3 w-3" />
                Ask AI
              </button>
              <CopyButton text={record.error || ""} label="Copy the full error" />
            </div>
          </div>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-600 dark:text-white/55">
            {record.error}
          </pre>
        </div>
      )}
    </li>
  );
}

export default function TestExplorerDrawer({
  isOpen,
  onClose,
  ingestionId,
  status,
  onStatusChange,
}: Props) {
  const [mounted, setMounted] = useState(false);
  // null means "let the server pick the grouping for this status" — keeping
  // the user's choice and the resolved default in separate places is what
  // stops the resolved value from feeding back in and refetching.
  const [groupBy, setGroupBy] = useState<string | null>(null);
  const [group, setGroup] = useState("");
  const [sort, setSort] = useState("name");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounced(searchInput, 250);
  const [offset, setOffset] = useState(0);

  const [meta, setMeta] = useState<TestExplorerResponse | null>(null);
  const [rows, setRows] = useState<TestRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const listRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => setMounted(true), []);

  // Escape closes; the page behind must not scroll while a full-height
  // overlay is on top of it.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen, onClose]);

  // Reset the drill-down whenever the panel is reopened or pointed at a
  // different status/build — carrying a previous status's group filter over
  // would silently show an empty list.
  useEffect(() => {
    if (!isOpen) return;
    setGroupBy(null);
    setGroup("");
    setSearchInput("");
    setOffset(0);
    setRows([]);
    setError(null);
  }, [isOpen, status, ingestionId]);

  useEffect(() => {
    if (!isOpen) return;
    if (!ingestionId) {
      // Nothing to query against — say so instead of spinning forever.
      setLoading(false);
      setError("Select a build to see its tests.");
      return;
    }
    const controller = new AbortController();
    setLoading(true);

    getTestsByStatus(ingestionId, {
      status,
      groupBy: groupBy || undefined,
      group: group || undefined,
      q: search || undefined,
      sort,
      limit: PAGE_SIZE,
      offset,
      signal: controller.signal,
    })
      .then((data) => {
        setMeta(data);
        setRows((prev) => (data.offset > 0 ? [...prev, ...data.tests] : data.tests));
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Failed to load test details");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [isOpen, ingestionId, status, groupBy, group, search, sort, offset]);

  /** Hand a question to the floating chat and get out of its way — both sit
   *  at z-50, so leaving the drawer open would just hide the answer. */
  const askAi = useCallback(
    (question: string) => {
      askSentinel(question);
      onClose();
    },
    [onClose],
  );

  const changeFilter = useCallback((apply: () => void) => {
    apply();
    setOffset(0);
    listRef.current?.scrollTo({ top: 0 });
  }, []);

  const handleExport = useCallback(async () => {
    if (!ingestionId || exporting) return;
    setExporting(true);
    try {
      const collected: TestRecord[] = [];
      for (let at = 0; at < EXPORT_CAP; at += EXPORT_PAGE) {
        const page = await getTestsByStatus(ingestionId, {
          status,
          groupBy: groupBy || undefined,
          group: group || undefined,
          q: search || undefined,
          sort,
          limit: EXPORT_PAGE,
          offset: at,
        });
        collected.push(...page.tests);
        if (!page.has_more || page.tests.length === 0) break;
      }

      const header = [
        "Status",
        "Test",
        "Spec file",
        "Module",
        "Project",
        "Browser",
        "Duration (s)",
        "Executed at",
        "Failure signature",
        "Error",
      ];
      const body = collected.map((r) =>
        [
          r.status,
          r.test_name,
          r.spec_file,
          r.module_name,
          r.project_name,
          r.browser,
          r.duration,
          r.executed_at,
          r.failure_signature,
          r.error,
        ]
          .map(csvCell)
          .join(","),
      );
      const blob = new Blob([[header.map(csvCell).join(","), ...body].join("\r\n")], {
        type: "text/csv;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${ingestionId || "build"}-${status}-tests.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Export failed — the build may still be loading. Try again.");
    } finally {
      setExporting(false);
    }
  }, [ingestionId, exporting, status, groupBy, group, search, sort]);

  if (!isOpen || !mounted) return null;

  const tone = STATUS_META[status];
  const counts = meta?.status_counts;
  const activeGroupBy = meta?.group_by || "none";
  const groupLabel =
    meta?.group_options?.find((o) => o.key === activeGroupBy)?.label || "No grouping";
  const isFiltered = Boolean(group) || Boolean(search);
  const initialLoad = loading && rows.length === 0;

  return createPortal(
    <AnimatePresence>
      <motion.div
        key="test-explorer"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-[2px]"
        onClick={onClose}
      >
        <motion.aside
          role="dialog"
          aria-modal="true"
          aria-label={`${tone.label} tests`}
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 40, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 32 }}
          onClick={(e) => e.stopPropagation()}
          className="flex h-full w-full max-w-[980px] flex-col border-l border-slate-200 bg-white shadow-[-24px_0_60px_rgba(15,23,42,0.25)] dark:border-white/[0.08] dark:bg-[#0a0a0a]"
        >
          {/* ── Header: which slice, how big, and the sibling slices ── */}
          <header className="shrink-0 border-b border-slate-200 px-5 pt-4 dark:border-white/[0.07]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${tone.dot}`} />
                  <h2 className="text-base font-semibold text-slate-900 dark:text-white">
                    {tone.label} tests
                  </h2>
                </div>
                <p className="mt-1 text-xs text-slate-500 dark:text-white/40">
                  {isFiltered ? (
                    <>
                      <span className="font-semibold tabular-nums text-slate-700 dark:text-white/70">
                        {(meta?.matched ?? 0).toLocaleString()}
                      </span>{" "}
                      of {(meta?.status_total ?? 0).toLocaleString()} {status} · grouped by{" "}
                      {groupLabel.toLowerCase()}
                    </>
                  ) : (
                    <>
                      <span className="font-semibold tabular-nums text-slate-700 dark:text-white/70">
                        {(meta?.status_total ?? 0).toLocaleString()}
                      </span>{" "}
                      of {(meta?.total_rows ?? 0).toLocaleString()} results in this build
                    </>
                  )}
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={exporting || !meta?.matched}
                  title={`Export the ${isFiltered ? "filtered" : status} list as CSV (first ${EXPORT_CAP.toLocaleString()} rows)`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-cyan-500/30 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/10 dark:text-white/55 dark:hover:text-white"
                >
                  {exporting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="h-3.5 w-3.5" />
                  )}
                  CSV
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-white/35 dark:hover:bg-white/[0.08] dark:hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="mt-3 flex gap-1">
              {(Object.keys(STATUS_META) as TestStatus[]).map((key) => {
                const on = key === status;
                const count = counts?.[key];
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onStatusChange(key)}
                    className={`-mb-px border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
                      on
                        ? `border-current ${STATUS_META[key].text}`
                        : "border-transparent text-slate-500 hover:text-slate-800 dark:text-white/40 dark:hover:text-white/70"
                    }`}
                  >
                    {STATUS_META[key].label}
                    {count !== undefined && (
                      <span className="ml-1.5 tabular-nums opacity-60">
                        {count.toLocaleString()}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </header>

          {/* ── Toolbar: search, grouping, ordering ── */}
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-200 px-5 py-2.5 dark:border-white/[0.07]">
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400 dark:text-white/30" />
              <input
                ref={searchRef}
                value={searchInput}
                onChange={(e) => changeFilter(() => setSearchInput(e.target.value))}
                placeholder="Search test name, error, module…"
                className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pl-8 pr-7 text-xs text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-cyan-500/40 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/85 dark:placeholder:text-white/25"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={() => changeFilter(() => setSearchInput(""))}
                  aria-label="Clear search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 dark:text-white/30 dark:hover:text-white"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {(meta?.group_options?.length ?? 0) > 1 && (
              <label className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-white/40">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                <select
                  value={activeGroupBy}
                  onChange={(e) =>
                    changeFilter(() => {
                      setGroupBy(e.target.value);
                      setGroup("");
                    })
                  }
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-cyan-500/40 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/80"
                >
                  {meta?.group_options?.map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <select
              value={sort}
              onChange={(e) => changeFilter(() => setSort(e.target.value))}
              aria-label="Sort order"
              className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-cyan-500/40 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/80"
            >
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* ── Body: categories on the left, tests on the right ── */}
          <div className="flex min-h-0 flex-1">
            {activeGroupBy !== "none" && (meta?.groups?.length ?? 0) > 0 && (
              <nav className="hidden w-64 shrink-0 overflow-y-auto border-r border-slate-200 py-2 md:block dark:border-white/[0.07]">
                <p className="px-4 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400 dark:text-white/30">
                  {groupLabel}
                </p>
                <GroupButton
                  label="All"
                  count={meta?.status_total ?? 0}
                  share={100}
                  active={!group}
                  tone={tone.bar}
                  onClick={() => changeFilter(() => setGroup(""))}
                />
                {meta?.groups?.map((g) => (
                  <GroupButton
                    key={g.key}
                    label={g.key}
                    count={g.count}
                    share={g.share}
                    active={group === g.key}
                    tone={tone.bar}
                    onClick={() => changeFilter(() => setGroup(group === g.key ? "" : g.key))}
                  />
                ))}
                {meta?.group_truncated && (
                  <p className="px-4 pt-2 text-[10px] leading-snug text-slate-400 dark:text-white/25">
                    Showing the {meta.groups.length} largest groups. Narrow with search to see
                    the rest.
                  </p>
                )}
              </nav>
            )}

            <div ref={listRef} className="min-w-0 flex-1 overflow-y-auto">
              {/* Group chips stand in for the rail below the md breakpoint. */}
              {activeGroupBy !== "none" && (meta?.groups?.length ?? 0) > 0 && (
                <div className="flex gap-1.5 overflow-x-auto border-b border-slate-200 px-4 py-2 md:hidden dark:border-white/[0.07]">
                  <button
                    type="button"
                    onClick={() => changeFilter(() => setGroup(""))}
                    className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] ${
                      !group
                        ? tone.chipOn
                        : "border-slate-200 text-slate-500 dark:border-white/10 dark:text-white/45"
                    }`}
                  >
                    All {(meta?.status_total ?? 0).toLocaleString()}
                  </button>
                  {meta?.groups?.map((g) => (
                    <button
                      key={g.key}
                      type="button"
                      onClick={() => changeFilter(() => setGroup(group === g.key ? "" : g.key))}
                      className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] ${
                        group === g.key
                          ? tone.chipOn
                          : "border-slate-200 text-slate-500 dark:border-white/10 dark:text-white/45"
                      }`}
                    >
                      {g.key} {g.count.toLocaleString()}
                    </button>
                  ))}
                </div>
              )}

              {error && (
                <div className="m-4 flex items-start gap-2 rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2.5 text-xs text-red-600 dark:text-red-400">
                  <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {initialLoad && (
                <ul className="animate-pulse">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <li key={i} className="border-b border-slate-100 px-4 py-3 dark:border-white/[0.05]">
                      <div className="h-3 w-2/3 rounded bg-slate-200 dark:bg-white/10" />
                      <div className="mt-2 h-2.5 w-1/3 rounded bg-slate-100 dark:bg-white/[0.06]" />
                    </li>
                  ))}
                </ul>
              )}

              {!initialLoad && !error && rows.length === 0 && (
                <div className="px-6 py-16 text-center">
                  <p className="text-sm font-medium text-slate-700 dark:text-white/70">
                    No {status} tests match
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-white/40">
                    {isFiltered
                      ? "Clear the search or pick another group."
                      : `This build has no ${status} results.`}
                  </p>
                  {isFiltered && (
                    <button
                      type="button"
                      onClick={() =>
                        changeFilter(() => {
                          setSearchInput("");
                          setGroup("");
                        })
                      }
                      className="mt-3 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-cyan-500/30 dark:border-white/10 dark:text-white/55"
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              )}

              {rows.length > 0 && (
                <ul>
                  {rows.map((record, i) => (
                    <TestRow
                      key={`${record.test_name}-${i}`}
                      record={record}
                      dimensions={meta?.dimensions || []}
                      showError={status !== "passed"}
                      onAsk={askAi}
                    />
                  ))}
                </ul>
              )}

              {meta?.has_more && (
                <div className="px-4 py-4 text-center">
                  <button
                    type="button"
                    onClick={() => setOffset(rows.length)}
                    disabled={loading}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-cyan-500/30 hover:text-slate-900 disabled:opacity-50 dark:border-white/10 dark:text-white/55 dark:hover:text-white"
                  >
                    {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Load {Math.min(PAGE_SIZE, (meta.matched || 0) - rows.length).toLocaleString()} more
                  </button>
                  <p className="mt-2 text-[11px] text-slate-400 dark:text-white/25">
                    Showing {rows.length.toLocaleString()} of {(meta.matched || 0).toLocaleString()}
                  </p>
                </div>
              )}
            </div>
          </div>
        </motion.aside>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}

function GroupButton({
  label,
  count,
  share,
  active,
  tone,
  onClick,
}: {
  label: string;
  count: number;
  share: number;
  active: boolean;
  tone: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      className={`block w-full px-4 py-1.5 text-left transition-colors ${
        active ? "bg-slate-100 dark:bg-white/[0.05]" : "hover:bg-slate-50 dark:hover:bg-white/[0.03]"
      }`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className={`truncate text-xs ${
            active
              ? "font-semibold text-slate-900 dark:text-white"
              : "text-slate-600 dark:text-white/60"
          }`}
        >
          {label}
        </span>
        <span className="shrink-0 text-[11px] tabular-nums text-slate-400 dark:text-white/35">
          {count.toLocaleString()}
        </span>
      </div>
      {/* The bar is the whole point of the rail: it turns a column of counts
          into "this one cause is half of them" at a glance. */}
      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-white/[0.07]">
        <div
          className={`h-full rounded-full ${tone} ${active ? "" : "opacity-50"}`}
          style={{ width: `${Math.max(2, Math.min(100, share))}%` }}
        />
      </div>
    </button>
  );
}
