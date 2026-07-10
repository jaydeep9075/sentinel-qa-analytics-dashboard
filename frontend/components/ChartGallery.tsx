"use client";

import { useState, useEffect, useMemo } from "react";
import useSWR from "swr";
import { getChartHistory, deleteChart } from "@/lib/api";
import { useIngestion } from "@/lib/IngestionContext";
import AIGeneratedChart from "./AIGeneratedChart";
import {
  LayoutGrid,
  List,
  Trash2,
  GripVertical,
  Sparkles,
  Loader2,
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

const fetchCharts = async (ingestionId: string) => {
  const sessionId = "__all__";
  console.log("📊 fetchCharts using sessionId:", sessionId);
  const response = (await getChartHistory(sessionId, ingestionId)) as
    | ChartHistoryResponse
    | ChartHistoryItem[];
  console.log("📊 fetchCharts - full response:", response);

  let historyArray = (response as ChartHistoryResponse).history;
  if (!historyArray && Array.isArray(response)) {
    historyArray = response;
  }

  console.log("📊 fetchCharts - historyArray:", historyArray);

  if (!Array.isArray(historyArray)) {
    console.error("❌ historyArray is not an array:", historyArray);
    return [];
  }

  const charts = historyArray.map((item: ChartHistoryItem) => {
    console.log("📊 Processing chart item:", item);
    let parsedConfig;
    try {
      parsedConfig =
        typeof item.config === "string" ? JSON.parse(item.config) : item.config;
    } catch (e) {
      console.error("❌ Failed to parse chart config:", e);
      parsedConfig = null;
    }
    return {
      id: item.id,
      prompt: item.prompt || "Chart",
      config: parsedConfig,
      created_at: item.created_at,
    };
  });

  console.log("📊 fetchCharts - returning charts:", charts);
  return charts;
};

function SortableItem({
  chart,
  onDelete,
}: {
  chart: Chart;
  onDelete: (id: string) => void;
}) {
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

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="group bg-white border border-slate-200 dark:bg-white/[0.02] dark:border-white/[0.06] rounded-2xl overflow-hidden hover:border-cyan-500/15 transition-all"
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
        <button
          onClick={() => onDelete(chart.id)}
          className="text-slate-400 dark:text-white/15 hover:text-red-400 p-2 hover:bg-red-500/[0.08] rounded-lg transition-all"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
      {/* chart body */}
      <div className="p-4">
        {chart.config ? (
          <AIGeneratedChart config={chart.config} />
        ) : (
          <div className="text-red-400/60 p-4 text-center text-sm">
            Invalid chart data
          </div>
        )}
      </div>
    </div>
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

  const {
    data: charts,
    error,
    isLoading,
    mutate,
  } = useSWR(
    selectedIngestion ? ["charts", selectedIngestion] : null,
    () => fetchCharts(selectedIngestion!),
    {
      refreshInterval: 5000,
      onSuccess: (data) => console.log("📊 SWR onSuccess - charts:", data),
      onError: (err) => console.error("❌ SWR onError:", err),
    },
  );

  useEffect(() => {
    const handleStart = (event: Event) => {
      const e = event as CustomEvent<string>;
      const detail = String(e.detail || "");
      if (!detail) return;
      setGeneratingPrompts((prev) => [...prev, detail]);
    };
    const handleEnd = (event: Event) => {
      const e = event as CustomEvent<string>;
      const detail = String(e.detail || "");
      setGeneratingPrompts((prev) => prev.filter((p) => p !== detail));
      mutate();
    };

    window.addEventListener("chart-generating-start", handleStart);
    window.addEventListener("chart-generating-end", handleEnd);

    return () => {
      window.removeEventListener("chart-generating-start", handleStart);
      window.removeEventListener("chart-generating-end", handleEnd);
    };
  }, [mutate]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDelete = async (id: string) => {
    if (!selectedIngestion) return;
    try {
      await deleteChart(id, selectedIngestion);
      mutate();
    } catch {
      alert("Failed to delete chart");
    }
  };

  const chartList = useMemo(() => {
    const source = charts || [];
    if (!source.length || !orderedIds.length) return source;

    const byId = new Map(source.map((c) => [c.id, c]));
    const orderedExisting = orderedIds
      .map((id) => byId.get(id))
      .filter((c): c is Chart => Boolean(c));
    const seen = new Set(orderedExisting.map((c) => c.id));
    const newItems = source.filter((c) => !seen.has(c.id));
    return [...newItems, ...orderedExisting];
  }, [charts, orderedIds]);

  if (isLoading)
    return (
      <div className="text-center py-16 text-slate-500 dark:text-white/25 text-sm">
        Loading gallery...
      </div>
    );

  if (error) {
    console.error("❌ Chart gallery error:", error);
    return (
      <div className="text-red-400/80 p-4 border border-red-500/20 rounded-xl bg-red-500/[0.04] text-sm">
        Error loading charts: {String(error)}
      </div>
    );
  }

  console.log(
    "📊 Rendering ChartGallery - chartList length:",
    chartList.length,
  );

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
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">
          Chart Gallery{" "}
          <span className="text-sm font-normal text-slate-500 dark:text-white/25">
            ({chartList.length})
          </span>
        </h2>
        <div className="flex bg-slate-100 dark:bg-white/[0.03] p-1 rounded-xl border border-slate-200 dark:border-white/[0.06]">
          <button
            onClick={() => setLayout("grid")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              layout === "grid"
                ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_12px_rgba(0,240,255,0.15)]"
                : "text-slate-500 hover:text-slate-700 dark:text-white/30 dark:hover:text-white/50"
            }`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Grid
          </button>
          <button
            onClick={() => setLayout("list")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              layout === "list"
                ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_12px_rgba(0,240,255,0.15)]"
                : "text-slate-500 hover:text-slate-700 dark:text-white/30 dark:hover:text-white/50"
            }`}
          >
            <List className="w-3.5 h-3.5" />
            List
          </button>
        </div>
      </div>

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
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
