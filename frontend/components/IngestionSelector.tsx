"use client";
import { useIngestion } from "@/lib/IngestionContext";
import { Database, ChevronDown } from "lucide-react";

export default function IngestionSelector() {
  const { ingestions, selectedIngestion, setSelectedIngestion, loading } =
    useIngestion();

  if (loading) return <div className="text-[10px] text-slate-500 dark:text-white/20 uppercase tracking-widest">Loading...</div>;
  if (ingestions.length === 0) return null;

  return (
    <div className="relative flex items-center gap-1.5">
      <Database className="w-3.5 h-3.5 text-cyan-500/50" />
      <select
        value={selectedIngestion || ""}
        onChange={(e) => setSelectedIngestion(e.target.value)}
        className="appearance-none bg-white border border-slate-300 rounded-lg px-3 py-1.5 pr-8 text-xs text-slate-700 hover:border-cyan-500/30 focus:outline-none focus:border-cyan-500/40 focus:ring-1 focus:ring-cyan-500/20 transition-all cursor-pointer dark:bg-white/[0.03] dark:border-white/[0.08] dark:text-white/60 dark:hover:border-cyan-500/20 dark:focus:border-cyan-500/30"
      >
        {ingestions.map((ing) => (
          <option key={ing.id} value={ing.id} className="bg-white text-slate-700 dark:bg-black dark:text-white">
            {ing.build_label}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 dark:text-white/20 pointer-events-none" />
    </div>
  );
}
