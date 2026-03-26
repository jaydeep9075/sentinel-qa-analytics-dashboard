"use client";

import useSWR from 'swr';
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
import { useState } from 'react';

interface Chart {
  id: string;
  prompt: string;
  chart_type: string;
  config: any;
  created_at: string;
}

function SortableItem({ chart, onDelete }: { chart: Chart; onDelete: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: chart.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 999 : "auto",
  };

  return (
    <div ref={setNodeRef} style={style} className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden hover:border-blue-500/50 transition-all">
      <div className="p-4 border-b border-[#2a2a2a] bg-[#0f0f0f]">
        <div className="flex justify-between items-start">
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 mb-2">
              <div {...attributes} {...listeners} className="cursor-move p-1 hover:bg-[#2a2a2a] rounded-lg">
                <svg className="h-5 w-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8h16M4 16h16" />
                </svg>
              </div>
              <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full">{chart.chart_type || 'AI Chart'}</span>
            </div>
            <p className="text-sm text-gray-400 italic truncate">"{chart.prompt}"</p>
          </div>
          <button onClick={() => onDelete(chart.id)} className="text-gray-500 hover:text-red-400 p-2 hover:bg-red-500/10 rounded-lg">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
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
  const [layout, setLayout] = useState<"grid" | "list">("grid");

  // ✅ Efficiency: SWR handles fetching, error, and loading states automatically
  const { data: charts, error, isLoading, mutate } = useSWR('/ai/generated-charts', () =>
    getGeneratedCharts().then(res => res.data.charts || [])
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDelete = async (id: string) => {
    try {
      await deleteChart(id);
      mutate(charts?.filter((c: Chart) => c.id !== id), false); // Optimistic UI update
    } catch (err) {
      alert("Failed to delete chart");
    }
  };

  if (isLoading) return <div className="text-center py-16 text-gray-400">Loading gallery...</div>;
  if (error) return <div className="text-red-400 p-4 border border-red-500/30 rounded-xl">Error loading charts</div>;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-white">Chart Gallery <span className="text-sm font-normal text-gray-500">({charts?.length})</span></h2>
        <div className="flex space-x-2 bg-[#1a1a1a] p-1 rounded-lg border border-[#2a2a2a]">
          <button onClick={() => setLayout("grid")} className={`p-2 rounded-lg ${layout === "grid" ? "bg-blue-500" : "text-gray-400"}`}>Grid</button>
          <button onClick={() => setLayout("list")} className={`p-2 rounded-lg ${layout === "list" ? "bg-blue-500" : "text-gray-400"}`}>List</button>
        </div>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => {
        if (over && active.id !== over.id) {
          const oldIndex = charts.findIndex((item: any) => item.id === active.id);
          const newIndex = charts.findIndex((item: any) => item.id === over.id);
          mutate(arrayMove(charts, oldIndex, newIndex), false);
        }
      }}>
        <SortableContext items={charts?.map((c: any) => c.id) || []} strategy={layout === "grid" ? rectSortingStrategy : verticalListSortingStrategy}>
          <div className={layout === "grid" ? "grid grid-cols-1 md:grid-cols-2 gap-6" : "space-y-4"}>
            {charts?.map((chart: Chart) => (
              <SortableItem key={chart.id} chart={chart} onDelete={handleDelete} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}