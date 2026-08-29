"use client";
import { useRB } from "@/lib/RBContext";
import { FolderOpen, ChevronDown } from "lucide-react";

/**
 * The active project, and the control that changes it.
 *
 * A project is the data boundary: builds, charts and chat answers all belong
 * to exactly one. So there is no "No Project" option any more — an unscoped
 * dashboard was a dashboard showing every project's builds in one list, which
 * is the thing projects exist to prevent.
 *
 * With a single project there is nothing to switch between, so it renders as
 * a label rather than a dropdown that can only be set to what it already is.
 */
export default function ProjectSelector() {
  const { projects, projectItems, selectedProject, setSelectedProject, loading } = useRB();

  const byId = new Map(projectItems.map((item) => [item.project_id.toLowerCase(), item]));
  const rootProjects = projects.filter((project) => {
    const item = byId.get(project.toLowerCase());
    return !item?.parent_project_id;
  });
  const subProjectsByParent = new Map<string, string[]>();
  for (const project of projects) {
    const item = byId.get(project.toLowerCase());
    const parent = item?.parent_project_id;
    if (!parent) continue;
    const key = parent.toLowerCase();
    const list = subProjectsByParent.get(key) || [];
    list.push(project);
    subProjectsByParent.set(key, list);
  }

  const orderedProjects = [
    ...rootProjects,
    ...projects.filter((project) => {
      const item = byId.get(project.toLowerCase());
      const parent = String(item?.parent_project_id || "").trim();
      return parent && !projects.some((p) => p.toLowerCase() === parent.toLowerCase());
    }),
  ];

  if (loading) {
    return (
      <div className="shrink-0 text-[10px] uppercase tracking-widest text-slate-500 dark:text-white/20">
        Loading projects...
      </div>
    );
  }

  if (projects.length === 0) return null;

  if (projects.length === 1) {
    return (
      <span
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white/70"
        title="Active project"
      >
        <FolderOpen className="h-3.5 w-3.5 text-purple-500" />
        {selectedProject || projects[0]}
      </span>
    );
  }

  return (
    <div className="relative flex shrink-0 items-center gap-1.5">
      <FolderOpen className="h-3.5 w-3.5 text-purple-500/60" />
      <select
        value={selectedProject || ""}
        onChange={(e) => setSelectedProject(e.target.value)}
        title="Active project — builds and answers are scoped to it"
        aria-label="Active project"
        className="cursor-pointer appearance-none rounded-lg border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-700 transition-all hover:border-purple-500/30 focus:border-purple-500/40 focus:outline-none focus:ring-1 focus:ring-purple-500/20 dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white/60 dark:hover:border-purple-500/20 dark:focus:border-purple-500/30"
      >
        {orderedProjects.map((project) => {
          const children = subProjectsByParent.get(project.toLowerCase()) || [];
          const optionRows = [
            <option key={project} value={project} className="bg-white text-slate-700 dark:bg-black dark:text-white">
              {project}
            </option>,
            ...children
              .sort((a, b) => a.localeCompare(b))
              .map((child) => (
                <option
                  key={child}
                  value={child}
                  className="bg-white text-slate-700 dark:bg-black dark:text-white"
                >
                  {`  - ${child}`}
                </option>
              )),
          ];
          return optionRows;
        })}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-400 dark:text-white/20" />
    </div>
  );
}
