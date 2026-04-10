"use client";
import { useRB } from "@/lib/RBContext";

export default function ProjectSelector() {
  const { projects, selectedProject, setSelectedProject, loading } = useRB();
  if (loading)
    return <div className="text-xs text-gray-500">Loading projects...</div>;
  if (projects.length === 0) return null;

  return (
    <select
      value={selectedProject || ""}
      onChange={(e) => setSelectedProject(e.target.value)}
      className="bg-black/50 border border-white/10 rounded-lg px-3 py-1 text-sm ml-2"
    >
      <option value="">No Project</option>
      {projects.map((p) => (
        <option key={p} value={p}>
          {p}
        </option>
      ))}
    </select>
  );
}
