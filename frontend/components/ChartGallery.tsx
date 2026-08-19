"use client";

import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import useSWR from "swr";
import { getChartHistory, deleteChart, submitFeedback } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import { schedulePlotlyPreload } from "@/lib/plotlyPreload";
import AIGeneratedChart from "./AIGeneratedChart";
import {
  LayoutGrid,
  List,
  Trash2,
  GripVertical,
  Sparkles,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  Palette,
} from "lucide-react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

interface Chart {
  id: string;
  prompt: string;
  config: unknown;
  created_at: string;
}

interface ChartHistoryItem {
  id: string;
  prompt?: string;
  config?: string | unknown;
  created_at: string;
}

interface ChartHistoryResponse {
  history?: ChartHistoryItem[];
}

const chartsCacheByIngestion = new Map<string, Chart[]>();
const parsedConfigCache = new Map<string, unknown>();

/** Payload the chart generator hands over once a figure is ready. */
type ChartGeneratedDetail = {
  prompt?: string;
  chart?: string | unknown;
  chartId?: string;
};

function readEventDetail(event: Event): ChartGeneratedDetail {
  const detail = (event as CustomEvent<ChartGeneratedDetail | string>).detail;
  if (typeof detail === "string") return { prompt: detail };
  return detail || {};
}

function parseChartConfig(raw: string | unknown): unknown {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== "string") return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function perfNow(): number {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

function shouldLogPerf(): boolean {
  if (typeof window === "undefined") return false;
  if (process.env.NODE_ENV !== "production") return true;
  return localStorage.getItem("qa_perf_debug") === "1";
}

const fetchCharts = async (ingestionId: string) => {
  const started = perfNow();
  const sessionId = "__all__";
  const response = (await getChartHistory(sessionId, ingestionId)) as
    | ChartHistoryResponse
    | ChartHistoryItem[];

  let historyArray = (response as ChartHistoryResponse).history;
  if (!historyArray && Array.isArray(response)) {
    historyArray = response;
  }

  if (!Array.isArray(historyArray)) {
    return [];
  }

  const parseStarted = perfNow();
  const charts = historyArray.map((item: ChartHistoryItem) => {
    const cacheKey = `${item.id}:${item.created_at || ""}`;
    let parsedConfig;
    if (parsedConfigCache.has(cacheKey)) {
      parsedConfig = parsedConfigCache.get(cacheKey);
    } else {
      try {
        parsedConfig =
          typeof item.config === "string" ? JSON.parse(item.config) : item.config;
      } catch {
        parsedConfig = null;
      }
      parsedConfigCache.set(cacheKey, parsedConfig);
    }
    return {
      id: item.id,
      prompt: item.prompt || "Chart",
      config: parsedConfig,
      created_at: item.created_at,
    };
  });

  if (shouldLogPerf()) {
    const totalMs = perfNow() - started;
    const parseMs = perfNow() - parseStarted;
    console.debug("[perf] charts:history", {
      ingestionId,
      count: charts.length,
      total_ms: Number(totalMs.toFixed(1)),
      parse_ms: Number(parseMs.toFixed(1)),
    });
  }
  return charts;
};

function SortableItem({
  chart,
  onDelete,
  isDeleting = false,
  ingestionId,
}: {
  chart: Chart;
  onDelete: (id: string) => void;
  isDeleting?: boolean;
  ingestionId?: string;
}) {
  const [isSavingFeedback, setIsSavingFeedback] = useState(false);
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: chart.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 999 : "auto",
  };

  const submitChartFeedback = async (
    feedbackType: "up" | "down" | "improve",
    askForNotes = false,
  ) => {
    if (!ingestionId || isSavingFeedback) return;
    const notes = askForNotes
      ? window.prompt("What should improve in this chart? Mention color, readability, labels, or layout.") || ""
      : "";

    try {
      setIsSavingFeedback(true);
      await submitFeedback(ingestionId, {
        target_kind: "chart",
        feedback_type: feedbackType,
        chart_id: chart.id,
        prompt: chart.prompt,
        notes,
        tags: feedbackType === "improve" ? ["color", "chart-style"] : ["chart-quality"],
      });
      setFeedbackSaved(true);
      setTimeout(() => setFeedbackSaved(false), 1800);
    } finally {
      setIsSavingFeedback(false);
    }
  };

  return (
    // Opacity-only entrance wrapper: dnd-kit writes its own inline
    // `transform` on the node below for drag positioning, so animating
    // transform/scale here (even on a parent) risks visibly fighting it
    // mid-drag. Opacity is safe because dnd-kit never touches it.
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.35 }}>
    <div
      ref={setNodeRef}
      style={style}
      className="group bg-white border border-slate-200 dark:bg-white/[0.02] dark:border-white/[0.06] rounded-2xl overflow-hidden hover:border-cyan-500/15 hover:shadow-[0_16px_35px_rgba(6,182,212,0.1)] dark:hover:shadow-[0_16px_35px_rgba(0,0,0,0.5)] hover:-translate-y-1 transition-all"
    >
      {/* card header */}
      <div className="px-5 py-3.5 border-b border-slate-200 dark:border-white/[0.05] bg-slate-50 dark:bg-white/[0.01] flex justify-between items-start">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <div
              {...attributes}
              {...listeners}
              className="cursor-move p-1 hover:bg-slate-200 dark:hover:bg-white/[0.06] rounded-lg transition-colors"
            >
              <GripVertical className="w-4 h-4 text-slate-400 dark:text-white/20" />
            </div>
            <span className="px-2 py-0.5 bg-cyan-500/[0.08] text-cyan-400 text-[10px] rounded-full uppercase tracking-wider font-semibold border border-cyan-500/15">
              Chart
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-white/30 italic truncate pl-8">
            &ldquo;{chart.prompt}&rdquo;
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => submitChartFeedback("up")}
            disabled={isSavingFeedback}
            className="text-emerald-500 hover:text-emerald-600 p-2 hover:bg-emerald-500/[0.08] rounded-lg transition-all disabled:opacity-50"
            title="Good chart"
          >
            <ThumbsUp className="w-4 h-4" />
          </button>
          <button
            onClick={() => submitChartFeedback("down", true)}
            disabled={isSavingFeedback}
            className="text-red-500 hover:text-red-600 p-2 hover:bg-red-500/[0.08] rounded-lg transition-all disabled:opacity-50"
            title="Needs improvement"
          >
            <ThumbsDown className="w-4 h-4" />
          </button>
          <button
            onClick={() => submitChartFeedback("improve", true)}
            disabled={isSavingFeedback}
            className="text-amber-500 hover:text-amber-600 p-2 hover:bg-amber-500/[0.08] rounded-lg transition-all disabled:opacity-50"
            title="Tune colors or style"
          >
            <Palette className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => onDelete(chart.id)}
            disabled={isDeleting}
            aria-label="Delete chart"
            title="Delete chart"
            className="text-slate-400 dark:text-white/30 hover:text-red-500 p-2 hover:bg-red-500/[0.08] rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isDeleting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
      {/* chart body */}
      <div className="p-4">
        {feedbackSaved && (
          <p className="mb-2 text-[11px] font-semibold text-emerald-500">
            Feedback saved and used for future chart styling.
          </p>
        )}
        {chart.config ? (
          <AIGeneratedChart config={chart.config} />
        ) : (
          <div className="text-red-400/60 p-4 text-center text-sm">
            Invalid chart data
          </div>
        )}
      </div>
    </div>
    </motion.div>
  );
}

function ChartSkeleton({ prompt }: { prompt: string }) {
  return (
    <div className="group bg-[var(--card-bg)] rounded-2xl border border-[var(--skeleton-border)] overflow-hidden relative shadow-[0_8px_32px_rgba(0,0,0,0.12)] dark:shadow-[0_8px_32px_rgba(0,0,0,0.4)] transition-colors duration-300">
      {/* card header */}
      <div className="px-5 py-3.5 border-b border-[var(--skeleton-border)] bg-gradient-to-b from-[var(--skeleton-highlight)]/30 to-transparent flex justify-between items-start">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <div
              className="w-6 h-6 rounded-lg skeleton-shimmer skeleton-shimmer-delay-1"
              style={{ background: "var(--skeleton-bg)" }}
            />
            <div
              className="w-16 h-5 rounded-full skeleton-shimmer skeleton-shimmer-delay-2"
              style={{ background: "var(--skeleton-bg)" }}
            />
          </div>
          {prompt ? (
            <p className="text-xs text-[var(--skeleton-text)] italic truncate pl-8">
              &ldquo;{prompt}&rdquo;
            </p>
          ) : (
            <div
              className="h-3.5 w-48 rounded ml-8 mt-1 skeleton-shimmer skeleton-shimmer-delay-1"
              style={{ background: "var(--skeleton-bg)" }}
            />
          )}
        </div>
      </div>

      {/* chart body skeleton */}
      <div className="p-6 h-[400px] flex flex-col relative">
        {/* Y-axis labels and grid lines */}
        <div className="absolute inset-0 px-6 py-6 pb-14 flex flex-col justify-between z-0">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center w-full gap-3">
              <div
                className={`w-6 h-2 rounded skeleton-shimmer skeleton-shimmer-delay-${i}`}
                style={{ background: "var(--skeleton-bg)" }}
              />
              <div
                className="flex-1 border-b border-dashed"
                style={{ borderColor: "var(--skeleton-grid)" }}
              />
            </div>
          ))}
        </div>

        {/* X & Y Axis lines */}
        <div
          className="absolute left-[3.25rem] top-6 bottom-14 border-l z-0"
          style={{ borderColor: "var(--skeleton-axis)" }}
        />
        <div
          className="absolute left-[3.25rem] right-6 bottom-14 border-b z-0"
          style={{ borderColor: "var(--skeleton-axis)" }}
        />

        {/* Bars Container */}
        <div className="absolute left-[3.25rem] right-6 bottom-14 top-6 flex items-end justify-around px-4 z-10 gap-2">
          {/* Group 1 */}
          <div className="flex items-end gap-1 h-full w-full justify-center">
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[40%] skeleton-shimmer skeleton-shimmer-delay-1 shadow-[0_0_15px_rgba(34,211,238,0.15)] dark:shadow-[0_0_15px_rgba(34,211,238,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-cyan-start), var(--skeleton-bar-cyan-end))",
              }}
            />
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[60%] skeleton-shimmer skeleton-shimmer-delay-2 shadow-[0_0_15px_rgba(192,132,252,0.15)] dark:shadow-[0_0_15px_rgba(192,132,252,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-purple-start), var(--skeleton-bar-purple-end))",
              }}
            />
          </div>
          {/* Group 2 */}
          <div className="flex items-end gap-1 h-full w-full justify-center">
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[70%] skeleton-shimmer skeleton-shimmer-delay-3 shadow-[0_0_15px_rgba(34,211,238,0.15)] dark:shadow-[0_0_15px_rgba(34,211,238,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-cyan-start), var(--skeleton-bar-cyan-end))",
              }}
            />
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[30%] skeleton-shimmer skeleton-shimmer-delay-4 shadow-[0_0_15px_rgba(192,132,252,0.15)] dark:shadow-[0_0_15px_rgba(192,132,252,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-purple-start), var(--skeleton-bar-purple-end))",
              }}
            />
          </div>
          {/* Group 3 */}
          <div className="flex items-end gap-1 h-full w-full justify-center">
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[50%] skeleton-shimmer skeleton-shimmer-delay-5 shadow-[0_0_15px_rgba(34,211,238,0.15)] dark:shadow-[0_0_15px_rgba(34,211,238,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-cyan-start), var(--skeleton-bar-cyan-end))",
              }}
            />
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[90%] skeleton-shimmer skeleton-shimmer-delay-6 shadow-[0_0_15px_rgba(192,132,252,0.15)] dark:shadow-[0_0_15px_rgba(192,132,252,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-purple-start), var(--skeleton-bar-purple-end))",
              }}
            />
          </div>
          {/* Group 4 */}
          <div className="flex items-end gap-1 h-full w-full justify-center">
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[80%] skeleton-shimmer skeleton-shimmer-delay-2 shadow-[0_0_15px_rgba(34,211,238,0.15)] dark:shadow-[0_0_15px_rgba(34,211,238,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-cyan-start), var(--skeleton-bar-cyan-end))",
              }}
            />
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[40%] skeleton-shimmer skeleton-shimmer-delay-3 shadow-[0_0_15px_rgba(192,132,252,0.15)] dark:shadow-[0_0_15px_rgba(192,132,252,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-purple-start), var(--skeleton-bar-purple-end))",
              }}
            />
          </div>
          {/* Group 5 */}
          <div className="flex items-end gap-1 h-full w-full justify-center">
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[30%] skeleton-shimmer skeleton-shimmer-delay-4 shadow-[0_0_15px_rgba(34,211,238,0.15)] dark:shadow-[0_0_15px_rgba(34,211,238,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-cyan-start), var(--skeleton-bar-cyan-end))",
              }}
            />
            <div
              className="w-full max-w-[20px] rounded-t-sm h-[65%] skeleton-shimmer skeleton-shimmer-delay-5 shadow-[0_0_15px_rgba(192,132,252,0.15)] dark:shadow-[0_0_15px_rgba(192,132,252,0.2)]"
              style={{
                background:
                  "linear-gradient(to top, var(--skeleton-bar-purple-start), var(--skeleton-bar-purple-end))",
              }}
            />
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 left-0 right-0 flex justify-center gap-6 z-10">
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-sm animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.4)] dark:shadow-[0_0_8px_rgba(34,211,238,0.5)]"
              style={{ background: "var(--skeleton-bar-cyan-end)" }}
            />
            <div
              className="w-12 h-2 rounded skeleton-shimmer skeleton-shimmer-delay-1"
              style={{ background: "var(--skeleton-bg)" }}
            />
          </div>
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-sm animate-pulse shadow-[0_0_8px_rgba(192,132,252,0.4)] dark:shadow-[0_0_8px_rgba(192,132,252,0.5)]"
              style={{ background: "var(--skeleton-bar-purple-end)" }}
            />
            <div
              className="w-12 h-2 rounded skeleton-shimmer skeleton-shimmer-delay-2"
              style={{ background: "var(--skeleton-bg)" }}
            />
          </div>
        </div>
      </div>

      {/* Status Overlay */}
      <div className="absolute inset-0 flex flex-col items-center justify-center z-20 bg-black/20 dark:bg-black/40 backdrop-blur-[2px]">
        <div className="bg-[var(--card-bg)]/95 border border-cyan-500/30 px-6 py-4 rounded-2xl flex flex-col items-center gap-3 status-glow relative overflow-hidden">
          <div
            className="absolute inset-0 skeleton-shimmer opacity-50"
            style={{
              background:
                "linear-gradient(90deg, transparent, rgba(34,211,238,0.1), transparent)",
            }}
          />
          <div className="flex items-center gap-3 relative z-10">
            <Loader2 className="w-5 h-5 text-cyan-500 dark:text-cyan-400 animate-spin" />
            <span className="text-xs font-mono text-cyan-600 dark:text-cyan-400 tracking-widest font-bold">
              CRAFTING CHART...
            </span>
          </div>
          <p className="text-[10px] text-slate-500 dark:text-white/40 font-mono relative z-10 uppercase">
            Analyzing Data
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ChartGallery() {
  const { selectedIngestion } = useIngestion();
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [orderedIds, setOrderedIds] = useState<string[]>([]);
  const [generatingPrompts, setGeneratingPrompts] = useState<string[]>([]);
  // Charts already rendered from the generator's own response, still awaiting
  // confirmation from the next history fetch. They are dropped the moment the
  // server list contains them, so a chart is never shown twice.
  const [pendingCharts, setPendingCharts] = useState<Chart[]>([]);
  // Ids removed locally that the server list may still be carrying (its
  // response was in flight, or a cached copy is being replayed).
  const [deletedIds, setDeletedIds] = useState<string[]>([]);
  const [deletingIds, setDeletingIds] = useState<string[]>([]);
  const fallbackCharts = selectedIngestion
    ? chartsCacheByIngestion.get(selectedIngestion)
    : undefined;

  const {
    data: charts,
    error,
    isLoading,
    mutate,
  } = useSWR(
    selectedIngestion ? ["charts", selectedIngestion] : null,
    () => fetchCharts(selectedIngestion!),
    {
      fallbackData: fallbackCharts,
      keepPreviousData: true,
      dedupingInterval: 8000,
      refreshInterval: 20000,
      refreshWhenHidden: false,
      revalidateOnFocus: true,
    },
  );

  useEffect(() => {
    if (!selectedIngestion || !charts) return;
    chartsCacheByIngestion.set(selectedIngestion, charts as Chart[]);
  }, [selectedIngestion, charts]);

  // Warm the Plotly chunk while the gallery is idle. Without this the first
  // chart of a session pays a multi-megabyte download only AFTER its data has
  // arrived — the part of the wait that used to happen with nothing on screen.
  useEffect(() => schedulePlotlyPreload(), []);

  useEffect(() => {
    const handleStart = (event: Event) => {
      const prompt = String(readEventDetail(event).prompt || "");
      if (!prompt) return;
      setGeneratingPrompts((prev) => [...prev, prompt]);
    };
    const handleGenerated = (event: Event) => {
      const { prompt, chart, chartId } = readEventDetail(event);
      const promptText = String(prompt || "");
      const config = parseChartConfig(chart);

      if (config) {
        // Render straight from the generator's response. The placeholder is
        // only retired once its replacement is in the list, so the two hand
        // over in the same commit and the card never blinks out of existence.
        setPendingCharts((prev) => [
          {
            id: chartId || `pending:${promptText}:${Date.now()}`,
            prompt: promptText || "Chart",
            config,
            created_at: new Date().toISOString(),
          },
          // Confirmed entries are filtered out at render time; the cap is
          // only here so a long session can't accumulate them forever.
          ...prev.filter((c) => c.prompt !== promptText).slice(0, 5),
        ]);
      }

      setGeneratingPrompts((prev) => prev.filter((p) => p !== promptText));
      // Reconcile with the server in the background; the chart is already up.
      mutate();
    };
    const handleFailed = (event: Event) => {
      const prompt = String(readEventDetail(event).prompt || "");
      setGeneratingPrompts((prev) => prev.filter((p) => p !== prompt));
    };

    window.addEventListener("chart-generating-start", handleStart);
    window.addEventListener("chart-generated", handleGenerated);
    window.addEventListener("chart-generation-failed", handleFailed);

    return () => {
      window.removeEventListener("chart-generating-start", handleStart);
      window.removeEventListener("chart-generated", handleGenerated);
      window.removeEventListener("chart-generation-failed", handleFailed);
    };
  }, [mutate]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDelete = async (id: string) => {
    if (!selectedIngestion || deletingIds.includes(id)) return;

    setDeletingIds((prev) => [...prev, id]);
    // Tombstone first. A chart lives in three places at once (the SWR list,
    // the module cache, and `pendingCharts`); removing it from one still
    // leaves the other two able to put it back, so the id is filtered at
    // render time until the server list stops carrying it.
    setDeletedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setPendingCharts((prev) => prev.filter((c) => c.id !== id));

    const dropped = (list?: Chart[]) => (list || []).filter((c) => c.id !== id);
    chartsCacheByIngestion.set(selectedIngestion, dropped(charts as Chart[] | undefined));

    try {
      // Optimistic: the card disappears on click, and the revalidation that
      // follows only ever confirms it.
      await mutate(deleteChart(id, selectedIngestion).then(() => dropped(charts as Chart[] | undefined)), {
        optimisticData: dropped(charts as Chart[] | undefined),
        rollbackOnError: true,
        revalidate: true,
      });
    } catch (err) {
      setDeletedIds((prev) => prev.filter((d) => d !== id));
      chartsCacheByIngestion.set(selectedIngestion, (charts as Chart[]) || []);
      alert(err instanceof Error ? err.message : "Failed to delete chart");
    } finally {
      setDeletingIds((prev) => prev.filter((d) => d !== id));
    }
  };

  // A tombstone is retired once the server agrees the chart is gone, so the
  // list can't grow without bound across a long session.
  useEffect(() => {
    if (!deletedIds.length || !charts) return;
    const serverIds = new Set((charts as Chart[]).map((c) => c.id));
    const stillPresent = deletedIds.filter((id) => serverIds.has(id));
    if (stillPresent.length !== deletedIds.length) setDeletedIds(stillPresent);
  }, [charts, deletedIds]);

  // A pending chart is superseded as soon as the server's list carries the
  // same chart — by id when the backend returned one, otherwise by prompt.
  // Matching on prompt alone would be wrong for a re-run of the same prompt,
  // so the id is preferred whenever it exists.
  const unconfirmedPending = useMemo(() => {
    const source = charts || [];
    if (!pendingCharts.length) return [];
    const serverIds = new Set(source.map((c) => c.id));
    const serverPrompts = new Set(source.map((c) => c.prompt));
    return pendingCharts.filter((p) =>
      p.id.startsWith("pending:") ? !serverPrompts.has(p.prompt) : !serverIds.has(p.id),
    );
  }, [charts, pendingCharts]);

  const chartList = useMemo(() => {
    const deleted = new Set(deletedIds);
    const source = [...unconfirmedPending, ...(charts || [])].filter((c) => !deleted.has(c.id));
    if (!source.length || !orderedIds.length) return source;

    const byId = new Map(source.map((c) => [c.id, c]));
    const orderedExisting = orderedIds
      .map((id) => byId.get(id))
      .filter((c): c is Chart => Boolean(c));
    const seen = new Set(orderedExisting.map((c) => c.id));
    const newItems = source.filter((c) => !seen.has(c.id));
    return [...newItems, ...orderedExisting];
  }, [charts, orderedIds, unconfirmedPending, deletedIds]);

  if (isLoading)
    return (
      <div className="text-center py-16 text-slate-500 dark:text-white/25 text-sm">
        Loading gallery...
      </div>
    );

  if (error) {
    return (
      <div className="text-red-400/80 p-4 border border-red-500/20 rounded-xl bg-red-500/[0.04] text-sm">
        Error loading charts: {String(error)}
      </div>
    );
  }

  if (chartList.length === 0 && generatingPrompts.length === 0) {
    return (
      <div className="text-center py-20">
        <Sparkles className="w-10 h-10 mx-auto mb-4 text-cyan-500/20" />
        <p className="text-slate-500 dark:text-white/25 text-sm">
          No charts yet. Generate one using the chart generator!
        </p>
      </div>
    );
  }

  return (
    <div>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex justify-between items-center mb-6"
      >
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">
          Chart Gallery{" "}
          <span className="text-sm font-normal text-slate-500 dark:text-white/25">
            ({chartList.length})
          </span>
        </h2>
        <div className="relative flex bg-slate-100 dark:bg-white/[0.03] p-1 rounded-xl border border-slate-200 dark:border-white/[0.06]">
          <button
            onClick={() => setLayout("grid")}
            className={`relative z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              layout === "grid"
                ? "text-white"
                : "text-slate-500 hover:text-slate-700 dark:text-white/30 dark:hover:text-white/50"
            }`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Grid
          </button>
          <button
            onClick={() => setLayout("list")}
            className={`relative z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              layout === "list"
                ? "text-white"
                : "text-slate-500 hover:text-slate-700 dark:text-white/30 dark:hover:text-white/50"
            }`}
          >
            <List className="w-3.5 h-3.5" />
            List
          </button>
          {/* sliding active-pill indicator, shared layoutId animates the
              swap between grid/list instead of the color just snapping */}
          <motion.div
            layout
            layoutId="chart-gallery-layout-pill"
            transition={{ type: "spring", stiffness: 400, damping: 32 }}
            className="absolute top-1 bottom-1 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 shadow-[0_0_12px_rgba(0,240,255,0.15)]"
            style={
              layout === "grid"
                ? { left: 4, width: "calc(50% - 6px)" }
                : { left: "calc(50% + 2px)", width: "calc(50% - 6px)" }
            }
          />
        </div>
      </motion.div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={({ active, over }) => {
          if (over && active.id !== over.id) {
            const oldIndex = chartList.findIndex(
              (item: Chart) => item.id === active.id,
            );
            const newIndex = chartList.findIndex(
              (item: Chart) => item.id === over.id,
            );
            const newOrder = arrayMove(chartList, oldIndex, newIndex);
            setOrderedIds(newOrder.map((c) => c.id));
          }
        }}
      >
        <SortableContext
          items={chartList.map((c) => c.id)}
          strategy={
            layout === "grid"
              ? rectSortingStrategy
              : verticalListSortingStrategy
          }
        >
          <div
            className={
              layout === "grid"
                ? "grid grid-cols-1 md:grid-cols-2 gap-6"
                : "space-y-4"
            }
          >
            {generatingPrompts.map((prompt, i) => (
              <ChartSkeleton key={`skeleton-${i}`} prompt={prompt} />
            ))}
            {chartList.map((chart: Chart) => (
              <SortableItem
                key={chart.id}
                chart={chart}
                onDelete={handleDelete}
                isDeleting={deletingIds.includes(chart.id)}
                ingestionId={selectedIngestion ?? undefined}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
