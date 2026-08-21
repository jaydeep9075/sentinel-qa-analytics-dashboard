"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderOpen, ArrowRight, FolderPlus, ShieldAlert } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { useRB } from "@/lib/RBContext";
import { usePermissions } from "@/lib/usePermissions";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * The project picker, and the first screen a brand-new install ever shows.
 *
 * Three states, and they are genuinely different problems:
 *
 *   1. Projects you can open - pick one.
 *   2. No projects exist at all - only reachable by an administrator on a
 *      fresh install. Bootstrapping is the *whole* job of this screen then,
 *      because an admin with no project has no other route to create one:
 *      the admin console's Projects tab sits behind a dashboard that refuses
 *      to render without a project.
 *   3. Projects exist but none are yours - nothing to do here but ask.
 *
 * Collapsing 2 and 3 into one "no projects" message is what leaves a first-run
 * admin staring at "contact an administrator" while being the administrator.
 */
export default function ProjectsPage() {
  const router = useRouter();
  const { projects, loading, selectedProject, setSelectedProject, refreshProjects } = useRB();
  const { permissions, loaded: permissionsLoaded } = usePermissions();
  const isAdmin = permissions.is_admin;

  const [newProjectId, setNewProjectId] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const sortedProjects = useMemo(
    () => [...projects].sort((a, b) => a.localeCompare(b)),
    [projects],
  );

  const openProject = useCallback(
    (project: string) => {
      setSelectedProject(project);
      router.push("/dashboard");
    },
    [router, setSelectedProject],
  );

  const createProject = useCallback(async () => {
    const projectId = newProjectId.trim();
    if (!projectId) return;

    setCreating(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API}/admin/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ project_id: projectId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to create project");

      setNewProjectId("");
      await refreshProjects();
      openProject(data.project || projectId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }, [newProjectId, openProject, refreshProjects]);

  const busy = loading || !permissionsLoaded;

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <AppHeader label="Projects" nav="none" />

      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {sortedProjects.length === 0 && isAdmin
              ? "Create your first project"
              : "Select a project"}
          </h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-white/50">
            A project owns its builds, charts and chat history. Everything in the dashboard is
            scoped to the project you open.
          </p>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-300/50 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/[0.08] dark:text-red-300">
            {error}
          </div>
        )}

        {busy ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 dark:border-white/[0.08] dark:bg-white/[0.02] dark:text-white/40">
            Loading projects...
          </div>
        ) : sortedProjects.length === 0 && isAdmin ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/[0.08] dark:bg-white/[0.02]">
            <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400">
              <FolderPlus className="h-4 w-4" />
            </div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">
              No projects yet
            </h2>
            <p className="mt-1 max-w-xl text-sm text-slate-600 dark:text-white/50">
              Name your first one - usually the product or storefront under test. Everyone who
              already has an account gets access to it, because on a fresh install the first project
              is the whole system. Later projects grant nothing implicitly; you assign those in
              Admin &rarr; Projects.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <input
                value={newProjectId}
                onChange={(e) => setNewProjectId(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") createProject();
                }}
                placeholder="e.g. FSA"
                className="w-56 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-cyan-500/50 dark:border-white/[0.12] dark:bg-white/[0.03] dark:text-white"
              />
              <button
                onClick={createProject}
                disabled={creating || !newProjectId.trim()}
                className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <FolderPlus className="h-4 w-4" />
                {creating ? "Creating..." : "Create project"}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500 dark:text-white/35">
              2-64 characters: letters, numbers, dot, underscore or hyphen.
            </p>
          </div>
        ) : sortedProjects.length === 0 ? (
          <div className="flex items-start gap-3 rounded-2xl border border-amber-300/40 bg-amber-50 p-6 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/[0.08] dark:text-amber-200">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold">No project has been assigned to your account.</p>
              <p className="mt-1 opacity-80">
                An administrator grants project access from Admin &rarr; Projects. Until then there
                is no data this account is allowed to open.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sortedProjects.map((project) => {
              const active = selectedProject === project;
              return (
                <button
                  key={project}
                  onClick={() => openProject(project)}
                  className="group rounded-2xl border border-slate-200 bg-white p-5 text-left transition-all hover:-translate-y-0.5 hover:border-cyan-500/40 dark:border-white/[0.08] dark:bg-white/[0.02]"
                >
                  <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400">
                    <FolderOpen className="h-4 w-4" />
                  </div>
                  <h2 className="truncate text-base font-semibold text-slate-900 dark:text-white">
                    {project}
                  </h2>
                  <p className="mt-1 text-xs text-slate-500 dark:text-white/40">
                    {active ? "Current project" : "Open project dashboard"}
                  </p>
                  <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-600 dark:text-cyan-400">
                    Open
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
