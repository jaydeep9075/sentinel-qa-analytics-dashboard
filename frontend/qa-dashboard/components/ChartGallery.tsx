"use client";

import { useEffect, useState } from "react";
import { getGeneratedCharts, deleteChart } from "@/lib/api";
import AIGeneratedChart from "./AIGeneratedChart";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
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
  chart_type: string;
  config: any;
  created_at: string;
}

interface SortableItemProps {
  chart: Chart;
  onDelete: (id: string) => void;
}

function SortableItem({ chart, onDelete }: SortableItemProps) {
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
      className={`bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden hover:border-blue-500/50 transition-all ${
        isDragging ? "shadow-2xl shadow-blue-500/20" : ""
      }`}
    >
      <div className="p-4 border-b border-[#2a2a2a] bg-[#0f0f0f]">
        <div className="flex justify-between items-start">
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 mb-2">
              <div
                {...attributes}
                {...listeners}
                className="cursor-move p-1 hover:bg-[#2a2a2a] rounded-lg transition-colors"
              >
                <svg
                  className="h-5 w-5 text-gray-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 8h16M4 16h16"
                  />
                </svg>
              </div>
              <span className="inline-block px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full">
                {chart.chart_type}
              </span>
            </div>
            <p className="text-sm text-gray-400 italic truncate">
              "{chart.prompt}"
            </p>
            <p className="text-xs text-gray-600 mt-1">
              {new Date(chart.created_at).toLocaleString()}
            </p>
          </div>
          <button
            onClick={() => onDelete(chart.id)}
            className="text-gray-500 hover:text-red-400 p-2 hover:bg-red-500/10 rounded-lg transition-all"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </div>
      </div>
      <div className="p-4">
        <AIGeneratedChart config={chart.config} />
      </div>
    </div>
  );
}

export default function ChartGallery() {
  const [charts, setCharts] = useState<Chart[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [layout, setLayout] = useState<"grid" | "list">("grid");

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  useEffect(() => {
    fetchCharts();
  }, []);

  const fetchCharts = async () => {
    try {
      const response = await getGeneratedCharts();
      setCharts(response.data.charts || []);
    } catch (err) {
      setError("Failed to load charts");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteChart(id);
      setCharts(charts.filter((chart) => chart.id !== id));
    } catch (err) {
      setError("Failed to delete chart");
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setCharts((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id);
        const newIndex = items.findIndex((item) => item.id === over.id);
        return arrayMove(items, oldIndex, newIndex);
      });
    }
  };

  if (loading) {
    return (
      <div className="text-center py-16">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        <p className="mt-4 text-gray-400">Loading gallery...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-6 py-4 rounded-xl">
        {error}
      </div>
    );
  }

  if (charts.length === 0) {
    return (
      <div className="text-center py-16 bg-[#1a1a1a] rounded-xl border border-[#2a2a2a]">
        <svg
          className="mx-auto h-16 w-16 text-gray-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
          />
        </svg>
        <h3 className="mt-4 text-lg font-medium text-gray-300">
          No charts generated yet
        </h3>
        <p className="mt-2 text-gray-500">
          Try asking the AI to create some visualizations!
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 space-y-4 sm:space-y-0">
        <h2 className="text-xl sm:text-2xl font-bold text-white">
          Chart Gallery
          <span className="ml-2 text-sm font-normal text-gray-500">
            ({charts.length} charts)
          </span>
        </h2>

        {/* Layout Toggle */}
        <div className="flex items-center space-x-2 bg-[#1a1a1a] p-1 rounded-lg border border-[#2a2a2a]">
          <button
            onClick={() => setLayout("grid")}
            className={`p-2 rounded-lg transition-all ${
              layout === "grid"
                ? "bg-blue-500 text-white"
                : "text-gray-400 hover:text-white hover:bg-[#2a2a2a]"
            }`}
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
              />
            </svg>
          </button>
          <button
            onClick={() => setLayout("list")}
            className={`p-2 rounded-lg transition-all ${
              layout === "list"
                ? "bg-blue-500 text-white"
                : "text-gray-400 hover:text-white hover:bg-[#2a2a2a]"
            }`}
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
        </div>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={charts.map((c) => c.id)}
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
            {charts.map((chart) => (
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
