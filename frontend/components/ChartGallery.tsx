"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { getChartHistory, deleteChart } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import { useIngestion } from "@/lib/IngestionContext";
import AIGeneratedChart from "./AIGeneratedChart";
import { LayoutGrid, List, Trash2, GripVertical, Sparkles } from "lucide-react";
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
  config: any;
  created_at: string;
}

const fetchCharts = async (ingestionId: string) => {
  const sessionId = getSessionId();
  console.log("📊 fetchCharts using sessionId:", sessionId);
  const response = await getChartHistory(sessionId, ingestionId);
  console.log("📊 fetchCharts - full response:", response);

  let historyArray = response.history;
  if (!historyArray && Array.isArray(response)) {
    historyArray = response;
  }

  console.log("📊 fetchCharts - historyArray:", historyArray);

  if (!Array.isArray(historyArray)) {
    console.error("❌ historyArray is not an array:", historyArray);
    return [];
  }

  const charts = historyArray.map((item: any) => {
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
      className="group bg-white/[0.02] rounded-2xl border border-white/[0.06] overflow-hidden hover:border-cyan-500/15 transition-all"
    >
      {/* card header */}
      <div className="px-5 py-3.5 border-b border-white/[0.05] bg-white/[0.01] flex justify-between items-start">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <div
              {...attributes}
              {...listeners}
              className="cursor-move p-1 hover:bg-white/[0.06] rounded-lg transition-colors"
            >
              <GripVertical className="w-4 h-4 text-white/20" />
            </div>
            <span className="px-2 py-0.5 bg-cyan-500/[0.08] text-cyan-400 text-[10px] rounded-full uppercase tracking-wider font-semibold border border-cyan-500/15">
              Chart
            </span>
          </div>
          <p className="text-xs text-white/30 italic truncate pl-8">
            &ldquo;{chart.prompt}&rdquo;
          </p>
        </div>
        <button
          onClick={() => onDelete(chart.id)}
          className="text-white/15 hover:text-red-400 p-2 hover:bg-red-500/[0.08] rounded-lg transition-all"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
      {/* chart body */}
      <div className="p-4">
        {chart.config ? (
          <AIGeneratedChart config={chart.config} />
        ) : (
          <div className="text-red-400/60 p-4 text-center text-sm">Invalid chart data</div>
        )}
      </div>
    </div>
  );
}

export default function ChartGallery() {
  const { selectedIngestion } = useIngestion();
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [localOrder, setLocalOrder] = useState<Chart[]>([]);

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
    if (charts) {
      setLocalOrder((prev) => {
        if (prev.length === 0) return charts;
        
        const existingIds = new Set(prev.map((c) => c.id));
        const chartMap = new Map(charts.map((c) => [c.id, c]));
        
        const orderedExisting = prev
          .filter((c) => chartMap.has(c.id))
          .map((c) => chartMap.get(c.id)!);
          
        const newItems = charts.filter((c) => !existingIds.has(c.id));
        
        return [...newItems, ...orderedExisting];
      });
    }
  }, [charts]);

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
    } catch (err) {
      alert("Failed to delete chart");
    }
  };

  if (isLoading)
    return (
      <div className="text-center py-16 text-white/25 text-sm">Loading gallery...</div>
    );

  if (error) {
    console.error("❌ Chart gallery error:", error);
    return (
      <div className="text-red-400/80 p-4 border border-red-500/20 rounded-xl bg-red-500/[0.04] text-sm">
        Error loading charts: {String(error)}
      </div>
    );
  }

  const chartList = localOrder || [];
  console.log(
    "📊 Rendering ChartGallery - chartList length:",
    chartList.length,
  );

  if (chartList.length === 0) {
    return (
      <div className="text-center py-20">
        <Sparkles className="w-10 h-10 mx-auto mb-4 text-cyan-500/20" />
        <p className="text-white/25 text-sm">No charts yet. Generate one using the chart generator!</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold text-white">
          Chart Gallery{" "}
          <span className="text-sm font-normal text-white/25">
            ({chartList.length})
          </span>
        </h2>
        <div className="flex bg-white/[0.03] p-1 rounded-xl border border-white/[0.06]">
          <button
            onClick={() => setLayout("grid")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              layout === "grid"
                ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_12px_rgba(0,240,255,0.15)]"
                : "text-white/30 hover:text-white/50"
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
                : "text-white/30 hover:text-white/50"
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
            setLocalOrder(newOrder);
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
