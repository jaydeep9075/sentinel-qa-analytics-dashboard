"use client";
import { useRB } from "@/lib/RBContext";
import { FolderOpen, ChevronDown } from "lucide-react";

export default function ProjectSelector() {
  const { projects, selectedProject, setSelectedProject, loading } = useRB();
  if (loading)
    return <div className="text-[10px] text-slate-500 dark:text-white/20 uppercase tracking-widest">Loading projects...</div>;
  if (projects.length === 0) return null;

  return (
    <div className="relative flex items-center gap-1.5">
      <FolderOpen className="w-3.5 h-3.5 text-purple-500/50" />
      <select
        value={selectedProject || ""}
        onChange={(e) => setSelectedProject(e.target.value)}
        className="appearance-none bg-white border border-slate-300 rounded-lg px-3 py-1.5 pr-8 text-xs text-slate-700 hover:border-purple-500/30 focus:outline-none focus:border-purple-500/40 focus:ring-1 focus:ring-purple-500/20 transition-all cursor-pointer dark:bg-white/[0.03] dark:border-white/[0.08] dark:text-white/60 dark:hover:border-purple-500/20 dark:focus:border-purple-500/30"
      >
        <option value="" className="bg-white text-slate-700 dark:bg-black dark:text-white">No Project</option>
        {projects.map((p) => (
          <option key={p} value={p} className="bg-white text-slate-700 dark:bg-black dark:text-white">
            {p}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 dark:text-white/20 pointer-events-none" />
    </div>
  );
}
