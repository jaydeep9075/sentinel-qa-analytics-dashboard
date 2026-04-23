"use client";
import { useRB } from "@/lib/RBContext";
import { FolderOpen, ChevronDown } from "lucide-react";

export default function ProjectSelector() {
  const { projects, selectedProject, setSelectedProject, loading } = useRB();
  if (loading)
    return <div className="text-[10px] text-white/20 uppercase tracking-widest">Loading projects...</div>;
  if (projects.length === 0) return null;

  return (
    <div className="relative flex items-center gap-1.5">
      <FolderOpen className="w-3.5 h-3.5 text-purple-500/50" />
      <select
        value={selectedProject || ""}
        onChange={(e) => setSelectedProject(e.target.value)}
        className="appearance-none bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-1.5 pr-8 text-xs text-white/60 hover:border-purple-500/20 focus:outline-none focus:border-purple-500/30 focus:ring-1 focus:ring-purple-500/20 transition-all cursor-pointer"
      >
        <option value="" className="bg-black text-white">No Project</option>
        {projects.map((p) => (
          <option key={p} value={p} className="bg-black text-white">
            {p}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-white/20 pointer-events-none" />
    </div>
  );
}
