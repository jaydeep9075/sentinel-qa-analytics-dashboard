"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, FolderPlus, RefreshCw, Save, Trash2, UsersRound } from "lucide-react";
import PageTransition from "@/components/PageTransition";
import { SkeletonRows } from "@/components/Skeleton";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Project administration: who may see which project, and which project owns
 * which build.
 *
 * The two questions are deliberately answered on one screen, because they are
 * the two halves of the same boundary — a user with access to a project sees
 * exactly the builds assigned to it, and nothing else. Splitting them across
 * screens is how installs end up with users granted a project that holds no
 * builds, and builds nobody can open.
 *
 * Nothing here is named after a particular customer's project. The earlier
 * version had "seed FSA access" and "migrate builds to FSA" buttons, which
 * work exactly once, on exactly one install.
 */

type AccessUser = {
  username: string;
  role: string;
  projects: string[];
};

type ProjectItem = {
  project_id: string;
  parent_project_id: string | null;
  is_subproject: boolean;
};

type BuildMapping = Record<string, string>;
type UserFilter = "all" | "no-access" | "multi";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", ...authHeaders() };
}

export default function AdminProjectsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [projects, setProjects] = useState<string[]>([]);
  const [projectItems, setProjectItems] = useState<ProjectItem[]>([]);
  const [users, setUsers] = useState<AccessUser[]>([]);
  const [mapping, setMapping] = useState<BuildMapping>({});
  const [unassignedBuilds, setUnassignedBuilds] = useState<string[]>([]);

  const [newProjectId, setNewProjectId] = useState("");
  const [newParentProjectId, setNewParentProjectId] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyProject, setBusyProject] = useState("");
  const [savingParentProject, setSavingParentProject] = useState("");
  const [parentDrafts, setParentDrafts] = useState<Record<string, string>>({});

  const [draftAssignments, setDraftAssignments] = useState<Record<string, string[]>>({});
  const [savingUser, setSavingUser] = useState("");
  const [userFilter, setUserFilter] = useState<UserFilter>("all");

  const load = useCallback(async () => {
    setError("");
    try {
      const headers = authHeaders();
      const [projectsRes, accessRes, mappingRes] = await Promise.all([
        fetch(`${API}/projects`, { headers }),
        fetch(`${API}/admin/projects/access`, { headers }),
        fetch(`${API}/admin/projects/build-mapping`, { headers }),
      ]);

      if (!projectsRes.ok || !accessRes.ok || !mappingRes.ok) {
        throw new Error("Failed to load project administration data");
      }

      const projectsData = await projectsRes.json();
      const accessData = await accessRes.json();
      const mappingData = await mappingRes.json();

      const nextProjects: string[] = Array.isArray(projectsData.projects) ? projectsData.projects : [];
      const nextProjectItems: ProjectItem[] = Array.isArray(projectsData.project_items)
        ? projectsData.project_items
            .map((row: Partial<ProjectItem>) => ({
              project_id: String(row.project_id || "").trim(),
              parent_project_id: row.parent_project_id ? String(row.parent_project_id) : null,
              is_subproject: Boolean(row.is_subproject),
            }))
            .filter((row: ProjectItem) => row.project_id)
        : nextProjects.map((project) => ({
            project_id: project,
            parent_project_id: null,
            is_subproject: false,
          }));
      const nextUsers: AccessUser[] = Array.isArray(accessData.users) ? accessData.users : [];

      setProjects(nextProjects);
      setProjectItems(nextProjectItems);
      setUsers(nextUsers);
      setMapping((mappingData.builds || {}) as BuildMapping);
      setUnassignedBuilds(Array.isArray(mappingData.unassigned) ? mappingData.unassigned : []);

      const parentMap: Record<string, string> = {};
      for (const item of nextProjectItems) {
        parentMap[item.project_id] = item.parent_project_id || "";
      }
      setParentDrafts(parentMap);

      const drafts: Record<string, string[]> = {};
      for (const user of nextUsers) {
        drafts[user.username] = Array.isArray(user.projects) ? [...user.projects] : [];
      }
      setDraftAssignments(drafts);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const sortedProjects = useMemo(
    () => [...projects].sort((a, b) => a.localeCompare(b)),
    [projects],
  );

  const sortedUsers = useMemo(
    () => [...users].sort((a, b) => a.username.localeCompare(b.username)),
    [users],
  );

  const projectItemById = useMemo(() => {
    const map = new Map<string, ProjectItem>();
    for (const item of projectItems) {
      map.set(item.project_id.toLowerCase(), item);
    }
    return map;
  }, [projectItems]);

  /** Builds per project and users per project, both derived rather than stored:
   *  a second copy of a count is a second thing that can be wrong. */
  const projectStats = useMemo(() => {
    const stats: Record<string, { builds: number; users: number }> = {};
    for (const project of sortedProjects) {
      stats[project] = { builds: 0, users: 0 };
    }
    for (const projectId of Object.values(mapping)) {
      const match = sortedProjects.find((p) => p.toLowerCase() === String(projectId).toLowerCase());
      if (match) stats[match].builds += 1;
    }
    for (const user of sortedUsers) {
      for (const assigned of user.projects || []) {
        const match = sortedProjects.find((p) => p.toLowerCase() === String(assigned).toLowerCase());
        if (match) stats[match].users += 1;
      }
    }
    return stats;
  }, [mapping, sortedProjects, sortedUsers]);

  const filteredUsers = useMemo(() => {
    if (userFilter === "no-access") {
      return sortedUsers.filter((u) => (u.projects || []).length === 0);
    }
    if (userFilter === "multi") {
      return sortedUsers.filter((u) => (u.projects || []).length > 1);
    }
    return sortedUsers;
  }, [sortedUsers, userFilter]);

  const filterCounts = useMemo(
    () => ({
      all: sortedUsers.length,
      noAccess: sortedUsers.filter((u) => (u.projects || []).length === 0).length,
      multi: sortedUsers.filter((u) => (u.projects || []).length > 1).length,
    }),
    [sortedUsers],
  );

  /** One place for "call the API, report what happened, reload". Every action
   *  on this page has the same shape, and hand-rolling it per button is how
   *  half of them ended up swallowing the server's reason for refusing. */
  const run = useCallback(
    async (
      label: string,
      request: () => Promise<Response>,
      describe: (payload: Record<string, unknown>) => string,
    ) => {
      setError("");
      setNotice("");
      try {
        const res = await request();
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(String(payload.detail || `Failed to ${label}`));
        setNotice(describe(payload));
        await load();
        return true;
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : `Failed to ${label}`);
        return false;
      }
    },
    [load],
  );

  const createProject = async () => {
    const projectId = newProjectId.trim();
    if (!projectId) return;
    setCreating(true);
    const ok = await run(
      "create project",
      () =>
        fetch(`${API}/admin/projects`, {
          method: "POST",
          headers: jsonHeaders(),
          body: JSON.stringify({
            project_id: projectId,
            parent_project_id: newParentProjectId || null,
          }),
        }),
      (payload) =>
        payload.first_project
          ? `Project ${projectId} created and granted to all ${payload.seeded_users || 0} existing account(s) — it is this install's first project.`
          : `Project ${projectId} created. Nobody has access to it yet - assign it below.`,
    );
    if (ok) {
      setNewProjectId("");
      setNewParentProjectId("");
    }
    setCreating(false);
  };

  const saveProjectParent = async (project: string) => {
    setSavingParentProject(project);
    const draftParent = String(parentDrafts[project] || "").trim();
    await run(
      "save project parent",
      () =>
        fetch(`${API}/admin/projects/${encodeURIComponent(project)}/parent`, {
          method: "PUT",
          headers: jsonHeaders(),
          body: JSON.stringify({ parent_project_id: draftParent || null }),
        }),
      (payload) =>
        payload.parent_project_id
          ? `${project} moved under ${payload.parent_project_id}.`
          : `${project} is now a top-level project.`,
    );
    setSavingParentProject("");
  };

  const deleteProject = async (project: string) => {
    if (!window.confirm(`Delete project "${project}"? Only possible while no build belongs to it.`)) {
      return;
    }
    setBusyProject(project);
    await run(
      "delete project",
      () =>
        fetch(`${API}/admin/projects/${encodeURIComponent(project)}`, {
          method: "DELETE",
          headers: authHeaders(),
        }),
      () => `Project ${project} deleted.`,
    );
    setBusyProject("");
  };

  const grantToAllUsers = async (project: string) => {
    setBusyProject(project);
    await run(
      "grant project access",
      () =>
        fetch(`${API}/admin/projects/${encodeURIComponent(project)}/grant-all`, {
          method: "POST",
          headers: authHeaders(),
        }),
      (payload) => `${project} granted to ${payload.updated_users || 0} additional account(s).`,
    );
    setBusyProject("");
  };

  const claimUnassignedBuilds = async (project: string) => {
    if (
      !window.confirm(
        `Assign all ${unassignedBuilds.length} unassigned build(s) to "${project}"? Builds already owned by another project are not touched.`,
      )
    ) {
      return;
    }
    setBusyProject(project);
    await run(
      "assign builds",
      () =>
        fetch(`${API}/admin/projects/${encodeURIComponent(project)}/claim-unassigned-builds`, {
          method: "POST",
          headers: authHeaders(),
        }),
      (payload) => `${payload.assigned || 0} build(s) moved into ${project}.`,
    );
    setBusyProject("");
  };

  const assignBuild = async (buildId: string, project: string) => {
    if (!project) return;
    await run(
      "assign build",
      () =>
        fetch(`${API}/admin/projects/build-mapping/${encodeURIComponent(buildId)}`, {
          method: "PUT",
          headers: jsonHeaders(),
          body: JSON.stringify({ project_id: project }),
        }),
      () => `${buildId} now belongs to ${project}.`,
    );
  };

  const saveAssignment = async (username: string) => {
    setSavingUser(username);
    const list = (draftAssignments[username] || []).filter((p) =>
      sortedProjects.some((sp) => sp.toLowerCase() === p.toLowerCase()),
    );
    await run(
      "save project access",
      () =>
        fetch(`${API}/admin/projects/access/${encodeURIComponent(username)}`, {
          method: "PUT",
          headers: jsonHeaders(),
          body: JSON.stringify({ projects: list }),
        }),
      () =>
        list.length
          ? `${username} can now open: ${list.join(", ")}.`
          : `${username} has no project access.`,
    );
    setSavingUser("");
  };

  const toggleUserProject = (username: string, project: string) => {
    setDraftAssignments((prev) => {
      const current = prev[username] || [];
      const has = current.some((p) => p.toLowerCase() === project.toLowerCase());
      return {
        ...prev,
        [username]: has
          ? current.filter((p) => p.toLowerCase() !== project.toLowerCase())
          : [...current, project],
      };
    });
  };

  const isDirty = (user: AccessUser) => {
    const draft = [...(draftAssignments[user.username] || [])].sort();
    const saved = [...(user.projects || [])].sort();
    return draft.join("|") !== saved.join("|");
  };

  return (
    <PageTransition>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold">Projects</h2>
            <p className="text-sm text-slate-500 dark:text-white/40">
              A project owns its builds. Access to a project is access to those builds, and to
              nothing else.
            </p>
          </div>
          <button
            onClick={load}
            className="flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 text-sm hover:border-cyan-500/40 dark:border-white/10"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>

        {error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/[0.08] p-3 text-sm text-red-500">
            {error}
          </div>
        )}
        {notice && (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.08] p-3 text-sm text-emerald-500">
            {notice}
          </div>
        )}

        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-white/[0.08] dark:bg-white/[0.02]">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
            Create project
          </h3>
          <div className="flex flex-wrap gap-2">
            <input
              value={newProjectId}
              onChange={(e) => setNewProjectId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") createProject();
              }}
              placeholder="Project id (2-64 chars: letters, numbers, . _ -)"
              className="min-w-[18rem] flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500/50 dark:border-white/[0.12] dark:bg-white/[0.03]"
            />
            <select
              value={newParentProjectId}
              onChange={(e) => setNewParentProjectId(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500/50 dark:border-white/[0.12] dark:bg-white/[0.03]"
            >
              <option value="">No parent (top-level)</option>
              {sortedProjects.map((project) => (
                <option key={project} value={project}>
                  {project}
                </option>
              ))}
            </select>
            <button
              onClick={createProject}
              disabled={creating || !newProjectId.trim()}
              className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <FolderPlus className="h-4 w-4" />
              {creating ? "Creating..." : "Create"}
            </button>
          </div>
          <p className="text-xs text-slate-500 dark:text-white/35">
            Creating a project grants nobody access to it — except on a fresh install, where the
            first project is given to every existing account so the system is usable at all.
          </p>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/[0.08] dark:bg-white/[0.02]">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
            Projects
          </h3>
          {loading ? (
            <SkeletonRows count={3} />
          ) : sortedProjects.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-white/40">No projects yet.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {sortedProjects.map((project) => {
                const stats = projectStats[project] || { builds: 0, users: 0 };
                const busy = busyProject === project;
                return (
                  <div
                    key={project}
                    className="rounded-xl border border-slate-200 p-4 dark:border-white/[0.08]"
                  >
                    <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">
                      {project}
                    </p>
                    {projectItemById.get(project.toLowerCase())?.parent_project_id && (
                      <p className="mt-0.5 text-[11px] text-slate-500 dark:text-white/40">
                        Sub-project of {projectItemById.get(project.toLowerCase())?.parent_project_id}
                      </p>
                    )}
                    <p className="mt-1 flex items-center gap-3 text-xs text-slate-500 dark:text-white/40">
                      <span className="inline-flex items-center gap-1">
                        <Database className="h-3 w-3" /> {stats.builds} build
                        {stats.builds === 1 ? "" : "s"}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <UsersRound className="h-3 w-3" /> {stats.users} user
                        {stats.users === 1 ? "" : "s"}
                      </span>
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <select
                        value={parentDrafts[project] || ""}
                        onChange={(e) =>
                          setParentDrafts((prev) => ({
                            ...prev,
                            [project]: e.target.value,
                          }))
                        }
                        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs dark:border-white/[0.12] dark:bg-white/[0.03]"
                      >
                        <option value="">Top-level</option>
                        {sortedProjects
                          .filter((candidate) => candidate.toLowerCase() !== project.toLowerCase())
                          .map((candidate) => (
                            <option key={candidate} value={candidate}>
                              Parent: {candidate}
                            </option>
                          ))}
                      </select>
                      <button
                        onClick={() => saveProjectParent(project)}
                        disabled={savingParentProject === project}
                        className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-semibold hover:border-cyan-500/40 disabled:opacity-60 dark:border-white/[0.12]"
                      >
                        {savingParentProject === project ? "Saving parent..." : "Save parent"}
                      </button>
                      <button
                        onClick={() => grantToAllUsers(project)}
                        disabled={busy}
                        className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-semibold hover:border-cyan-500/40 disabled:opacity-60 dark:border-white/[0.12]"
                      >
                        Grant to all users
                      </button>
                      {unassignedBuilds.length > 0 && (
                        <button
                          onClick={() => claimUnassignedBuilds(project)}
                          disabled={busy}
                          className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-semibold hover:border-cyan-500/40 disabled:opacity-60 dark:border-white/[0.12]"
                        >
                          Claim {unassignedBuilds.length} unassigned
                        </button>
                      )}
                      <button
                        onClick={() => deleteProject(project)}
                        disabled={busy || stats.builds > 0}
                        title={
                          stats.builds > 0
                            ? "Reassign or delete this project's builds first"
                            : "Delete project"
                        }
                        className="inline-flex items-center gap-1 rounded-lg border border-red-300 px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-500/30 dark:text-red-400 dark:hover:bg-red-500/10"
                      >
                        <Trash2 className="h-3 w-3" /> Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {unassignedBuilds.length > 0 && (
          <section className="rounded-xl border border-amber-300/40 bg-amber-50 p-4 dark:border-amber-500/30 dark:bg-amber-500/[0.06]">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-300">
              Unassigned builds ({unassignedBuilds.length})
            </h3>
            <p className="mt-1 text-xs text-amber-800/80 dark:text-amber-200/70">
              Ingested before projects existed. Only administrators can see them until they are
              assigned.
            </p>
            <div className="mt-3 space-y-2">
              {unassignedBuilds.map((buildId) => (
                <div key={buildId} className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-white/60 px-2 py-1 text-xs text-slate-700 dark:bg-black/30 dark:text-white/70">
                    {buildId}
                  </code>
                  <select
                    defaultValue=""
                    onChange={(e) => assignBuild(buildId, e.target.value)}
                    className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs dark:border-white/[0.12] dark:bg-white/[0.03]"
                  >
                    <option value="">Assign to project...</option>
                    {sortedProjects.map((project) => (
                      <option key={project} value={project}>
                        {project}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/[0.08] dark:bg-white/[0.02]">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-500 dark:text-white/40">
              Per-user access
            </h3>
            <div className="flex gap-1.5">
              {(
                [
                  ["all", `All (${filterCounts.all})`],
                  ["no-access", `No access (${filterCounts.noAccess})`],
                  ["multi", `Multi-project (${filterCounts.multi})`],
                ] as [UserFilter, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setUserFilter(value)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                    userFilter === value
                      ? "bg-cyan-600 text-white"
                      : "border border-slate-300 text-slate-600 dark:border-white/[0.12] dark:text-white/60"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <SkeletonRows count={4} />
          ) : filteredUsers.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-white/40">No accounts match this filter.</p>
          ) : (
            <div className="space-y-2">
              {filteredUsers.map((user) => {
                const draft = draftAssignments[user.username] || [];
                const adminAccount = ["admin", "cto"].includes(String(user.role).toLowerCase());
                return (
                  <div
                    key={user.username}
                    className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-white/[0.08]"
                  >
                    <div className="min-w-[10rem]">
                      <p className="text-sm font-semibold text-slate-900 dark:text-white">
                        {user.username}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-white/40">{user.role}</p>
                    </div>

                    {adminAccount ? (
                      <p className="flex-1 text-xs text-slate-500 dark:text-white/40">
                        Administrators can open every project — that is what makes them able to
                        grant access in the first place.
                      </p>
                    ) : (
                      <>
                        <div className="flex flex-1 flex-wrap gap-1.5">
                          {sortedProjects.map((project) => {
                            const on = draft.some((p) => p.toLowerCase() === project.toLowerCase());
                            return (
                              <button
                                key={project}
                                onClick={() => toggleUserProject(user.username, project)}
                                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                                  on
                                    ? "bg-cyan-600 text-white"
                                    : "border border-slate-300 text-slate-600 hover:border-cyan-500/40 dark:border-white/[0.12] dark:text-white/60"
                                }`}
                              >
                                {project}
                              </button>
                            );
                          })}
                        </div>
                        <button
                          onClick={() => saveAssignment(user.username)}
                          disabled={savingUser === user.username || !isDirty(user)}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Save className="h-3 w-3" />
                          {savingUser === user.username ? "Saving..." : "Save"}
                        </button>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </PageTransition>
  );
}
